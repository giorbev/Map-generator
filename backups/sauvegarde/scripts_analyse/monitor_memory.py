"""
Moniteur RAM/VRAM en temps réel pour tests Reforger Workbench
Affiche et enregistre l'utilisation mémoire pendant l'application de masques terrain
SAUVEGARDE CONTINUE : les données sont écrites immédiatement sur disque (résiste aux crashs)
"""

import tkinter as tk
from tkinter import ttk
import psutil
import time
from datetime import datetime
from pathlib import Path
import threading

import subprocess
import wmi

def get_gpu_info_amd():
    """Récupère les infos GPU AMD via WMI (Windows) - priorise GPU dédié"""
    try:
        w = wmi.WMI(namespace="root\\cimv2")

        # Lister tous les GPUs AMD/Radeon
        amd_gpus = []
        for gpu in w.Win32_VideoController():
            if 'AMD' in gpu.Name or 'Radeon' in gpu.Name or 'ATI' in gpu.Name:
                vram_total_mb = int(gpu.AdapterRAM or 0) / (1024 * 1024) if gpu.AdapterRAM else 0
                amd_gpus.append({
                    'name': gpu.Name,
                    'memory_used': 0,
                    'memory_total': vram_total_mb,
                    'temperature': 0,
                    'load': 0,
                    'limited': True,
                    'is_integrated': 'Graphics' in gpu.Name or '780M' in gpu.Name or '680M' in gpu.Name
                })

        if not amd_gpus:
            return None

        # Prioriser GPU dédié (RX series) sur GPU intégré (780M, etc.)
        dedicated_gpus = [g for g in amd_gpus if not g['is_integrated']]
        if dedicated_gpus:
            # Retourner le GPU dédié avec le plus de VRAM
            return max(dedicated_gpus, key=lambda g: g['memory_total'])
        else:
            # Sinon retourner GPU intégré
            return amd_gpus[0]

    except:
        pass
    return None

def get_gpu_info_nvidia():
    """Récupère les infos GPU NVIDIA via nvidia-smi"""
    try:
        result = subprocess.run([
            'nvidia-smi',
            '--query-gpu=name,memory.used,memory.total,temperature.gpu,utilization.gpu',
            '--format=csv,noheader,nounits'
        ], capture_output=True, text=True, timeout=2, encoding='utf-8')

        if result.returncode == 0 and result.stdout.strip():
            parts = result.stdout.strip().split(',')
            if len(parts) >= 5:
                return {
                    'name': parts[0].strip(),
                    'memory_used': float(parts[1].strip()),
                    'memory_total': float(parts[2].strip()),
                    'temperature': float(parts[3].strip()),
                    'load': float(parts[4].strip()),
                    'limited': False
                }
    except:
        pass
    return None

def get_gpu_info():
    """Récupère les infos GPU (AMD ou NVIDIA)"""
    # Essayer NVIDIA d'abord
    info = get_gpu_info_nvidia()
    if info:
        return info

    # Sinon essayer AMD
    info = get_gpu_info_amd()
    if info:
        return info

    return None

# Test GPU availability
GPU_AVAILABLE = get_gpu_info() is not None
GPU_INFO_INITIAL = get_gpu_info()
if not GPU_AVAILABLE:
    print("GPU monitoring désactivé (aucun GPU AMD/NVIDIA détecté)")
else:
    if GPU_INFO_INITIAL and GPU_INFO_INITIAL.get('limited'):
        print(f"GPU AMD détecté: {GPU_INFO_INITIAL['name']} - monitoring limité (VRAM totale uniquement)")


class MemoryMonitor:
    def __init__(self, root):
        self.root = root
        self.root.title("Moniteur RAM/VRAM - Reforger Workbench")
        self.root.geometry("600x450")

        self.monitoring = False
        self.log_file = None
        self.start_time = None
        self.log_count = 0

        self.setup_ui()

    def setup_ui(self):
        # Frame principal
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # Affichage RAM
        ttk.Label(main_frame, text="RAM Système:", font=('Arial', 12, 'bold')).grid(row=0, column=0, sticky=tk.W, pady=5)
        self.ram_label = ttk.Label(main_frame, text="-- GB / -- GB (---%)", font=('Arial', 11))
        self.ram_label.grid(row=0, column=1, sticky=tk.W, padx=10)

        self.ram_progress = ttk.Progressbar(main_frame, length=400, mode='determinate')
        self.ram_progress.grid(row=1, column=0, columnspan=2, pady=5, sticky=(tk.W, tk.E))

        # Affichage VRAM
        ttk.Label(main_frame, text="VRAM GPU:", font=('Arial', 12, 'bold')).grid(row=2, column=0, sticky=tk.W, pady=(15,5))
        self.vram_label = ttk.Label(main_frame, text="-- MB / -- MB (---%)", font=('Arial', 11))
        self.vram_label.grid(row=2, column=1, sticky=tk.W, padx=10)

        self.vram_progress = ttk.Progressbar(main_frame, length=400, mode='determinate')
        self.vram_progress.grid(row=3, column=0, columnspan=2, pady=5, sticky=(tk.W, tk.E))

        # Infos complémentaires
        ttk.Separator(main_frame, orient='horizontal').grid(row=4, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=15)

        self.info_label = ttk.Label(main_frame, text="", font=('Arial', 9), foreground='gray')
        self.info_label.grid(row=5, column=0, columnspan=2, sticky=tk.W)

        # Contrôles
        control_frame = ttk.Frame(main_frame)
        control_frame.grid(row=6, column=0, columnspan=2, pady=20)

        self.start_button = ttk.Button(control_frame, text="▶ Démarrer logging", command=self.start_monitoring, width=20)
        self.start_button.pack(side=tk.LEFT, padx=5)

        self.stop_button = ttk.Button(control_frame, text="⬛ Arrêter", command=self.stop_monitoring, state='disabled', width=20)
        self.stop_button.pack(side=tk.LEFT, padx=5)

        # Fichier log
        self.log_label = ttk.Label(main_frame, text="Pas de logging en cours", font=('Arial', 9), foreground='blue')
        self.log_label.grid(row=7, column=0, columnspan=2)

        # Compteur enregistrements
        self.count_label = ttk.Label(main_frame, text="", font=('Arial', 9), foreground='green')
        self.count_label.grid(row=8, column=0, columnspan=2)

        # Intervalle de mise à jour
        interval_frame = ttk.Frame(main_frame)
        interval_frame.grid(row=9, column=0, columnspan=2, pady=10)

        ttk.Label(interval_frame, text="Intervalle (sec):").pack(side=tk.LEFT, padx=5)
        self.interval_var = tk.StringVar(value="1.0")
        interval_spin = ttk.Spinbox(interval_frame, from_=0.5, to=10.0, increment=0.5,
                                    textvariable=self.interval_var, width=10)
        interval_spin.pack(side=tk.LEFT)

        # Note sauvegarde continue
        note_frame = ttk.Frame(main_frame)
        note_frame.grid(row=10, column=0, columnspan=2, pady=10)
        ttk.Label(note_frame, text="✓ Sauvegarde continue activée (résiste aux crashs)",
                 font=('Arial', 8), foreground='darkgreen').pack()

        # Démarrer mise à jour affichage
        self.update_display()

    def update_display(self):
        # RAM système
        ram = psutil.virtual_memory()
        ram_used_gb = ram.used / (1024**3)
        ram_total_gb = ram.total / (1024**3)
        ram_percent = ram.percent

        self.ram_label.config(text=f"{ram_used_gb:.2f} GB / {ram_total_gb:.2f} GB ({ram_percent:.1f}%)")
        self.ram_progress['value'] = ram_percent

        # VRAM GPU
        if GPU_AVAILABLE:
            try:
                gpu_info = get_gpu_info()
                if gpu_info:
                    vram_used = gpu_info['memory_used']
                    vram_total = gpu_info['memory_total']

                    if gpu_info.get('limited'):
                        # GPU AMD - données limitées
                        self.vram_label.config(text=f"Total: {vram_total:.0f} MB (utilisée: N/A)")
                        self.vram_progress['value'] = 0
                        self.info_label.config(text=f"GPU: {gpu_info['name']} (monitoring limité - AMD)")
                    else:
                        # GPU NVIDIA - données complètes
                        vram_percent = (vram_used / vram_total * 100) if vram_total > 0 else 0
                        self.vram_label.config(text=f"{vram_used:.0f} MB / {vram_total:.0f} MB ({vram_percent:.1f}%)")
                        self.vram_progress['value'] = vram_percent
                        self.info_label.config(text=f"GPU: {gpu_info['name']} | Temp: {gpu_info['temperature']:.0f}°C | Load: {gpu_info['load']:.1f}%")
                else:
                    self.vram_label.config(text="Aucun GPU détecté")
                    self.vram_progress['value'] = 0
            except Exception as e:
                self.vram_label.config(text=f"Erreur GPU: {str(e)[:30]}")
                self.vram_progress['value'] = 0
        else:
            self.vram_label.config(text="Aucun GPU détecté")
            self.vram_progress['value'] = 0

        # Continuer mise à jour
        self.root.after(500, self.update_display)

    def start_monitoring(self):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_dir = Path("data/memory_logs")
        log_dir.mkdir(exist_ok=True)

        self.log_path = log_dir / f"memory_log_{timestamp}.txt"

        # Fichier texte avec écriture immédiate (unbuffered via flush)
        self.log_file = open(self.log_path, 'w', encoding='utf-8')

        # En-tête lisible
        self.log_file.write("=" * 80 + "\n")
        self.log_file.write(f"MONITEUR MÉMOIRE REFORGER WORKBENCH - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        self.log_file.write("=" * 80 + "\n")
        self.log_file.write(f"Intervalle: {self.interval_var.get()}s\n")

        if GPU_AVAILABLE:
            try:
                gpu_info = get_gpu_info()
                if gpu_info:
                    self.log_file.write(f"GPU détecté: {gpu_info['name']}\n")
            except:
                pass

        self.log_file.write("=" * 80 + "\n\n")
        self.log_file.flush()  # Force écriture immédiate

        self.monitoring = True
        self.start_time = time.time()
        self.log_count = 0

        self.start_button.config(state='disabled')
        self.stop_button.config(state='normal')
        self.log_label.config(text=f"📝 Logging: {self.log_path.name}", foreground='green')

        # Démarrer thread de logging
        self.log_thread = threading.Thread(target=self.log_data, daemon=True)
        self.log_thread.start()

    def log_data(self):
        while self.monitoring:
            try:
                elapsed = time.time() - self.start_time
                timestamp = datetime.now().strftime("%H:%M:%S")

                # RAM
                ram = psutil.virtual_memory()
                ram_used_gb = ram.used / (1024**3)
                ram_total_gb = ram.total / (1024**3)
                ram_percent = ram.percent

                # Construire ligne lisible
                line = f"[{timestamp}] +{elapsed:6.1f}s | RAM: {ram_used_gb:5.2f}/{ram_total_gb:5.2f} GB ({ram_percent:5.1f}%)"

                # VRAM
                if GPU_AVAILABLE:
                    try:
                        gpu_info = get_gpu_info()
                        if gpu_info:
                            if gpu_info.get('limited'):
                                # AMD - données limitées
                                vram_total = gpu_info['memory_total']
                                line += f" | VRAM: Total {vram_total:5.0f} MB (utilisée: N/A - AMD)"
                            else:
                                # NVIDIA - données complètes
                                vram_used = gpu_info['memory_used']
                                vram_total = gpu_info['memory_total']
                                vram_percent = (vram_used / vram_total * 100) if vram_total > 0 else 0
                                line += f" | VRAM: {vram_used:5.0f}/{vram_total:5.0f} MB ({vram_percent:5.1f}%)"
                                line += f" | GPU: {gpu_info['temperature']:3.0f}°C {gpu_info['load']:5.1f}%"
                        else:
                            line += " | VRAM: N/A"
                    except Exception as e:
                        line += f" | VRAM: ERROR ({str(e)[:20]})"

                # Écriture immédiate sur disque
                self.log_file.write(line + "\n")
                self.log_file.flush()  # CRITIQUE: force écriture même en cas de crash

                self.log_count += 1

                # Mise à jour compteur dans UI
                self.root.after(0, lambda: self.count_label.config(
                    text=f"✓ {self.log_count} mesures enregistrées"))

                interval = float(self.interval_var.get())
                time.sleep(interval)

            except Exception as e:
                error_msg = f"\n[ERREUR] {datetime.now().strftime('%H:%M:%S')} - {str(e)}\n"
                try:
                    self.log_file.write(error_msg)
                    self.log_file.flush()
                except:
                    pass
                print(f"Erreur logging: {e}")
                break

    def stop_monitoring(self):
        self.monitoring = False

        if self.log_file:
            # Résumé final
            self.log_file.write("\n" + "=" * 80 + "\n")
            self.log_file.write(f"FIN - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            self.log_file.write(f"Durée totale: {time.time() - self.start_time:.1f}s\n")
            self.log_file.write(f"Mesures enregistrées: {self.log_count}\n")
            self.log_file.write("=" * 80 + "\n")

            self.log_file.close()
            self.log_file = None

        self.start_button.config(state='normal')
        self.stop_button.config(state='disabled')
        self.log_label.config(text=f"✓ Fichier sauvegardé: {self.log_path.name}", foreground='blue')
        self.count_label.config(text="")


def main():
    root = tk.Tk()
    app = MemoryMonitor(root)
    root.mainloop()


if __name__ == "__main__":
    main()
