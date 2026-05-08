import json
import os

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings.json")

DEFAULTS = {
    "sensitivity": 0.15,
    "cooldown": 0.8,
    "min_confidence": 0.70,
    "frame_window": 20,
    "enabled": True,
    "mode": "spaces",
    "show_landmarks": True,
    "show_trail": True,
    "natural_scrolling": False,
}


def load() -> dict:
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                data = json.load(f)
            merged = DEFAULTS.copy()
            merged.update(data)
            return merged
        except Exception:
            pass
    return DEFAULTS.copy()


def save(cfg: dict):
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(cfg, f, indent=2)
    except Exception as e:
        print(f"[config] Could not save settings: {e}")
