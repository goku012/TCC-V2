import json
from pathlib import Path

def settings_path() -> Path:
    base = Path.home() / ".tcc_sound_monitor"
    base.mkdir(parents=True, exist_ok=True)
    return base / "settings.json"

def load_settings(defaults: dict) -> dict:
    cfg = dict(defaults)
    p = settings_path()
    if p.exists():
        try:
            with open(p, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            return data
        except Exception:
            return {"cfg": cfg}
    return {"cfg": cfg}

def save_settings(data: dict):
    p = settings_path()
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
