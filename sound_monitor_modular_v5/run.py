# Inicializador simples: python run.py
import sys, pathlib
ROOT = pathlib.Path(__file__).parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
import customtkinter as ctk
from sound_monitor.app import SoundMonitorApp

if __name__ == "__main__":
    ctk.set_appearance_mode("dark")
    app = SoundMonitorApp()
    app.mainloop()
