import customtkinter as ctk
# Permite rodar tanto como pacote (-m sound_monitor.main) quanto como script (python sound_monitor/main.py)
try:
    from .app import SoundMonitorApp  # quando executado como pacote
except ImportError:  # quando executado diretamente
    from sound_monitor.app import SoundMonitorApp  # fallback absoluto

if __name__ == "__main__":
    ctk.set_appearance_mode("dark")
    app = SoundMonitorApp()
    app.mainloop()
