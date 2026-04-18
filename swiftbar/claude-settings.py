#!/usr/bin/env python3
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".claude-usage"))
from claude_shared import (  # noqa: E402
    load_bar_data, load_config, load_update_info, print_settings_dropdown, save_config,
)

_BOOL_KEYS = {"show_weekly"}


def main():
    cfg = load_config()

    if cfg.get("click_action") == "settings":
        sys.exit(0)

    sp, sr, wp, wr = load_bar_data()
    latest_version = load_update_info()

    print("| sfimage=gearshape.fill")
    print_settings_dropdown(cfg, Path(__file__).resolve(), sp, sr, wp, wr, latest_version)


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
