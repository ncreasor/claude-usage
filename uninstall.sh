#!/usr/bin/env bash
set -euo pipefail

PLIST_DIR="$HOME/Library/LaunchAgents"
SERVER_PLIST="$PLIST_DIR/com.claude.usage.plist"
SYSTRAY_PLIST="$PLIST_DIR/com.claude.usage.systray.plist"

# ── Stop and remove server daemon ─────────────────────────────────────────────
if [ -f "$SERVER_PLIST" ]; then
    launchctl bootout "gui/$(id -u)" "$SERVER_PLIST" 2>/dev/null || true
    rm "$SERVER_PLIST"
    echo "Server daemon removed."
else
    echo "Server daemon not installed — skipping."
fi

# ── Stop and remove systray app ───────────────────────────────────────────────
if [ -f "$SYSTRAY_PLIST" ]; then
    launchctl bootout "gui/$(id -u)" "$SYSTRAY_PLIST" 2>/dev/null || true
    rm "$SYSTRAY_PLIST"
    pkill -f "claude-usage-systray\|claude-usage.py" 2>/dev/null || true
    echo "Systray app removed."
else
    echo "Systray app not installed — skipping."
fi

# ── Remove launcher app ───────────────────────────────────────────────────────
APP_PATH="$HOME/Applications/Claude Usage.app"
if [ -d "$APP_PATH" ]; then
    rm -rf "$APP_PATH"
    echo "Launcher app removed."
fi

# ── Optionally remove cached data and shared lib ──────────────────────────────
DATA_DIR="$HOME/.claude-usage"
if [ -d "$DATA_DIR" ]; then
    read -rp "Remove cached data at $DATA_DIR? [y/N] " confirm
    if [[ "$confirm" == "y" || "$confirm" == "Y" ]]; then
        rm -rf "$DATA_DIR"
        echo "Data removed."
    fi
fi

echo "Done."
