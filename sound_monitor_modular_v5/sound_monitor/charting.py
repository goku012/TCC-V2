def draw_history_chart(canvas, chart_points, cfg, chart_window_sec=120):
    w = int(canvas.winfo_width() or 760)
    h = int(canvas.winfo_height() or 120)
    pad_l, pad_r, pad_t, pad_b = 40, 10, 10, 25
    canvas.delete("all")
    canvas.create_line(pad_l, h - pad_b, w - pad_r, h - pad_b, fill="#555")
    canvas.create_line(pad_l, pad_t, pad_l, h - pad_b, fill="#555")
    if not chart_points:
        canvas.create_text(w//2, h//2, text="Sem dados ainda", fill="#888", font=("Segoe UI", 10))
        return
    t_now = chart_points[-1][0]
    t_min = max(0.0, t_now - chart_window_sec)
    t_max = t_now
    span = max(1e-6, t_max - t_min)
    min_db = cfg["min_db"]; max_db = cfg["max_db"]
    def x_map(t): return pad_l + (w - pad_l - pad_r) * ((t - t_min) / span)
    def y_map_db(L):
        ratio = (L - min_db) / max(1e-9, (max_db - min_db))
        ratio = max(0.0, min(1.0, ratio))
        return (h - pad_b) - (h - pad_b - pad_t) * ratio
    def y_map_dose(d):
        ratio = max(0.0, min(1.0, float(d)))
        return (h - pad_b) - (h - pad_b - pad_t) * ratio
    last_x_db = last_y_db = last_x_ds = last_y_ds = None
    for (t_rel, L, dose) in chart_points:
        if t_rel < t_min: continue
        x = x_map(t_rel); y_db = y_map_db(L); y_ds = y_map_dose(dose)
        if last_x_db is not None:
            canvas.create_line(last_x_db, last_y_db, x, y_db, fill="#8FD14F", width=2)
        last_x_db, last_y_db = x, y_db
        if last_x_ds is not None:
            canvas.create_line(last_x_ds, last_y_ds, x, y_ds, fill="#4FC3F7", width=2)
        last_x_ds, last_y_ds = x, y_ds
    canvas.create_text(w - 140, pad_t + 12, text="dB", fill="#8FD14F", font=("Segoe UI", 10, "bold"))
    canvas.create_text(w - 90, pad_t + 12, text="Dose%", fill="#4FC3F7", font=("Segoe UI", 10, "bold"))
    for label, Lbl in [("min", min_db), ("ref", cfg["ref_db"]), ("max", max_db)]:
        y = y_map_db(Lbl)
        canvas.create_line(pad_l - 5, y, w - pad_r, y, fill="#333")
        canvas.create_text(pad_l - 28, y, text=f"{Lbl:.0f}", fill="#aaa", font=("Segoe UI", 9))
    for dt in range(0, int(chart_window_sec) + 1, 30):
        x = x_map(t_max - dt)
        canvas.create_line(x, h - pad_b, x, pad_t, fill="#333")
        canvas.create_text(x, h - pad_b + 12, text=f"-{dt}s", fill="#aaa", font=("Segoe UI", 9))
