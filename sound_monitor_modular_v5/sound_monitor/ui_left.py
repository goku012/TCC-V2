import customtkinter as ctk
from .constants import DISCORD_ACCENT, DISCORD_SURFACE

def build_left_panel(app):
    app.left_frame = ctk.CTkFrame(app, width=200, corner_radius=10, fg_color=DISCORD_SURFACE)
    app.left_frame.pack(side="left", fill="y", padx=8, pady=8)

    ctk.CTkLabel(app.left_frame, text="🎧", font=("Segoe UI", 64)).pack(pady=(10, 0))

    app.btn_prefixado = ctk.CTkButton(app.left_frame, text="Prefixado (ajuste imediato)",
                                      width=200, fg_color=DISCORD_ACCENT,
                                      command=lambda: app.set_mode("prefixado"))
    app.btn_prefixado.pack(pady=(12, 6))

    app.btn_dinamico = ctk.CTkButton(app.left_frame, text="Dinâmico (auto-limitando)",
                                     width=200, fg_color="#444",
                                     command=lambda: app.set_mode("dinamico"))
    app.btn_dinamico.pack(pady=6)

    app.mode_info = ctk.CTkLabel(app.left_frame, text="—", text_color="#bbb",
                                 wraplength=180, justify="left")
    app.mode_info.pack(pady=(8, 4))

    ctk.CTkLabel(app.left_frame, text="Dev: Breno Landim", font=("Segoe UI", 12),
                 text_color="#aaa").pack(side="bottom", pady=10)
