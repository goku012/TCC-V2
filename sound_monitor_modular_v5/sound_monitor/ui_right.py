import tkinter as tk
import customtkinter as ctk
from .constants import (
    DISCORD_SURFACE, DISCORD_SURFACE_ALT, DISCORD_ACCENT,
    DISCORD_SUCCESS
)
from .gauge import Gauge

def build_right_panel(app):
    app.right_frame = ctk.CTkFrame(app, corner_radius=10, fg_color=DISCORD_SURFACE)
    app.right_frame.pack(side="right", fill="both", expand=True, padx=8, pady=8)

    ctk.CTkLabel(app.right_frame, text="Status de Exposição", font=("Segoe UI", 26, "bold")).pack(pady=8)

    status_frame = ctk.CTkFrame(app.right_frame, fg_color=DISCORD_SURFACE)
    status_frame.pack(fill="both", expand=True, padx=20, pady=10)

    gauge_frame = ctk.CTkFrame(status_frame, fg_color=DISCORD_SURFACE)
    gauge_frame.pack(side="left", fill="both", expand=True)
    app.gauge = Gauge(gauge_frame, size=220, min_db=app.cfg["min_db"], max_db=app.cfg["max_db"])
    app.gauge.pack(pady=10)

    info_frame = ctk.CTkFrame(status_frame, fg_color=DISCORD_SURFACE)
    info_frame.pack(side="right", fill="both", expand=True, padx=20, pady=10)

    app.zone_text_label = tk.Label(info_frame, text="Zona", font=("Segoe UI", 12, "bold"),
                                   bg=DISCORD_SURFACE, fg="white")
    app.zone_text_label.pack(pady=(0, 0))

    app.zone_canvas = tk.Canvas(info_frame, width=160, height=64, bg=DISCORD_SURFACE, highlightthickness=0)
    app.zone_canvas.pack(pady=(0, 0), expand=True)

    def draw_zone_badge(text, color):
        app.zone_canvas.delete("all")
        r = 16; x1, y1, x2, y2 = 0, 0, 160, 64
        app.zone_canvas.create_arc(x1, y1, x1 + 2*r, y1 + 2*r, start=90, extent=90, fill=color, outline=color)
        app.zone_canvas.create_arc(x2 - 2*r, y1, x2, y1 + 2*r, start=0, extent=90, fill=color, outline=color)
        app.zone_canvas.create_arc(x1, y2 - 2*r, x1 + 2*r, y2, start=180, extent=90, fill=color, outline=color)
        app.zone_canvas.create_arc(x2 - 2*r, y2 - 2*r, x2, y2, start=270, extent=90, fill=color, outline=color)
        app.zone_canvas.create_rectangle(x1 + r, y1, x2 - r, y2, fill=color, outline=color)
        app.zone_canvas.create_rectangle(x1, y1 + r, x2, y2 - r, fill=color, outline=color)
        app.zone_canvas.create_text(80, 32, text=text, font=("Segoe UI", 18, "bold"), fill="white")
    app.draw_zone_badge = draw_zone_badge
    app.draw_zone_badge("SEGURA", DISCORD_SUCCESS)

    app.time_label = tk.Label(app.right_frame, text="Tempo permitido: --:--:-- | Tempo neste volume: --:--:--",
                              font=("Segoe UI", 14), bg=DISCORD_SURFACE, fg="white")
    app.time_label.pack(pady=(6, 0))

    app.remaining_label = tk.Label(app.right_frame, text="Tempo restante (neste volume) até 100%: --:--:--",
                                   font=("Segoe UI", 14), bg=DISCORD_SURFACE, fg="white")
    app.remaining_label.pack(pady=(2, 6))

    app.general_status = tk.Label(app.right_frame, text="Status: normal",
                                  font=("Segoe UI", 12, "bold"), bg=DISCORD_SURFACE, fg="#bbb")
    app.general_status.pack(pady=(0, 6))

    app.profile_label = tk.Label(app.right_frame, text=app._format_profile_text(),
                                 font=("Segoe UI", 11), bg=DISCORD_SURFACE, fg="#9aa0a6")
    app.profile_label.pack(pady=(0, 8))

    app.period_label = tk.Label(app.right_frame, text="Dose diária: 0%",
                                font=("Segoe UI", 12), bg=DISCORD_SURFACE, fg="#bbb")
    app.period_label.pack(pady=(0, 10))

    vol_frame = ctk.CTkFrame(app.right_frame, fg_color=DISCORD_SURFACE)
    vol_frame.pack(pady=10)
    tk.Label(vol_frame, text="🔊", font=("Segoe UI Emoji", 15), bg=DISCORD_SURFACE, fg="white").pack(side="left", padx=5)

    app.vol_slider = ctk.CTkSlider(vol_frame, from_=0, to=100, number_of_steps=100,
                                   command=app.on_vol_slider_change, width=520, height=28,
                                   progress_color=DISCORD_ACCENT)
    app.vol_slider.set(50)
    app.vol_slider.pack(side="left", padx=10)

    app.vol_label = tk.Label(vol_frame, text=f"{app._round_slider_label(50)}%", font=("Segoe UI", 10, "bold"),
                             bg=DISCORD_SURFACE, fg="white", width=5)
    app.vol_label.pack(side="left", padx=10)

    chart_frame = ctk.CTkFrame(app.right_frame, fg_color=DISCORD_SURFACE)
    chart_frame.pack(fill="x", padx=20, pady=(8, 0))
    app.chart_canvas = tk.Canvas(chart_frame, width=760, height=120, bg=DISCORD_SURFACE_ALT, highlightthickness=0)
    app.chart_canvas.pack()
    app.chart_canvas.bind("<Configure>", lambda e: app._on_ui(app._draw_history_chart))

    btn_frame = ctk.CTkFrame(app.right_frame, fg_color=DISCORD_SURFACE)
    btn_frame.pack(side="bottom", pady=18)

    app.btn_reset = ctk.CTkButton(btn_frame, text="Resetar sessão",
                                  width=120, height=56, fg_color="#444",
                                  font=("Segoe UI", 14, "bold"),
                                  command=app.reset_session)
    app.btn_reset.pack(side="left", padx=10, pady=10)

    app.btn_excel = ctk.CTkButton(btn_frame, text="Salvar Relatório (Excel)",
                                  width=180, height=56, fg_color="#0078D7",
                                  font=("Segoe UI", 14, "bold"),
                                  command=app.save_report)
    app.btn_excel.pack(side="left", padx=10, pady=10)

    app.btn_cfg = ctk.CTkButton(btn_frame, text="Configurações",
                                width=120, height=56, fg_color=DISCORD_ACCENT,
                                font=("Segoe UI", 14, "bold"),
                                command=app._open_settings_modal)
    app.btn_cfg.pack(side="left", padx=10, pady=10)

    app.pause_btn = ctk.CTkButton(btn_frame, text="Pausar",
                                  width=150, height=56, fg_color="#6b7280",
                                  font=("Segoe UI", 14, "bold"),
                                  command=app._toggle_pause)
    app.pause_btn.pack(side="left", padx=10, pady=10)
