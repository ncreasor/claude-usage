#!/usr/bin/env python3
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".claude-usage"))
from claude_shared import (  # noqa: E402
    DATA_FILE, INTERVALS, THEME_NAMES, CHECK_UPDATE_URL, UPDATE_URL, VERSION,
    b64img, load_config, render_weekly_bar, save_config,
)

RELEASES_URL = "https://github.com/ncreasor/claude-usage/releases"


_BOOL_KEYS = {"show_weekly"}


def _cfg_matches(cfg_val, opt_val):
    if isinstance(cfg_val, bool):
        return cfg_val == (opt_val == "true")
    return cfg_val == opt_val


def opt(label, key, value, cfg):
    mark = "✓" if _cfg_matches(cfg[key], value) else " "
    py = sys.executable
    pl = Path(__file__).resolve()
    return (
        f"-- {mark} {label} | bash={py} param1={pl} "
        f"param2=--set param3={key} param4={value} "
        f"terminal=false refresh=true"
    )


def load_update_info():
    try:
        data = json.loads(DATA_FILE.read_text())
        if data.get("update_available") and data.get("latest_version"):
            return data["latest_version"]
    except (OSError, json.JSONDecodeError):
        pass
    return None


def _load_weekly_data():
    try:
        data = json.loads(DATA_FILE.read_text())
        return data.get("weekly_percent"), data.get("weekly_resets_at")
    except (OSError, json.JSONDecodeError):
        return None, None


def main():
    cfg = load_config()

    if cfg.get("click_action") == "settings":
        sys.exit(0)

    latest_version = load_update_info()

    print("| sfimage=gearshape.fill")
    print("---")
    if latest_version:
        print(
            f"v{VERSION} → v{latest_version} | bash=/usr/bin/curl "
            f"param1=-s param2=-X param3=POST param4={UPDATE_URL} "
            f"terminal=false color=#ff9500"
        )
    else:
        print(
            f"v{VERSION}  ↻ | bash=/usr/bin/curl "
            f"param1=-s param2=-X param3=POST param4={CHECK_UPDATE_URL} "
            f"terminal=false color=#888888"
        )
    print("---")
    if not cfg.get("show_weekly", True):
        wp, wr = _load_weekly_data()
        weekly_img = b64img(render_weekly_bar(wp, wr, cfg))
        print(f"Weekly | image={weekly_img}")
        print("---")
    print("Style")
    print(opt("Standard", "style", "standard", cfg))
    print(opt("Compact", "style", "compact", cfg))
    print("Color")
    for theme in THEME_NAMES:
        print(opt(theme.capitalize(), "theme", theme, cfg))
    print("Refresh Interval")
    for mins in INTERVALS:
        label = f"{mins} min" if mins > 1 else "1 min"
        print(opt(label, "fetch_interval_minutes", mins, cfg))
    print("Time Format")
    print(opt("Rounded  (5m, 2h)", "time_format", "rounded", cfg))
    print(opt("Exact  (4m32s, 1h23m)", "time_format", "exact", cfg))
    print("Weekly Bar")
    print(opt("Show", "show_weekly", "true", cfg))
    print(opt("Hide (show in settings)", "show_weekly", "false", cfg))
    print("Bar Click Action")
    print(opt("Refresh data", "click_action", "refresh", cfg))
    print(opt("Open settings (hide gear)", "click_action", "settings", cfg))


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--set":
        key = sys.argv[2]
        raw = sys.argv[3]
        if key == "fetch_interval_minutes":
            value: str | int | bool = int(raw)
        elif key in _BOOL_KEYS:
            value = raw == "true"
        else:
            value = raw
        save_config(key, value)
        for plugin in ["claude-usage", "claude-settings"]:
            subprocess.Popen(
                ["/usr/bin/open", "-g", f"swiftbar://refreshplugin?name={plugin}"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        sys.exit(0)
    main()
