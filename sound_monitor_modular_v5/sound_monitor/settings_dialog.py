import tkinter as tk
import customtkinter as ctk
from tkinter import messagebox
from .constants import DISCORD_SURFACE, DISCORD_SURFACE_ALT, DISCORD_ACCENT
from .utils import allowed_time_seconds_for_level, round_pct_ui, map_percent_to_db

def open_settings_modal(app):
    def _cfg_preview_text(tmp_cfg):
        t85 = allowed_time_seconds_for_level(85, tmp_cfg)
        t90 = allowed_time_seconds_for_level(90, tmp_cfg)
        def pretty(sec):
            s = int(max(0, sec)); h = s // 3600; m = (s % 3600) // 60
            if h > 0: return f"{h}h {m}min"
            return f"{m}min"
        return (f"Exemplo prático (base diária 8h):\n"
                f"• A 85 dB: ~{pretty(t85)} até atingir 100% da dose diária.\n"
                f"• A 90 dB: ~{pretty(t90)} até atingir 100% da dose diária.\n"
                f"O modo Prefixado mantém uma folga mínima antes de ajustar o volume.")

    def _make_tmp_cfg(ref_db=None, er=None, min_vol=None, def_vol=None):
        tmp = dict(app.cfg)
        if ref_db is not None: tmp["ref_db"] = float(ref_db)
        if er is not None:     tmp["exchange_rate_db"] = float(er)
        tmp["base_time_sec"] = 8 * 3600.0
        if min_vol is not None: tmp["min_enforced_volume"] = float(min_vol)
        if def_vol is not None: tmp["default_volume"] = float(def_vol)
        return tmp

    PROFILES = {
        "NIOSH (85 dB / 8h, 3 dB)": {"ref_db": 85.0, "er": 3.0, "desc": "Padrão ocupacional: 85 dB por 8h, troca 3 dB."},
        "OMS (80 dB / 8h, 3 dB)": {"ref_db": 80.0, "er": 3.0, "desc": "Mais protetivo: 80 dB por 8h, troca 3 dB."},
        "Personalizado (manter atual)": {"ref_db": None, "er": None, "desc": "Mantém valores atuais de referência e troca. Base diária é sempre 8h."},
    }

    top = ctk.CTkToplevel(app)
    top.title("Configurações")
    top.geometry("700x720")
    top.attributes("-topmost", True)

    tab = ctk.CTkTabview(top, width=660, height=590)
    tab.pack(fill="both", expand=True, padx=16, pady=16)
    basic = tab.add("Básico")
    adv = tab.add("Avançado")

    basic_wrap = ctk.CTkFrame(basic, fg_color=DISCORD_SURFACE)
    basic_wrap.pack(fill="both", expand=True, padx=6, pady=6)

    ctk.CTkLabel(basic_wrap, text="Nível de proteção (perfil diário):", anchor="w").pack(fill="x", pady=(8,4))
    profile_names = list(PROFILES.keys())

    cur_ref = round(float(app.cfg["ref_db"]), 1)
    cur_er  = round(float(app.cfg["exchange_rate_db"]), 1)
    current_profile = "Personalizado (manter atual)"
    if abs(cur_ref - 85.0) < 0.6 and abs(cur_er - 3.0) < 0.6:
        current_profile = "NIOSH (85 dB / 8h, 3 dB)"
    elif abs(cur_ref - 80.0) < 0.6 and abs(cur_er - 3.0) < 0.6:
        current_profile = "OMS (80 dB / 8h, 3 dB)"

    var_profile = tk.StringVar(value=current_profile)
    opt_profile = ctk.CTkOptionMenu(basic_wrap, values=profile_names, variable=var_profile)
    opt_profile.pack(fill="x", pady=(0,6))

    lbl_profile_desc = ctk.CTkLabel(basic_wrap, text=PROFILES[current_profile]["desc"],
                                    text_color="#B5BAC1", justify="left", wraplength=600)
    lbl_profile_desc.pack(fill="x", pady=(0,10))

    ctk.CTkLabel(basic_wrap, text="Estratégia do Dinâmico:", anchor="w").pack(fill="x", pady=(6,4))
    dyn_names = ["Reserva de tempo (10–20 min)", "Reduzir até Zona Segura"]
    dyn_map_name_to_key = {"Reserva de tempo (10–20 min)": "reserva", "Reduzir até Zona Segura": "zona_segura"}
    dyn_map_key_to_name = {v: k for k, v in dyn_map_name_to_key.items()}
    var_dyn = tk.StringVar(value=dyn_map_key_to_name.get(app.dynamic_strategy, dyn_names[0]))
    ctk.CTkOptionMenu(basic_wrap, values=dyn_names, variable=var_dyn).pack(fill="x", pady=(0,6))
    ctk.CTkLabel(basic_wrap,
        text=("• Reserva: mantém uma folga alvo e reduz suave quando precisa.\n"
              "• Zona Segura: baixa o volume gradualmente até o ponteiro ficar no verde."),
        text_color="#B5BAC1", justify="left", wraplength=600).pack(fill="x", pady=(0,10))

    def _mk_slider_row(parent, title, init_val, on_change, max_to=60):
        row = ctk.CTkFrame(parent, fg_color=DISCORD_SURFACE)
        row.pack(fill="x", pady=6)
        ctk.CTkLabel(row, text=title, anchor="w").pack(side="left", padx=(0, 8))
        init_val = max(0.0, min(float(init_val), float(max_to)))
        val_lbl = ctk.CTkLabel(row, text=f"{int(round(init_val))}%", width=48, anchor="e")
        val_lbl.pack(side="right")
        sld = ctk.CTkSlider(
            row, from_=0, to=max_to, number_of_steps=int(max_to), width=380,
            command=lambda v:(val_lbl.configure(text=f"{int(float(v))}%"), on_change(float(v))))
        sld.set(init_val); sld.pack(fill="x", padx=(0,56))
        return sld, val_lbl

    tmp_min = [app.cfg["min_enforced_volume"]]
    tmp_def = [app.cfg["default_volume"]]
    ctk.CTkLabel(basic_wrap, text="Volumes:", anchor="w").pack(fill="x", pady=(8,0))
    sld_def,_ = _mk_slider_row(basic_wrap, "Volume inicial ao abrir o app",
                               float(app.cfg["default_volume"]),
                               lambda v: tmp_def.__setitem__(0, v), max_to=60)
    sld_min,_ = _mk_slider_row(basic_wrap, "Volume mínimo imposto em bloqueios",
                               float(app.cfg["min_enforced_volume"]),
                               lambda v: tmp_min.__setitem__(0, v), max_to=60)

    var_dyn_softlock = tk.BooleanVar(value=app.dynamic_softlock_enabled)
    ctk.CTkCheckBox(
        basic_wrap,
        text="Travar aumentos enquanto o Dinâmico reduz (soft-lock)",
        variable=var_dyn_softlock
    ).pack(anchor="w", pady=4)

    preview_box = ctk.CTkFrame(basic_wrap, fg_color=DISCORD_SURFACE_ALT, corner_radius=8)
    preview_box.pack(fill="x", pady=(8,4))
    lbl_preview = ctk.CTkLabel(preview_box, text=_cfg_preview_text(app.cfg), justify="left", wraplength=600)
    lbl_preview.pack(padx=12, pady=10)

    def _refresh_preview_for_profile(name):
        p = PROFILES.get(name, PROFILES["Personalizado (manter atual)"])
        if p["ref_db"] is None:
            tmp = _make_tmp_cfg(min_vol=tmp_min[0], def_vol=tmp_def[0])
        else:
            tmp = _make_tmp_cfg(ref_db=p["ref_db"], er=p["er"], min_vol=tmp_min[0], def_vol=tmp_def[0])
        lbl_profile_desc.configure(text=p["desc"])
        lbl_preview.configure(text=_cfg_preview_text(tmp))
    opt_profile.configure(command=_refresh_preview_for_profile)

    adv_wrap = ctk.CTkFrame(adv, fg_color=DISCORD_SURFACE)
    adv_wrap.pack(fill="both", expand=True, padx=6, pady=6)

    ctk.CTkLabel(adv_wrap, text="(Avançado) Ajustes técnicos", text_color="#B5BAC1").pack(anchor="w", pady=(0,8))

    def add_row(parent, label, initial, placeholder="", width=140):
        row = ctk.CTkFrame(parent, fg_color=DISCORD_SURFACE)
        row.pack(fill="x", pady=6)
        ctk.CTkLabel(row, text=label, width=320, anchor="w").pack(side="left")
        entry = ctk.CTkEntry(row, width=width, placeholder_text=placeholder)
        entry.pack(side="right"); entry.insert(0, str(initial))
        return entry

    e_min_db = add_row(adv_wrap, "Mínimo dB (escala do gauge):", app.cfg["min_db"])
    e_max_db = add_row(adv_wrap, "Máximo dB (escala do gauge):", app.cfg["max_db"])
    e_ref_db = add_row(adv_wrap, "Nível de referência (dB):", app.cfg["ref_db"])
    e_er     = add_row(adv_wrap, "Taxa de troca (dB) [3]:", app.cfg["exchange_rate_db"])

    btns = ctk.CTkFrame(top, fg_color=DISCORD_SURFACE); btns.pack(fill="x", pady=(0,12), padx=16)

    def apply_all():
        try:
            chosen = var_profile.get()
            if chosen != "Personalizado (manter atual)":
                p = PROFILES[chosen]
                ref_db = float(p["ref_db"]); er = float(p["er"])
            else:
                ref_db = float(e_ref_db.get()); er = float(e_er.get())

            min_db = float(e_min_db.get()); max_db = float(e_max_db.get())
            if max_db - min_db < 10.0: raise ValueError("Max dB deve ser ≥10 acima do Min dB.")
            if er <= 0: raise ValueError("Taxa de troca (dB) deve ser > 0.")

            min_vol = float(tmp_min[0]); def_vol = float(tmp_def[0])
            for v in (min_vol, def_vol):
                if not (0.0 <= v <= 100.0):
                    raise ValueError("Volumes devem estar entre 0 e 100%.")

            dyn_key = {"Reserva de tempo (10–20 min)": "reserva", "Reduzir até Zona Segura": "zona_segura"}[var_dyn.get()]

            app.cfg.update({
                "min_db": min_db,
                "max_db": max_db,
                "ref_db": ref_db,
                "base_time_sec": 8 * 3600.0,
                "exchange_rate_db": er,
                "min_enforced_volume": min_vol,
                "default_volume": def_vol,
            })
            app.dynamic_softlock_enabled = bool(var_dyn_softlock.get())
            app.dynamic_strategy = dyn_key

            app._refresh_profile_label()
            app.gauge.set_bounds(app.cfg["min_db"], app.cfg["max_db"])
            L_eff = map_percent_to_db(app._vol_cache, app.cfg)
            app.gauge.set_value(L_eff, app.session_dose)
            app.vol_label.configure(text=f"{round_pct_ui(app._vol_cache)}%")
            app.set_mode(app.mode, silent=True)
            app._save_settings()

            _refresh_preview_for_profile(var_profile.get())
            messagebox.showinfo("Configurações", "Configurações aplicadas e salvas.")
        except Exception as ex:
            messagebox.showerror("Configurações", f"Erro: {ex}")

    def restore_defaults():
        var_profile.set("NIOSH (85 dB / 8h, 3 dB)")
        var_dyn.set("Reserva de tempo (10–20 min)")
        var_dyn_softlock.set(True)
        sld_def.set(app._defaults_cfg["default_volume"])
        sld_min.set(app._defaults_cfg["min_enforced_volume"])
        e_min_db.delete(0, tk.END); e_min_db.insert(0, str(app._defaults_cfg["min_db"]))
        e_max_db.delete(0, tk.END); e_max_db.insert(0, str(app._defaults_cfg["max_db"]))
        e_ref_db.delete(0, tk.END); e_ref_db.insert(0, "85")
        e_er.delete(0, tk.END); e_er.insert(0, "3")
        _refresh_preview_for_profile("NIOSH (85 dB / 8h, 3 dB)")
        messagebox.showinfo("Configurações", "Padrões restaurados (não esqueça de clicar em Aplicar).")

    ctk.CTkButton(btns, text="Aplicar", fg_color=DISCORD_ACCENT, width=120, command=apply_all).pack(side="left", padx=6)
    ctk.CTkButton(btns, text="Restaurar padrões", fg_color="#6b7280", width=160, command=restore_defaults).pack(side="left", padx=6)
    ctk.CTkButton(btns, text="Fechar", fg_color="#444", width=120, command=top.destroy).pack(side="right", padx=6)
