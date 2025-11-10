import time
from datetime import datetime
from tkinter import messagebox
from .utils import (
    map_percent_to_db, dose_increment_per_second, allowed_time_seconds_for_level,
    risk_zone_from_dose, risk_zone_from_level, fmt_hms, round_pct_ui
)
from .constants import DISCORD_SUCCESS, DISCORD_WARN, DISCORD_ERROR
from .charting import draw_history_chart
from .com_guard import ComGuard

def start_monitor_thread(app):
    import threading
    t = threading.Thread(target=lambda: _monitor_loop(app), daemon=True)
    t.start()

def _monitor_loop(app):
    with ComGuard():
        while not app._stop_event.is_set():
            try:
                if app.locked:
                    if abs(float(app._vol_cache) - float(app.lock_target_pct or 0)) > 0.1:
                        app._on_ui(lambda: app._safe_set_slider(app.lock_target_pct))
                    app._apply_system_volume_from_slider(show_install_hint=False)

                vol_percent = float(app._vol_cache)
                now = time.time()
                dt = now - app._last_update
                dt = max(0.0, min(dt, 1.0))
                app._last_update = now

                now_dt = datetime.now()
                _roll_day_if_needed(app, now_dt)

                L_eff = map_percent_to_db(vol_percent, app.cfg)

                if app.paused:
                    app._on_ui(lambda: app.gauge.set_value(L_eff, app.session_dose))
                    app._on_ui(lambda: app.general_status.config(text="Status: pausado", fg=DISCORD_WARN))
                    app._apply_system_volume_from_slider(show_install_hint=False)
                    time.sleep(0.1 if app.locked else 0.2)
                    continue

                vol_key = int(round_pct_ui(app._vol_cache))
                if app._last_L_for_timer is None:
                    app._last_L_for_timer = L_eff
                    app._last_vol_key = vol_key
                else:
                    changed_db = abs(L_eff - app._last_L_for_timer) >= app.timer_epsilon_db
                    changed_pct = (app._last_vol_key is None) or (app._last_vol_key != vol_key)
                    if changed_db or changed_pct:
                        app._last_L_for_timer = L_eff
                        app._last_vol_key = vol_key
                        app.time_at_current_level = 0.0

                app.prev_session_dose = app.session_dose
                inc = dose_increment_per_second(L_eff, app.cfg) * dt
                app.session_dose = min(1.0, app.session_dose + inc)
                app.daily_dose = min(10.0, app.daily_dose + inc)

                if app.session_dose < 1.0:
                    app.time_at_current_level += dt
                else:
                    if not app.locked and app.hard_lock_enabled:
                        app._on_ui(lambda: app._lock_volume(app.cfg["min_enforced_volume"], reason="limite diário"))
                    app.time_at_current_level = 0.0

                allowed_sec = allowed_time_seconds_for_level(L_eff, app.cfg)
                time_str = fmt_hms(allowed_sec)
                time_cur_str = fmt_hms(app.time_at_current_level)
                remaining_sec = (1.0 - app.session_dose) * allowed_sec if app.session_dose < 1.0 else 0.0

                if app._ema_remaining_sec is None:
                    app._ema_remaining_sec = remaining_sec
                else:
                    a = app._ema_alpha
                    app._ema_remaining_sec = a * remaining_sec + (1 - a) * app._ema_remaining_sec
                ema_remaining = app._ema_remaining_sec
                remaining_str = fmt_hms(ema_remaining)

                zone = risk_zone_from_dose(app.session_dose)
                zone_color = DISCORD_SUCCESS if zone == "SEGURA" else DISCORD_WARN if zone == "ATENÇÃO" else DISCORD_ERROR
                level_zone = risk_zone_from_level(L_eff)

                # regras dos modos
                _apply_mode_rules(app, vol_percent, ema_remaining, allowed_sec, level_zone)

                # Alertas DIÁRIOS
                daily_pct = app.daily_dose * 100.0
                if daily_pct >= 80.0 and not app.daily_warn_fired and daily_pct < 100.0:
                    app.daily_warn_fired = True
                    app._on_ui(lambda: messagebox.showwarning("Atenção diária", "Dose diária ≥ 80%."))
                if 80.0 <= daily_pct < 100.0:
                    app._on_ui(lambda: app.period_label.config(fg=DISCORD_WARN))
                elif daily_pct >= 100.0:
                    app._on_ui(lambda: app.period_label.config(fg=DISCORD_ERROR))
                else:
                    app._on_ui(lambda: app.period_label.config(fg="#bbb"))

                if daily_pct >= 100.0 and not app.daily_block_fired:
                    app.daily_block_fired = True
                    app._on_ui(lambda: messagebox.showerror("Bloqueio diário", "Dose diária atingiu 100%. Volume mínimo imposto."))
                    if app.hard_lock_enabled:
                        app._on_ui(lambda: app._lock_volume(app.cfg["min_enforced_volume"], reason="limite diário"))

                if not app.alert_50_fired and app.session_dose >= 0.5:
                    app.alert_50_fired = True
                    app._on_ui(lambda: messagebox.showwarning("Atenção", "Você atingiu 50% da dose diária."))
                if not app.alert_100_fired and app.session_dose >= 1.0:
                    app.alert_100_fired = True
                    app._on_ui(lambda: messagebox.showerror("Risco crítico", "Limite de dose diária ultrapassado!"))
                    if app.hard_lock_enabled:
                        app._on_ui(lambda: app._lock_volume(app.cfg["min_enforced_volume"], reason="limite diário"))

                # Atualiza UI
                app._on_ui(lambda: app.gauge.set_value(L_eff, app.session_dose))
                app._on_ui(lambda: app.draw_zone_badge(zone, zone_color))
                app._on_ui(lambda: app.time_label.config(text=f"Tempo permitido: {time_str} | Tempo neste volume: {time_cur_str}"))
                app._on_ui(lambda: app.remaining_label.config(text=f"Tempo restante (neste volume) até 100%: {remaining_str}"))
                app._on_ui(lambda: app.vol_slider.configure(progress_color=zone_color))
                app._on_ui(lambda: app.vol_label.configure(text=f"{round_pct_ui(app._vol_cache)}%"))
                app._on_ui(lambda: app.period_label.config(text=f"Dose diária: {daily_pct:.0f}%"))

                if app._audio_backend.available() and (now - app._last_sys_sync) >= 0.5:
                    app._last_sys_sync = now
                    try:
                        sys_pct = app._quantize_pct(app._audio_backend.get_percent())
                        if app.dynamic_softlock_enabled and app.dynamic_ceiling_pct is not None:
                            if sys_pct > app.dynamic_ceiling_pct + 0.5:
                                app._on_ui(lambda: app._safe_set_slider(app.dynamic_ceiling_pct))
                                app._apply_system_volume_from_slider(show_install_hint=False)
                                sys_pct = app.dynamic_ceiling_pct

                        if app.locked:
                            if abs(sys_pct - float(app.lock_target_pct or 0)) > 0.5:
                                app._on_ui(lambda: app._safe_set_slider(app.lock_target_pct))
                                app._apply_system_volume_from_slider(show_install_hint=False)
                        else:
                            if app.dynamic_decay_active and sys_pct > float(app._vol_cache) + 0.01:
                                sys_pct = app._vol_cache
                            if abs(sys_pct - float(app._vol_cache)) > 1.0:
                                app._on_ui(lambda v=sys_pct: app._safe_set_slider(v))
                    except Exception:
                        pass

                # Histórico (~1s)
                if (now - app._last_hist_log) >= 1.0:
                    app._last_hist_log = now
                    t_rel = now - app.session_start_ts
                    app.history.append({
                        "ts_iso": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now)),
                        "t_session": t_rel,
                        "mode": app.mode,
                        "vol_percent": float(app._vol_cache),
                        "L": L_eff,
                        "dose": app.session_dose,
                        "zone": zone,
                        "daily": app.daily_dose,
                    })
                    if len(app.history) > app.MAX_HISTORY:
                        del app.history[:len(app.history) - app.MAX_HISTORY]
                    app.chart_points.append((t_rel, L_eff, app.session_dose))
                    cutoff = t_rel - app.chart_window_sec - 2
                    app.chart_points = [p for p in app.chart_points if p[0] >= cutoff]

                # Redesenha gráfico (~0.8s)
                if (now - app._last_chart_draw) >= 0.8:
                    app._last_chart_draw = now
                    app._on_ui(lambda: draw_history_chart(app.chart_canvas, app.chart_points, app.cfg, app.chart_window_sec))

            except Exception as ex:
                print("Erro no monitor:", ex)

            time.sleep(0.2)

def _roll_day_if_needed(app, now_dt):
    day_key = now_dt.strftime("%Y-%m-%d")
    if day_key != app._day_key:
        app._day_key = day_key
        app.daily_dose = 0.0
        app.daily_warn_fired = False
        app.daily_block_fired = False
        app.alert_50_fired = False
        app.alert_100_fired = False
        app.session_dose = 0.0
        app._on_ui(lambda: messagebox.showinfo("Novo dia", "Dose diária reiniciada."))

def _apply_mode_rules(app, vol_percent, ema_remaining, allowed_sec, level_zone):
    # prefixado
    if app.mode == "prefixado" and app.session_dose < 1.0 and not app.locked:
        cap = app._calc_prefix_volume_cap_pct(app.session_dose)
        if cap is not None and vol_percent > cap + 0.1:
            def _snap_to_safe():
                safe_v = max(app.cfg["min_enforced_volume"], cap)
                app._safe_set_slider(safe_v)
                app._vol_cache = safe_v
                app._apply_system_volume_from_slider(show_install_hint=True)
            app._on_ui(_snap_to_safe)
            app._on_ui(lambda: app.general_status.config(text="Status: ajustado p/ seguro", fg="#F0B232"))
            if app.hard_lock_enabled and app.lock_on_autoadjust:
                app._on_ui(lambda: app._lock_volume(max(app.cfg["min_enforced_volume"], cap), reason="ajuste de segurança"))
        else:
            app._on_ui(lambda: app.general_status.config(text="Status: normal", fg="#bbb"))

    # dinamico
    elif app.mode == "dinamico" and app.session_dose < 1.0 and not app.locked:
        now = time.time()
        if app.dynamic_strategy == "reserva":
            reserve_target = max(app.dynamic_reserve_min_sec, min(app.dynamic_reserve_max_sec, app.dynamic_reserve_fraction * allowed_sec))
            lower = reserve_target - app.dynamic_hysteresis_sec
            upper = reserve_target + app.dynamic_hysteresis_sec

            if not app.dynamic_limiting_active and ema_remaining < lower:
                app.dynamic_limiting_active = True
                if app.dynamic_softlock_enabled:
                    cur = app._quantize_pct(app._vol_cache)
                    app.dynamic_ceiling_pct = cur if app.dynamic_ceiling_pct is None else min(app.dynamic_ceiling_pct, cur)
                    app._dynamic_upper_ok_since = None
            elif app.dynamic_limiting_active and ema_remaining > upper:
                app.dynamic_limiting_active = False

            if app.dynamic_limiting_active:
                if (now - app.last_dynamic_adjust_ts) >= app.dynamic_adjust_interval:
                    deficit = reserve_target - ema_remaining
                    if deficit < 60: step = app.dynamic_step_small
                    elif deficit < 300: step = app.dynamic_step_medium
                    else: step = app.dynamic_step_large
                    def _decay():
                        current = app._vol_cache
                        target = app._quantize_pct(current - step)
                        if target < current - 0.099:
                            app.dynamic_decay_active = True
                            app._safe_set_slider(target)
                            if app.dynamic_softlock_enabled:
                                app.dynamic_ceiling_pct = target if app.dynamic_ceiling_pct is None else min(app.dynamic_ceiling_pct, target)
                    app._on_ui(_decay)
                    app.last_dynamic_adjust_ts = now
                app._on_ui(lambda: app.general_status.config(text="Status: auto-limitando", fg="#F0B232"))
            else:
                app.dynamic_decay_active = False
                if app.dynamic_softlock_enabled:
                    if ema_remaining > upper:
                        if app._dynamic_upper_ok_since is None:
                            app._dynamic_upper_ok_since = now
                        elif (now - app._dynamic_upper_ok_since) >= app.dynamic_release_delay:
                            app.dynamic_ceiling_pct = None
                    else:
                        app._dynamic_upper_ok_since = None
                app._on_ui(lambda: app.general_status.config(text="Status: normal", fg="#bbb"))

        else:
            if level_zone != "SEGURA":
                if not app.dynamic_limiting_active:
                    app.dynamic_limiting_active = True
                    if app.dynamic_softlock_enabled:
                        cur = app._quantize_pct(app._vol_cache)
                        app.dynamic_ceiling_pct = cur if app.dynamic_ceiling_pct is None else min(app.dynamic_ceiling_pct, cur)
                        app._dynamic_upper_ok_since = None
                if (now - app.last_dynamic_adjust_ts) >= app.dynamic_adjust_interval:
                    if app._last_L_for_timer is None or app._last_L_for_timer < 90: step = app.dynamic_step_small
                    else: step = app.dynamic_step_medium if app._last_L_for_timer < 95 else app.dynamic_step_large
                    def _decay2():
                        new_v = max(app.cfg["min_enforced_volume"], app._vol_cache - step)
                        if abs(new_v - app._vol_cache) >= 0.1:
                            app._safe_set_slider(new_v)
                            if app.dynamic_softlock_enabled:
                                app.dynamic_ceiling_pct = new_v if app.dynamic_ceiling_pct is None else min(app.dynamic_ceiling_pct, new_v)
                    app._on_ui(_decay2)
                    app.last_dynamic_adjust_ts = now
                app._on_ui(lambda: app.general_status.config(text="Status: auto-limitando (até zona segura)", fg="#F0B232"))
            else:
                app.dynamic_limiting_active = False
                app.dynamic_decay_active = False
                if app.dynamic_softlock_enabled:
                    if level_zone == "SEGURA":
                        if app._dynamic_upper_ok_since is None:
                            app._dynamic_upper_ok_since = now
                        elif (now - app._dynamic_upper_ok_since) >= app.dynamic_release_delay:
                            app.dynamic_ceiling_pct = None
                    else:
                        app._dynamic_upper_ok_since = None
                app._on_ui(lambda: app.general_status.config(text="Status: normal", fg="#bbb"))
