import time, math, platform, json
import customtkinter as ctk
from pathlib import Path
from tkinter import messagebox, filedialog
from datetime import datetime
from queue import Queue, Empty

from .constants import (
    DISCORD_BG, DISCORD_SURFACE, DISCORD_ACCENT, DISCORD_ERROR
)
from .utils import db_to_percent, fmt_hms, round_pct_ui
from .audio import AudioBackend, VolumeEnforcer
from .persistence import load_settings, save_settings
from .ui_left import build_left_panel
from .ui_right import build_right_panel
from .settings_dialog import open_settings_modal
from .monitor import start_monitor_thread
from .reporting import has_openpyxl, make_workbook, compute_summary_stats
from .charting import draw_history_chart

class SoundMonitorApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Monitor de Exposição Sonora - TCC")
        self.geometry("980x740")
        self.minsize(860, 770)
        self.configure(fg_color=DISCORD_BG)

        # Config padrão (8h / 3dB)
        self._defaults_cfg = {
            "min_db": 40.0, "max_db": 95.0, "ref_db": 85.0,
            "base_time_sec": 8 * 3600.0, "exchange_rate_db": 3.0,
            "min_enforced_volume": 5.0, "default_volume": 30.0,
        }
        self.cfg = dict(self._defaults_cfg)

        # Preferências e estados
        self.hard_lock_enabled = True
        self.lock_on_autoadjust = True
        self.locked = False
        self.lock_target_pct = None
        self.lock_reason = ""
        self.mode = "prefixado"
        self.dynamic_strategy = "reserva"

        mynow = time.time()
        self.session_dose = 0.0
        self.prev_session_dose = 0.0
        self.time_at_current_level = 0.0
        self.daily_dose = 0.0
        self._day_key = datetime.now().strftime("%Y-%m-%d")
        self.alert_50_fired = False
        self.alert_100_fired = False
        self.daily_warn_fired = False
        self.daily_block_fired = False
        self._last_update = mynow
        import threading
        self._stop_event = threading.Event()

        self._last_L_for_timer = None
        self.timer_epsilon_db = 1.0
        self._last_vol_key = None

        self.history = []
        self.MAX_HISTORY = 50000
        self.session_start_ts = mynow
        self._last_hist_log = 0.0
        self._last_chart_draw = 0.0
        self.chart_window_sec = 120
        self.chart_points = []
        self._last_sys_sync = 0.0

        self._audio_backend = AudioBackend()
        self._audio_warned = False

        self._lock_enforcer = None
        import threading as _t
        self._lock_enforcer_stop = _t.Event()

        self._slider_updating = False
        self.paused = False

        # Parâmetros dinâmicos
        self.dynamic_reserve_min_sec = 600.0
        self.dynamic_reserve_max_sec = 1200.0
        self.dynamic_reserve_fraction = 0.10
        self.dynamic_step_small = 0.5
        self.dynamic_step_medium = 1.0
        self.dynamic_step_large = 2.0
        self.dynamic_hysteresis_sec = 90.0
        self.dynamic_adjust_interval = 0.6
        self.dynamic_limiting_active = False
        self.dynamic_decay_active = False
        self.last_dynamic_adjust_ts = 0.0
        self.dynamic_softlock_enabled = True
        self.dynamic_ceiling_pct = None
        self.dynamic_release_delay = 20.0
        self._dynamic_upper_ok_since = None

        self._volume_quantum = 2.0
        self._ema_remaining_sec = None
        self._ema_alpha = 0.25

        # UI
        build_left_panel(self)
        build_right_panel(self)

        self._vol_cache = float(self.vol_slider.get())
        self._ui_queue = Queue()
        self.after(20, self._ui_pump)

        # Carregar settings
        self._load_settings()

        # Monitor
        start_monitor_thread(self)

        # Sync inicial
        if self._audio_backend.available():
            try:
                sv = self._get_system_volume_percent()
                if abs(sv - float(self.vol_slider.get())) > 2.0:
                    self._safe_set_slider(sv)
                self.vol_label.configure(text=f"{round_pct_ui(self.vol_slider.get())}%")
                self._vol_cache = float(self.vol_slider.get())
            except Exception:
                pass

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # --- UI Dispatchers ---
    def _ui_pump(self):
        try:
            while True:
                func = self._ui_queue.get_nowait()
                try:
                    func()
                except Exception as e:
                    print("Erro ao executar função de UI:", e)
        except Exception:
            pass
        self.after(20, self._ui_pump)

    def _on_ui(self, func):
        self._ui_queue.put(func)

    # --- Helpers ---
    def _round_slider_label(self, v):
        return round_pct_ui(v)

    def _quantize_pct(self, pct: float) -> float:
        q = float(self._volume_quantum) if getattr(self, "_volume_quantum", None) else 1.0
        return max(0.0, min(100.0, round(float(pct) / q) * q))

    def _format_profile_text(self):
        hours = self.cfg["base_time_sec"] / 3600.0
        er_val = self.cfg["exchange_rate_db"]
        er = int(er_val) if float(er_val).is_integer() else er_val
        return f"Perfil diário: {self.cfg['ref_db']:.0f} dB / {hours:g}h ({er} dB)"

    def _refresh_profile_label(self):
        self.profile_label.config(text=self._format_profile_text())

    def _draw_history_chart(self):
        """Wrapper para redimensionamento do canvas de histórico."""
        try:
            draw_history_chart(self.chart_canvas, self.chart_points, self.cfg, self.chart_window_sec)
        except Exception as e:
            print("Erro ao redesenhar gráfico:", e)

    # --- Áudio ---
    def _get_system_volume_percent(self):
        if not self._audio_backend.available():
            raise RuntimeError("Sem backend de áudio")
        return float(self._audio_backend.get_percent())

    def _set_system_volume_percent(self, pct):
        if not self._audio_backend.available():
            raise RuntimeError("Sem backend de áudio")
        self._audio_backend.set_percent(pct)

    # --- Persistência ---
    def _settings_payload(self):
        return {
            "mode": self.mode,
            "volume": float(self._vol_cache),
            "cfg": self.cfg,
            "hard_lock_enabled": self.hard_lock_enabled,
            "lock_on_autoadjust": self.lock_on_autoadjust,
            "dynamic_strategy": self.dynamic_strategy,
            "dynamic_softlock_enabled": self.dynamic_softlock_enabled,
        }

    def _load_settings(self):
        try:
            data = load_settings(self._defaults_cfg)
            if isinstance(data.get("cfg"), dict):
                for k, v in self._defaults_cfg.items():
                    self.cfg[k] = data["cfg"].get(k, v)
            self.hard_lock_enabled = bool(data.get("hard_lock_enabled", True))
            self.lock_on_autoadjust = bool(data.get("lock_on_autoadjust", True))
            self.dynamic_softlock_enabled = bool(data.get("dynamic_softlock_enabled", True))
            self.dynamic_strategy = data.get("dynamic_strategy", "reserva")
            if self.dynamic_strategy not in ("reserva", "zona_segura"):
                self.dynamic_strategy = "reserva"
            mode = data.get("mode")
            if mode in ("prefixado", "dinamico"):
                self.set_mode(mode, silent=True)
            vol = float(data.get("volume", self.cfg["default_volume"]))
            self._safe_set_slider(vol)
            self.vol_label.configure(text=f"{round_pct_ui(vol)}%")
            self._vol_cache = vol
        except Exception as e:
            print("Falha ao carregar settings:", e)
        finally:
            self._refresh_profile_label()
            self.gauge.set_bounds(self.cfg["min_db"], self.cfg["max_db"])

    def _save_settings(self):
        try:
            save_settings(self._settings_payload())
        except Exception as e:
            print("Falha ao salvar settings:", e)

    # --- Bloqueio ---
    def _lock_volume(self, target_pct: float, reason: str = ""):
        self.locked = True
        self.lock_target_pct = max(self.cfg["min_enforced_volume"], float(target_pct))
        self.lock_reason = reason
        self.vol_slider.configure(state="disabled")
        self.btn_dinamico.configure(state="disabled")
        self.btn_prefixado.configure(state="disabled")
        self.pause_btn.configure(state="disabled")
        self._safe_set_slider(self.lock_target_pct)
        self._apply_system_volume_from_slider(show_install_hint=True)
        self.general_status.config(text=f"Status: bloqueado ({reason})", fg=DISCORD_ERROR)
        self._start_lock_enforcer()

    def _unlock_volume(self):
        self.locked = False
        self.lock_target_pct = None
        self.lock_reason = ""
        self._stop_lock_enforcer()
        self.vol_slider.configure(state="normal")
        self.btn_dinamico.configure(state="normal")
        self.btn_prefixado.configure(state="normal")
        self.pause_btn.configure(state="normal")
        self.general_status.config(text="Status: normal", fg="#bbb")

    def _start_lock_enforcer(self):
        if self._lock_enforcer and self._lock_enforcer.is_alive():
            return
        self._lock_enforcer_stop.clear()
        self._lock_enforcer = VolumeEnforcer(
            self._audio_backend,
            target_fn=lambda: self.lock_target_pct if self.lock_target_pct is not None else self._vol_cache,
            stop_event=self._lock_enforcer_stop,
            interval=0.07,
        )
        self._lock_enforcer.start()

    def _stop_lock_enforcer(self):
        self._lock_enforcer_stop.set()

    # --- Modo ---
    def set_mode(self, mode, silent=False):
        if mode not in ("prefixado", "dinamico"):
            return
        self.mode = mode
        self.time_at_current_level = 0.0
        self._last_L_for_timer = None
        self._last_vol_key = None
        self.dynamic_limiting_active = False
        self.dynamic_decay_active = False
        self.last_dynamic_adjust_ts = 0.0
        self.dynamic_ceiling_pct = None
        self._dynamic_upper_ok_since = None
        def set_btn_colors(p="#444", d="#444"):
            self.btn_prefixado.configure(fg_color=p)
            self.btn_dinamico.configure(fg_color=d)
        if mode == "prefixado":
            set_btn_colors(p=DISCORD_ACCENT)
            self.mode_info.configure(text="Passou do limite? Ajuste imediato para o volume seguro (mantém ≥10 min de folga)." )
        else:
            set_btn_colors(d=DISCORD_ACCENT)
            self.mode_info.configure(text="Dinâmico (Reserva/Zona Segura): reduz suavemente até manter folga ou entrar no verde.")
        if not silent:
            self.general_status.config(text="Status: normal", fg="#bbb")
        self._refresh_profile_label()

    # --- Slider ---
    def on_vol_slider_change(self, value):
        if self.locked:
            self._safe_set_slider(self.lock_target_pct)
            self._apply_system_volume_from_slider(show_install_hint=False)
            return
        if getattr(self, "_slider_updating", False):
            return
        v = self._quantize_pct(float(value))
        if self.dynamic_decay_active and v > self._vol_cache + 0.01:
            self._safe_set_slider(self._vol_cache)
            return
        if self.dynamic_softlock_enabled and self.dynamic_ceiling_pct is not None and v > self.dynamic_ceiling_pct + 0.01:
            self._safe_set_slider(self.dynamic_ceiling_pct)
            self._apply_system_volume_from_slider(show_install_hint=False)
            return
        if self.mode == "prefixado":
            cap = self._calc_prefix_volume_cap_pct(self.session_dose)
            if cap is not None and v > cap + 0.1:
                safe_v = max(self.cfg["min_enforced_volume"], cap)
                self._safe_set_slider(safe_v)
                self._vol_cache = safe_v
                self._apply_system_volume_from_slider(show_install_hint=True)
                self.general_status.config(text="Status: ajustado p/ seguro", fg="#F0B232")
                if self.hard_lock_enabled and self.lock_on_autoadjust:
                    self._lock_volume(safe_v, reason="ajuste de segurança")
                self.vol_label.configure(text=f"{round_pct_ui(safe_v)}%")
                return
        self._vol_cache = v
        self.vol_label.configure(text=f"{round_pct_ui(v)}%")
        self._apply_system_volume_from_slider(show_install_hint=True)

    # --- Ações UI ---
    def _toggle_pause(self):
        self.paused = not self.paused
        if self.paused:
            self.general_status.config(text="Status: pausado", fg="#F0B232")
            self.pause_btn.configure(text="Retomar")
        else:
            self.general_status.config(text="Status: normal", fg="#bbb")
            self.pause_btn.configure(text="Pausar")

    def reset_session(self):
        self.session_dose = 0.0
        self.prev_session_dose = 0.0
        self.alert_50_fired = False
        self.alert_100_fired = False
        self.time_at_current_level = 0.0
        self.session_start_ts = time.time()
        self.history = []
        self.chart_points = []
        self._last_hist_log = 0.0
        self._last_chart_draw = 0.0
        self._last_update = time.time()
        self._last_L_for_timer = None
        self._last_vol_key = None
        self.dynamic_limiting_active = False
        self.dynamic_decay_active = False
        self.last_dynamic_adjust_ts = 0.0
        self.dynamic_ceiling_pct = None
        self._dynamic_upper_ok_since = None
        self.general_status.config(text="Status: normal", fg="#bbb")
        self._on_ui(lambda: self.remaining_label.config(text="Tempo restante (neste volume) até 100%: --:--:--"))
        self._unlock_volume()
        messagebox.showinfo("Sessão reiniciada", "Dose e histórico foram resetados.")

    # --- Relatório ---
    def save_report(self):
        if not has_openpyxl():
            messagebox.showerror("Dependência ausente", "Para exportar Excel (.xlsx): pip install openpyxl")
            return
        if not self.history and not messagebox.askyesno("Sem dados", "Ainda não há histórico. Salvar mesmo assim?"):
            return
        filename = filedialog.asksaveasfilename(
            title="Salvar relatório Excel",
            defaultextension=".xlsx",
            filetypes=[("Pasta de trabalho do Excel", "*.xlsx")],
            initialfile=f"relatorio_som_{time.strftime('%Y%m%d_%H%M%S')}.xlsx"
        )
        if not filename:
            return
        try:
            wb = make_workbook(self.history, self.cfg)
            wb.save(filename)
            messagebox.showinfo("Relatório salvo", f"Relatório Excel exportado em:\n{filename}")
        except Exception as e:
            messagebox.showerror("Erro ao salvar", f"Ocorreu um erro ao salvar o Excel:\n{e}")

    # --- Cálculo do teto (prefixado) ---
    def _calc_prefix_volume_cap_pct(self, dose):
        base = self.cfg["base_time_sec"]
        ref = self.cfg["ref_db"]
        er = float(self.cfg.get("exchange_rate_db", 3.0))
        target = 10 * 60
        if (1.0 - dose) * base >= target:
            return None
        arg = max(1e-9, ((1.0 - dose) * base) / target)
        Lmax = ref + er * math.log(arg, 2)
        vol_cap = db_to_percent(Lmax, self.cfg)
        if vol_cap >= 100.0:
            return None
        if vol_cap <= 0.0:
            return 0.0
        return vol_cap

    # --- SO volume sync ---
    def _apply_system_volume_from_slider(self, show_install_hint=False):
        if self._audio_backend.available():
            try:
                target = self._quantize_pct(self._vol_cache)
                self._set_system_volume_percent(target)
                sys_pct = self._quantize_pct(self._get_system_volume_percent())
                if abs(sys_pct - target) > 0.5:
                    self._vol_cache = sys_pct
                    disp = round_pct_ui(sys_pct)
                    self._on_ui(lambda v=sys_pct: self._safe_set_slider(v))
                    self._on_ui(lambda t=disp: self.vol_label.configure(text=f"{t}%"))
                return
            except Exception:
                pass
        if platform.system() == "Windows" and show_install_hint and not self._audio_warned:
            self._audio_warned = True
            messagebox.showinfo(
                "Controlar volume do Windows",
                "Para o slider controlar (e travar) o volume do PC, instale: pip install pycaw comtypes"
            )

    # --- Settings modal ---
    def _open_settings_modal(self):
        open_settings_modal(self)

    # --- Close ---
    def _on_close(self):
        self._stop_event.set()
        try:
            self._save_settings()
        except Exception:
            pass
        try:
            self._stop_lock_enforcer()
        except Exception:
            pass
        self.destroy()
