# pc1_servidor.py - PC 1 (Mestre) - COMPLETO COM WEBCAM + TELA
import os
import threading
import time
import json
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog
from pyftpdlib.authorizers import DummyAuthorizer
from pyftpdlib.handlers import FTPHandler
from pyftpdlib.servers import FTPServer
import socket
import sounddevice as sd
import numpy as np
import asyncio
import websockets
from PIL import Image, ImageTk
import io

# ============ GLOBAL ============
frame_atual = None
dispositivos_conectados = {}
dispositivo_selecionado = None
audio_queue = []
audio_lock = threading.Lock()

async def ws_handler(websocket):
    global dispositivos_conectados, frame_atual, audio_queue, audio_lock
    ip = websocket.remote_address[0]
    
    try:
        async for message in websocket:
            if isinstance(message, bytes):
                if message[:4] == b'CMD:':
                    dados = json.loads(message[4:].decode())
                    if ip not in dispositivos_conectados:
                        dispositivos_conectados[ip] = {}
                    dispositivos_conectados[ip]["ws"] = websocket
                    dispositivos_conectados[ip]["ultimo_visto"] = time.time()
                    dispositivos_conectados[ip]["status"] = "online"
                    dispositivos_conectados[ip]["nome"] = dados.get("nome", ip)
                    dispositivos_conectados[ip]["cameras"] = dados.get("cameras", [])
                    dispositivos_conectados[ip]["microfones"] = dados.get("microfones", [])
                elif message[:4] == b'AUD:':
                    with audio_lock:
                        audio_queue.append(message[4:])
                        if len(audio_queue) > 200:
                            audio_queue.pop(0)
                else:
                    frame_atual = message
    except:
        pass
    finally:
        if ip in dispositivos_conectados:
            dispositivos_conectados[ip]["status"] = "offline"
            dispositivos_conectados[ip]["ultimo_visto"] = time.time()

async def start_ws():
    async with websockets.serve(ws_handler, "0.0.0.0", 8765, max_size=2**23, ping_interval=None):
        await asyncio.Future()

# ============ AUDIO PLAYER ============
class AudioPlayer:
    def __init__(self, log_func=None):
        self.ouvindo = False
        self.log = log_func
        self.volume = 1.0
    
    def iniciar(self, device=None):
        try:
            self.ouvindo = True
            threading.Thread(target=self._tocar, args=(device,), daemon=True).start()
            if self.log:
                self.log("Audio iniciado")
            return True
        except Exception as e:
            if self.log:
                self.log(f"Erro audio: {e}")
            return False
    
    def _tocar(self, device):
        global audio_queue, audio_lock
        try:
            stream = sd.OutputStream(device=device, channels=1, samplerate=44100, blocksize=1024, dtype='float32')
            stream.start()
            
            while self.ouvindo:
                chunk = None
                with audio_lock:
                    if audio_queue:
                        chunk = audio_queue.pop(0)
                
                if chunk:
                    try:
                        data = np.frombuffer(chunk, dtype=np.float32).reshape(-1, 1)
                        data = np.clip(data * self.volume, -1.0, 1.0)
                        stream.write(data)
                    except:
                        pass
                else:
                    time.sleep(0.002)
            
            stream.stop()
            stream.close()
        except:
            pass
    
    def set_volume(self, vol):
        self.volume = vol
    
    def parar(self):
        self.ouvindo = False
        time.sleep(0.1)

# ============ FTP ============
class ServidorFTP:
    def __init__(self):
        self.server = None
    
    def iniciar(self, porta, pasta, usuario, senha, log):
        try:
            if not os.path.exists(pasta):
                os.makedirs(pasta)
            authorizer = DummyAuthorizer()
            authorizer.add_user(usuario, senha, pasta, perm="elradfmw")
            handler = FTPHandler
            handler.authorizer = authorizer
            self.server = FTPServer(("0.0.0.0", porta), handler)
            threading.Thread(target=self.server.serve_forever, daemon=True).start()
            ip = socket.gethostbyname(socket.gethostname())
            log(f"FTP: {ip}:{porta}")
            return True, ip
        except Exception as e:
            log(f"FTP erro: {e}")
            return False, None
    
    def parar(self):
        if self.server:
            self.server.close_all()

# ============ INTERFACE ============
class InterfacePC1:
    def __init__(self, root):
        self.root = root
        self.root.title("PC 1 - MESTRE")
        self.root.geometry("1050x950")
        self.ftp = ServidorFTP()
        self.audio = AudioPlayer(log_func=self.log)
        self.vendo = False
        self.ouvindo_audio = False
        self.mic_ligado = False
        
        self.criar_widgets()
        self.atualizar_lista()
        self.root.protocol("WM_DELETE_WINDOW", self.fechar)
    
    def criar_widgets(self):
        # Painel esquerdo
        self.panel_esq = ttk.Frame(self.root, width=250)
        self.panel_esq.pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=5)
        self.panel_esq.pack_propagate(False)
        
        self.panel_dir = ttk.Frame(self.root)
        self.panel_dir.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # === ESQUERDA ===
        ttk.Label(self.panel_esq, text="DISPOSITIVOS", font=("Arial", 12, "bold")).pack(pady=5)
        
        self.tree = ttk.Treeview(self.panel_esq, columns=('nome', 'status'), show='headings', height=10)
        self.tree.heading('nome', text='Nome')
        self.tree.heading('status', text='Status')
        self.tree.column('nome', width=140)
        self.tree.column('status', width=80)
        self.tree.pack(fill=tk.BOTH, expand=True)
        self.tree.bind('<Double-1>', self.selecionar)
        
        ttk.Button(self.panel_esq, text="Atualizar", command=self.atualizar_lista).pack(pady=5)
        
        f1 = ttk.LabelFrame(self.panel_esq, text="Servidor", padding=5)
        f1.pack(fill=tk.X, pady=5)
        ttk.Label(f1, text="Porta:").pack()
        self.porta_var = tk.StringVar(value="2121")
        ttk.Entry(f1, textvariable=self.porta_var, width=10).pack()
        ttk.Label(f1, text="User:").pack()
        self.user_var = tk.StringVar(value="admin")
        ttk.Entry(f1, textvariable=self.user_var, width=10).pack()
        ttk.Label(f1, text="Senha:").pack()
        self.senha_var = tk.StringVar(value="senai2024")
        ttk.Entry(f1, textvariable=self.senha_var, width=10, show="*").pack()
        
        self.btn_iniciar = ttk.Button(self.panel_esq, text="INICIAR SERVIDOR", command=self.iniciar)
        self.btn_iniciar.pack(pady=5, fill=tk.X)
        self.btn_parar = ttk.Button(self.panel_esq, text="PARAR", command=self.parar, state=tk.DISABLED)
        self.btn_parar.pack(pady=2, fill=tk.X)
        
        # === DIREITA ===
        f2 = ttk.LabelFrame(self.panel_dir, text="Dispositivo Gerenciado", padding=10)
        f2.pack(fill=tk.X, pady=5)
        
        self.label_disp = tk.Label(f2, text="Nenhum dispositivo selecionado", font=("Arial", 14, "bold"), fg="gray")
        self.label_disp.pack()
        
        fc = ttk.Frame(f2)
        fc.pack(pady=5)
        ttk.Button(fc, text="TROCAR", command=self.trocar).pack(side=tk.LEFT, padx=5)
        ttk.Button(fc, text="REINICIAR PC 2", command=self.reiniciar_pc2).pack(side=tk.LEFT, padx=5)
        ttk.Button(fc, text="DESLIGAR PC 2", command=self.desligar_pc2).pack(side=tk.LEFT, padx=5)
        ttk.Button(fc, text="RECONECTAR PC 2", command=self.reconectar_pc2).pack(side=tk.LEFT, padx=5)
        
        # Camera / Tela
        f3 = ttk.LabelFrame(self.panel_dir, text="Visualizacao", padding=10)
        f3.pack(fill=tk.X, pady=5)
        
        fc2 = ttk.Frame(f3)
        fc2.pack(fill=tk.X)
        ttk.Button(fc2, text="📷 WEBCAM", command=self.iniciar_webcam).pack(side=tk.LEFT, padx=5)
        ttk.Button(fc2, text="🖥️ TELA", command=self.iniciar_tela).pack(side=tk.LEFT, padx=5)
        ttk.Button(fc2, text="⏹ PARAR", command=self.parar_video).pack(side=tk.LEFT, padx=5)
        self.video_status = tk.StringVar(value="--")
        ttk.Label(fc2, textvariable=self.video_status).pack(side=tk.LEFT, padx=5)
        
        self.frame_video = tk.Frame(f3, width=750, height=480, bg="black")
        self.frame_video.pack(pady=10)
        self.frame_video.pack_propagate(False)
        self.label_video = tk.Label(self.frame_video, text="Visualizacao desligada", bg="black", fg="white")
        self.label_video.pack(fill="both", expand=True)
        
        # Microfone
        f4 = ttk.LabelFrame(self.panel_dir, text="Microfone", padding=10)
        f4.pack(fill=tk.X, pady=5)
        
        fm = ttk.Frame(f4)
        fm.pack(fill=tk.X)
        self.combo_mic = ttk.Combobox(fm, values=["..."], width=30, state="readonly")
        self.combo_mic.pack(side=tk.LEFT, padx=5)
        self.btn_mic = ttk.Button(fm, text="LIGAR MIC", command=self.toggle_mic, state=tk.DISABLED)
        self.btn_mic.pack(side=tk.LEFT, padx=5)
        self.mic_status = tk.StringVar(value="--")
        ttk.Label(fm, textvariable=self.mic_status).pack(side=tk.LEFT, padx=5)
        
        # Audio
        f5 = ttk.LabelFrame(self.panel_dir, text="Ouvir Audio (UDP)", padding=10)
        f5.pack(fill=tk.X, pady=5)
        
        self.saidas = [("Padrao", None)]
        for i, d in enumerate(sd.query_devices()):
            if d['max_output_channels'] > 0:
                self.saidas.append((f"{i}: {d['name'][:30]}", i))
        
        self.combo_saida = ttk.Combobox(f5, values=[s[0] for s in self.saidas], width=25, state="readonly")
        self.combo_saida.pack(side=tk.LEFT, padx=5)
        self.combo_saida.current(0)
        
        self.btn_audio = ttk.Button(f5, text="OUVIR", command=self.toggle_audio, state=tk.DISABLED)
        self.btn_audio.pack(side=tk.LEFT, padx=10)
        self.audio_status = tk.StringVar(value="Parado")
        ttk.Label(f5, textvariable=self.audio_status).pack(side=tk.LEFT, padx=5)
        
        ttk.Label(f5, text="Vol:").pack(side=tk.LEFT, padx=5)
        self.vol_var = tk.DoubleVar(value=1.0)
        ttk.Scale(f5, from_=0, to=5, variable=self.vol_var, length=120, command=self.mudar_vol).pack(side=tk.LEFT, padx=5)
        self.vol_label = ttk.Label(f5, text="100%")
        self.vol_label.pack(side=tk.LEFT, padx=5)
        
        # Log
        f6 = ttk.LabelFrame(self.panel_dir, text="Log", padding=5)
        f6.pack(fill=tk.X, pady=5)
        self.log_text = scrolledtext.ScrolledText(f6, height=4)
        self.log_text.pack(fill=tk.X)
        
        try:
            ip = socket.gethostbyname(socket.gethostname())
            self.log(f"IP: {ip} | WS: ws://{ip}:8765 | FTP: {ip}:2121 | UDP: {ip}:9999")
        except:
            pass
    
    def log(self, msg):
        t = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{t}] {msg}\n")
        self.log_text.see(tk.END)
    
    def mudar_vol(self, e=None):
        v = self.vol_var.get()
        self.audio.set_volume(v)
        self.vol_label.config(text=f"{int(v*100)}%")
    
    def atualizar_lista(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        agora = time.time()
        for ip, d in dispositivos_conectados.items():
            nome = d.get("nome", ip)
            status = "🟢 ONLINE" if agora - d.get("ultimo_visto", 0) < 30 else "🔴 OFFLINE"
            self.tree.insert('', tk.END, iid=ip, values=(nome, status))
        self.root.after(3000, self.atualizar_lista)
    
    def selecionar(self, event=None):
        sel = self.tree.selection()
        if sel:
            global dispositivo_selecionado
            dispositivo_selecionado = sel[0]
            d = dispositivos_conectados.get(dispositivo_selecionado, {})
            self.label_disp.config(text=f"Gerenciando: {d.get('nome', dispositivo_selecionado)}", fg="green")
            
            mics = d.get('microfones', [])
            self.combo_mic['values'] = mics or ["Nenhum"]
            if mics: self.combo_mic.current(0)
            
            self.btn_mic.config(state=tk.NORMAL)
            self.btn_audio.config(state=tk.NORMAL)
            self.mic_status.set("Pronto")
    
    def trocar(self):
        global dispositivo_selecionado
        dispositivo_selecionado = None
        self.label_disp.config(text="Nenhum dispositivo", fg="gray")
        self.combo_mic['values'] = ["..."]
        self.btn_mic.config(state=tk.DISABLED)
        self.btn_audio.config(state=tk.DISABLED)
        self.vendo = False
        self.label_video.config(image="", text="Visualizacao desligada", bg="black", fg="white")
    
    def enviar(self, cmd):
        global dispositivo_selecionado
        if not dispositivo_selecionado:
            return False
        d = dispositivos_conectados.get(dispositivo_selecionado, {})
        ws = d.get("ws")
        if ws:
            try:
                asyncio.run(ws.send(f"CMD:{json.dumps(cmd)}".encode()))
                return True
            except:
                pass
        return False
    
    def iniciar_webcam(self):
        self.enviar({"acao": "iniciar_camera"})
        self.vendo = True
        self.video_status.set("Webcam AO VIVO")
        self.log("Webcam iniciada")
        threading.Thread(target=self._video, daemon=True).start()
    
    def iniciar_tela(self):
        self.enviar({"acao": "iniciar_tela"})
        self.vendo = True
        self.video_status.set("Tela AO VIVO")
        self.log("Captura de tela iniciada")
        threading.Thread(target=self._video, daemon=True).start()
    
    def parar_video(self):
        self.enviar({"acao": "parar_camera"})
        self.enviar({"acao": "parar_tela"})
        self.vendo = False
        self.video_status.set("Desligado")
        self.label_video.config(image="", text="Visualizacao desligada", bg="black", fg="white")
        self.log("Video parado")
    
    def _video(self):
        global frame_atual
        while self.vendo:
            if frame_atual:
                try:
                    img = Image.open(io.BytesIO(frame_atual))
                    img = img.resize((750, 480), Image.Resampling.LANCZOS)
                    img_tk = ImageTk.PhotoImage(img)
                    self.label_video.config(image=img_tk, text="", bg="black")
                    self.label_video.image = img_tk
                except:
                    pass
            time.sleep(0.03)
    
    def reiniciar_pc2(self):
        if messagebox.askyesno("Confirmar", "Reiniciar programa do PC 2?"):
            self.enviar({"acao": "reiniciar"})
            self.log("Reiniciar enviado")
    
    def desligar_pc2(self):
        if messagebox.askyesno("Confirmar", "Fechar programa do PC 2?"):
            self.enviar({"acao": "desligar_cliente"})
            self.log("Desligar enviado")
    
    def reconectar_pc2(self):
        self.enviar({"acao": "reconectar"})
        self.log("Reconectar enviado")
    
    def iniciar(self):
        try:
            threading.Thread(target=lambda: asyncio.run(start_ws()), daemon=True).start()
            time.sleep(0.5)
            self.log("WebSocket porta 8765")
            ok, _ = self.ftp.iniciar(int(self.porta_var.get()), "C:\\", self.user_var.get(), self.senha_var.get(), self.log)
            if ok:
                self.btn_iniciar.config(state=tk.DISABLED)
                self.btn_parar.config(state=tk.NORMAL)
        except Exception as e:
            messagebox.showerror("Erro", str(e))
    
    def toggle_mic(self):
        if self.mic_ligado:
            self.enviar({"acao": "parar_mic"})
            self.mic_ligado = False
            self.btn_mic.config(text="LIGAR MIC")
            self.mic_status.set("Desligado")
        else:
            sel = self.combo_mic.get()
            idx = 1
            if ":" in sel:
                try:
                    idx = int(sel.split(":")[0])
                except:
                    pass
            self.enviar({"acao": "iniciar_mic", "indice": idx})
            self.mic_ligado = True
            self.btn_mic.config(text="DESLIGAR MIC")
            self.mic_status.set("Ligado")
    
    def toggle_audio(self):
        if self.ouvindo_audio:
            self.audio.parar()
            self.ouvindo_audio = False
            self.btn_audio.config(text="OUVIR")
            self.audio_status.set("Parado")
        else:
            sel = self.combo_saida.get()
            dev = None
            for n, d in self.saidas:
                if n == sel:
                    dev = d
                    break
            if self.audio.iniciar(device=dev):
                self.ouvindo_audio = True
                self.btn_audio.config(text="PARAR")
                self.audio_status.set("OUVINDO")
    
    def parar(self):
        self.vendo = False
        if self.ouvindo_audio:
            self.audio.parar()
        self.ftp.parar()
        self.btn_iniciar.config(state=tk.NORMAL)
        for b in [self.btn_parar, self.btn_mic, self.btn_audio]:
            b.config(state=tk.DISABLED)
    
    def fechar(self):
        self.parar()
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = InterfacePC1(root)
    root.mainloop()