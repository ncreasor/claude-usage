#!/usr/bin/env python3
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".claude-usage"))
from claude_shared import DATA_FILE, THEME_NAMES, load_config, save_config  # noqa: E402

RELEASES_URL = "https://github.com/ncreasor/claude-usage/releases"

INTERVALS = [1, 2, 5, 10, 15, 30]


def opt(label, key, value, cfg):
    mark = "✓" if cfg[key] == value else " "
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


def main():
    cfg = load_config()
    latest_version = load_update_info()

    print("| sfimage=gearshape.fill")
    print("---")
    if latest_version:
        print(
            f"Update available v{latest_version} | bash=/usr/bin/open "
            f"param1={RELEASES_URL} terminal=false"
        )
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


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--set":
        key = sys.argv[2]
        value: str | int = int(sys.argv[3]) if key == "fetch_interval_minutes" else sys.argv[3]
        save_config(key, value)
        subprocess.Popen(
            ["/usr/bin/open", "-g", "swiftbar://refreshplugin?name=claude-usage"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        sys.exit(0)
    main()
