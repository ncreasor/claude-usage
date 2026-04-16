#!/usr/bin/env bash
set -euo pipefail

PLIST_DEST="$HOME/Library/LaunchAgents/com.claude.usage.plist"
PLUGINS_DIR="$(defaults read com.ameba.SwiftBar PluginsDirectory 2>/dev/null || true)"
PLUGIN_DEST="${PLUGINS_DIR:+$PLUGINS_DIR/claude-usage.py}"

# ── Stop and remove daemon ────────────────────────────────────────────────────
if [ -f "$PLIST_DEST" ]; then
    launchctl unload "$PLIST_DEST" 2>/dev/null || true
    rm "$PLIST_DEST"
    echo "Daemon removed."
else
    echo "Daemon not installed — skipping."
fi

# ── Remove plugins ────────────────────────────────────────────────────────────
for plugin in claude-usage.py claude-settings.py; do
    dest="${PLUGINS_DIR:+$PLUGINS_DIR/$plugin}"
    if [ -n "$dest" ] && [ -f "$dest" ]; then
        rm "$dest"
        echo "Plugin removed: $dest"
    fi
done
if [ -n "$PLUGINS_DIR" ]; then
    read -rp "Restart SwiftBar to unload plugins? [y/N] " restart
    if [[ "$restart" == "y" || "$restart" == "Y" ]]; then
        pkill -x SwiftBar 2>/dev/null || true
        open -a SwiftBar
    fi
fi

# ── Optionally remove cached data ─────────────────────────────────────────────
DATA_DIR="$HOME/.claude-usage"
if [ -d "$DATA_DIR" ]; then
    read -rp "Remove cached data at $DATA_DIR? [y/N] " confirm
    if [[ "$confirm" == "y" || "$confirm" == "Y" ]]; then
        rm -rf "$DATA_DIR"
        echo "Data removed."
    fi
fi

echo "Done."
