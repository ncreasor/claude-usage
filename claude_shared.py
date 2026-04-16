import json
from pathlib import Path

CONFIG_FILE = Path.home() / ".claude-usage" / "config.json"
DATA_FILE = Path.home() / ".claude-usage" / "data.json"

THEME_NAMES = ["orange", "blue", "green", "purple", "red", "teal", "pink", "yellow"]

DEFAULT_CONFIG = {
    "time_format": "24h",
    "percent_position": "inside",
    "theme": "orange",
    "fetch_interval_minutes": 5,
}


def load_config():
    cfg = dict(DEFAULT_CONFIG)
    try:
        stored = json.loads(CONFIG_FILE.read_text())
        for k in DEFAULT_CONFIG:
            if k in stored:
                cfg[k] = stored[k]
    except (OSError, json.JSONDecodeError):
        pass
    return cfg


def save_config(key, value):
    cfg = load_config()
    cfg[key] = value
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2))
