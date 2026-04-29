# pc2_cliente.py - PC 2 (Cliente) - COMPLETO COM WEBCAM + TELA
import os
os.environ["OPENCV_VIDEOIO_DEBUG"] = "0"
os.environ["OPENCV_LOG_LEVEL"] = "OFF"

import threading
import time
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
from datetime import datetime
import cv2
import sounddevice as sd
import numpy as np
import asyncio
import websockets
import json
import socket
import subprocess
import sys
import mss

try:
    import pystray
    from PIL import Image, ImageDraw
    TRAY_DISPONIVEL = True
except:
    TRAY_DISPONIVEL = False

class ClientePC2:
    def __init__(self, root):
        self.root = root
        self.root.title("PC 2 - Cliente")
        self.root.geometry("500x500")
        
        self.cap = None
        self.sct = None
        self.modo_tela = False
        self.enviando_camera = False
        self.enviando_audio = False
        self.ip_servidor = "127.0.0.1"
        self.sock_udp = None
        self.nome_dispositivo = socket.gethostname()
        self.ws = None
        self.janela_visivel = True
        self.mic_indice = 1
        
        self.criar_widgets()
        if TRAY_DISPONIVEL:
            self.criar_tray()
        self.root.protocol("WM_DELETE_WINDOW", self.minimizar_para_tray)
        self.root.after(500, self.conectar)
    
    # ============ TRAY ============
    def criar_tray(self):
        def criar_icone():
            img = Image.new('RGB', (64, 64), color='purple')
            draw = ImageDraw.Draw(img)
            draw.rectangle([16, 16, 48, 48], fill='white')
            draw.text((22, 22), "P2", fill='purple')
            return img
        
        menu = pystray.Menu(
            pystray.MenuItem("Mostrar Janela", lambda: self.root.after(0, self.mostrar_janela)),
            pystray.MenuItem("Reiniciar", lambda: self.root.after(0, self.reiniciar)),
            pystray.MenuItem("Sair", lambda: self.root.after(0, self.fechar_app))
        )
        self.tray_icon = pystray.Icon("PC2", criar_icone(), "PC 2 - SENAI", menu)
        threading.Thread(target=self.tray_icon.run, daemon=True).start()
    
    def minimizar_para_tray(self):
        self.root.withdraw()
        self.janela_visivel = False
    
    def mostrar_janela(self):
        self.root.deiconify()
        self.root.lift()
        self.janela_visivel = True
    
    def reiniciar(self):
        self.log("Reiniciando programa...")
        self.parar_tudo()
        python = sys.executable
        subprocess.Popen([python] + sys.argv)
        self.root.destroy()
        sys.exit(0)
    
    # ============ DETECÇÃO ============
    def detectar_dispositivos(self):
        cameras = []
        for i in range(5):
            try:
                cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
                if cap.isOpened():
                    cameras.append(f"Camera {i}")
                    cap.release()
            except:
                pass
        if not cameras:
            cameras = ["Camera 0"]
        
        microfones = []
        for i, d in enumerate(sd.query_devices()):
            if d['max_input_channels'] > 0:
                microfones.append(f"{i}: {d['name']}")
        
        return {"nome": self.nome_dispositivo, "cameras": cameras, "microfones": microfones}
    
    # ============ INTERFACE ============
    def criar_widgets(self):
        tk.Label(self.root, text="PC 2 - CLIENTE", font=("Arial", 16, "bold"), fg="purple").pack(pady=5)
        tk.Label(self.root, text=f"Nome: {self.nome_dispositivo}", fg="blue").pack()
        tk.Label(self.root, text="Minimize para bandeja - continua rodando", fg="gray", font=("Arial", 7)).pack()
        
        # Conexão
        f1 = ttk.LabelFrame(self.root, text="Conexao", padding=10)
        f1.pack(fill=tk.X, padx=15, pady=5)
        
        ttk.Label(f1, text="IP Servidor:").grid(row=0, column=0)
        self.ip_var = tk.StringVar(value=self.ip_servidor)
        ttk.Entry(f1, textvariable=self.ip_var, width=18).grid(row=0, column=1, padx=5)
        
        self.btn_conectar = ttk.Button(f1, text="CONECTAR", command=self.conectar)
        self.btn_conectar.grid(row=0, column=2, padx=5)
        self.btn_reconectar = ttk.Button(f1, text="RECONECTAR", command=self.reconectar)
        self.btn_reconectar.grid(row=0, column=3, padx=5)
        
        # Status
        self.status_var = tk.StringVar(value="Desconectado")
        tk.Label(self.root, textvariable=self.status_var, font=("Arial", 11, "bold")).pack()
        
        # Status camera
        self.status_cam = tk.StringVar(value="Camera: --")
        tk.Label(self.root, textvariable=self.status_cam).pack()
        
        # Status tela
        self.status_tela = tk.StringVar(value="Tela: --")
        tk.Label(self.root, textvariable=self.status_tela).pack()
        
        # Status microfone
        self.status_mic = tk.StringVar(value="Microfone: --")
        tk.Label(self.root, textvariable=self.status_mic).pack()
        
        # Botões
        fb = ttk.Frame(self.root)
        fb.pack(fill=tk.X, padx=15, pady=5)
        ttk.Button(fb, text="Minimizar", command=self.minimizar_para_tray).pack(side=tk.LEFT, padx=5)
        ttk.Button(fb, text="Reiniciar", command=self.reiniciar).pack(side=tk.LEFT, padx=5)
        ttk.Button(fb, text="SAIR", command=self.fechar_app).pack(side=tk.RIGHT, padx=5)
        
        # Log
        fl = ttk.LabelFrame(self.root, text="Log", padding=5)
        fl.pack(fill=tk.BOTH, expand=True, padx=15, pady=5)
        self.log_text = scrolledtext.ScrolledText(fl, height=6)
        self.log_text.pack(fill=tk.BOTH, expand=True)
    
    def log(self, msg):
        t = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{t}] {msg}\n")
        self.log_text.see(tk.END)
    
    # ============ CONEXÃO ============
    def conectar(self):
        self.ip_servidor = self.ip_var.get()
        self.btn_conectar.config(state=tk.DISABLED)
        self.status_var.set("Conectando...")
        self.log(f"Conectando a {self.ip_servidor}...")
        threading.Thread(target=self._run_websocket, daemon=True).start()
    
    def reconectar(self):
        self.log("Reconectando...")
        self.parar_tudo()
        time.sleep(0.5)
        self.conectar()
    
    def parar_tudo(self):
        self.enviando_camera = False
        self.enviando_audio = False
        if self.sock_udp:
            try:
                self.sock_udp.close()
            except:
                pass
            self.sock_udp = None
        if self.cap:
            try:
                self.cap.release()
            except:
                pass
            self.cap = None
    
    # ============ WEBSOCKET ============
    def _run_websocket(self):
        async def main():
            uri = f"ws://{self.ip_servidor}:8765"
            while True:
                try:
                    async with websockets.connect(uri, ping_interval=None, max_size=2**23, close_timeout=5) as ws:
                        self.ws = ws
                        self.status_var.set("Conectado")
                        self.log("Conectado ao servidor!")
                        
                        info = self.detectar_dispositivos()
                        await ws.send(f"CMD:{json.dumps(info)}".encode())
                        self.log(f"Registrado como: {self.nome_dispositivo}")
                        
                        last_hb = time.time()
                        
                        while True:
                            try:
                                msg = await asyncio.wait_for(ws.recv(), timeout=3)
                                if isinstance(msg, bytes):
                                    if msg[:4] == b'CMD:':
                                        cmd = json.loads(msg[4:].decode())
                                        self.executar_cmd(cmd)
                            except asyncio.TimeoutError:
                                agora = time.time()
                                if agora - last_hb > 5:
                                    info = self.detectar_dispositivos()
                                    try:
                                        await ws.send(f"CMD:{json.dumps(info)}".encode())
                                        last_hb = agora
                                    except:
                                        break
                                continue
                            except:
                                break
                except Exception as e:
                    self.log(f"Conexao perdida. Reconectando em 5s...")
                    self.status_var.set("Reconectando...")
                    await asyncio.sleep(5)
        
        asyncio.run(main())
    
    def executar_cmd(self, cmd):
        acao = cmd.get("acao", "")
        if acao == "iniciar_mic":
            self.iniciar_mic(cmd.get("indice", 1))
        elif acao == "parar_mic":
            self.parar_mic()
        elif acao == "iniciar_camera":
            self.iniciar_camera()
        elif acao == "parar_camera":
            self.parar_camera()
        elif acao == "iniciar_tela":
            self.iniciar_tela()
        elif acao == "parar_tela":
            self.parar_tela()
        elif acao == "reiniciar":
            self.log("Comando remoto: REINICIAR")
            self.root.after(500, self.reiniciar)
        elif acao == "desligar_cliente":
            self.log("Comando remoto: DESLIGAR")
            self.root.after(500, self.fechar_app)
        elif acao == "reconectar":
            self.log("Comando remoto: RECONECTAR")
            self.root.after(500, self.reconectar)
    
    # ============ WEBCAM ============
    def iniciar_camera(self):
        try:
            # Parar tela se estiver rodando
            self.parar_tela()
            
            for i in range(5):
                cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
                if cap.isOpened():
                    self.cap = cap
                    break
                cap.release()
            
            if not self.cap or not self.cap.isOpened():
                self.cap = cv2.VideoCapture(0)
            
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            self.cap.set(cv2.CAP_PROP_FPS, 20)
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            
            self.modo_tela = False
            self.enviando_camera = True
            self.status_cam.set("Webcam ATIVA")
            self.log("Webcam iniciada")
            threading.Thread(target=self._loop_webcam, daemon=True).start()
        except Exception as e:
            self.log(f"Erro webcam: {e}")
    
    def _loop_webcam(self):
        while self.enviando_camera and not self.modo_tela and self.cap and self.cap.isOpened():
            try:
                ret, frame = self.cap.read()
                if ret:
                    _, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 40])
                    if self.ws:
                        try:
                            asyncio.run(self._send_frame(buf.tobytes()))
                        except:
                            pass
                time.sleep(0.04)
            except:
                time.sleep(0.1)
    
    def parar_camera(self):
        self.enviando_camera = False
        if self.cap:
            self.cap.release()
            self.cap = None
        self.status_cam.set("Webcam Desligada")
        self.log("Webcam parada")
    
    # ============ TELA ============
    def iniciar_tela(self):
        try:
            # Parar webcam se estiver rodando
            self.parar_camera()
            
            self.sct = mss.mss()
            self.modo_tela = True
            self.enviando_camera = True
            self.status_tela.set("Tela ATIVA")
            self.log("Capturando TELA do PC")
            threading.Thread(target=self._loop_tela, daemon=True).start()
        except Exception as e:
            self.log(f"Erro tela: {e}")
    
    def _loop_tela(self):
        while self.enviando_camera and self.modo_tela and self.sct:
            try:
                monitor = self.sct.monitors[0]
                screenshot = self.sct.grab(monitor)
                frame = np.array(screenshot)
                frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
                frame = cv2.resize(frame, (800, 450))
                
                _, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 30])
                if self.ws:
                    try:
                        asyncio.run(self._send_frame(buf.tobytes()))
                    except:
                        pass
                time.sleep(0.05)
            except:
                time.sleep(0.1)
    
    def parar_tela(self):
        self.enviando_camera = False
        self.modo_tela = False
        self.sct = None
        self.status_tela.set("Tela Desligada")
        self.log("Captura de tela parada")
    
    async def _send_frame(self, data):
        if self.ws:
            try:
                await self.ws.send(data)
            except:
                pass
    
    # ============ MICROFONE UDP ============
    def iniciar_mic(self, indice):
        self.mic_indice = indice
        self.enviando_audio = True
        self.status_mic.set(f"Mic {indice} ativo")
        self.log(f"Microfone {indice} iniciado - enviando UDP para servidor")
        
        self.sock_udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        ip_audio = self.ip_servidor
        porta_audio = 9999
        
        def callback(indata, frames, time_info, status):
            if self.enviando_audio and self.sock_udp:
                try:
                    data = indata.copy().tobytes()
                    self.sock_udp.sendto(data, (ip_audio, porta_audio))
                except:
                    pass
        
        try:
            stream = sd.InputStream(
                device=indice,
                callback=callback,
                channels=1,
                samplerate=44100,
                blocksize=1024,
                dtype='float32'
            )
            stream.start()
            self.log(f"Audio UDP ATIVO - enviando para {ip_audio}:{porta_audio}")
            
            while self.enviando_audio:
                time.sleep(0.1)
            
            stream.stop()
            stream.close()
            self.log("Audio parado")
        except Exception as e:
            self.log(f"Erro ao abrir microfone: {e}")
            self.status_mic.set(f"Mic ERRO")
    
    def parar_mic(self):
        self.enviando_audio = False
        if self.sock_udp:
            try:
                self.sock_udp.close()
            except:
                pass
            self.sock_udp = None
        self.status_mic.set("Microfone desligado")
        self.log("Microfone desligado")
    
    def fechar_app(self):
        self.parar_tudo()
        if TRAY_DISPONIVEL and hasattr(self, 'tray_icon'):
            try:
                self.tray_icon.stop()
            except:
                pass
        self.root.destroy()
        os._exit(0)

if __name__ == "__main__":
    root = tk.Tk()
    app = ClientePC2(root)
    root.mainloop()