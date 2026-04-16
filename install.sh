#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
SERVER_PATH="$REPO_DIR/server/server.py"
PLIST_TEMPLATE="$REPO_DIR/server/com.claude.usage.plist.template"
PLIST_DEST="$HOME/Library/LaunchAgents/com.claude.usage.plist"
LOG_PATH="$HOME/Library/Logs/claude-usage.log"
VENV_DIR="$REPO_DIR/.venv"
DEFAULT_PLUGINS_DIR="$HOME/.swiftbar-plugins"

# ── 1. Homebrew ───────────────────────────────────────────────────────────────
if ! command -v brew &>/dev/null; then
    echo "Error: Homebrew not found. Install it from https://brew.sh then re-run."
    exit 1
fi

# ── 2. Python 3.11+ ───────────────────────────────────────────────────────────
BASE_PYTHON=""
for bin in python3.13 python3.12 python3.11 python3; do
    if command -v "$bin" &>/dev/null; then
        if "$bin" -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)" 2>/dev/null; then
            BASE_PYTHON="$(command -v "$bin")"
            break
        fi
    fi
done

if [ -z "$BASE_PYTHON" ]; then
    echo "Python 3.11+ not found — installing..."
    brew install python@3.13
    BASE_PYTHON="$(brew --prefix python@3.13)/bin/python3.13"
fi

echo "Python: $BASE_PYTHON ($("$BASE_PYTHON" --version))"

# ── 3. Virtualenv + dependencies ─────────────────────────────────────────────
if command -v uv &>/dev/null; then
    [ -d "$VENV_DIR" ] || uv venv --python "$BASE_PYTHON" --quiet "$VENV_DIR"
    uv pip install --python "$VENV_DIR/bin/python" --quiet curl_cffi cryptography
else
    [ -d "$VENV_DIR" ] || "$BASE_PYTHON" -m venv "$VENV_DIR"
    "$VENV_DIR/bin/pip" install --quiet curl_cffi cryptography
fi

PYTHON="$VENV_DIR/bin/python"

# ── 4. Launchd agent ─────────────────────────────────────────────────────────
mkdir -p "$HOME/Library/Logs"
sed \
    -e "s|__PYTHON_BIN__|$PYTHON|g" \
    -e "s|__SERVER_PATH__|$SERVER_PATH|g" \
    -e "s|__LOG_PATH__|$LOG_PATH|g" \
    "$PLIST_TEMPLATE" > "$PLIST_DEST"

launchctl unload "$PLIST_DEST" 2>/dev/null || true
launchctl load "$PLIST_DEST"
echo "Daemon: loaded (logs: tail -f $LOG_PATH)"

# ── 5. SwiftBar ───────────────────────────────────────────────────────────────
if [ ! -d "/Applications/SwiftBar.app" ]; then
    echo "SwiftBar: installing..."
    brew install --cask swiftbar
fi

PLUGINS_DIR="$(defaults read com.ameba.SwiftBar PluginsDirectory 2>/dev/null || true)"
if [ -z "$PLUGINS_DIR" ] || [ ! -d "$PLUGINS_DIR" ]; then
    mkdir -p "$DEFAULT_PLUGINS_DIR"
    defaults write com.ameba.SwiftBar PluginsDirectory "$DEFAULT_PLUGINS_DIR"
    PLUGINS_DIR="$DEFAULT_PLUGINS_DIR"
fi

mkdir -p "$HOME/.claude-usage"
cp "$REPO_DIR/claude_shared.py" "$HOME/.claude-usage/claude_shared.py"

for plugin in claude-usage.py claude-settings.py; do
    dest="$PLUGINS_DIR/$plugin"
    cp "$REPO_DIR/swiftbar/$plugin" "$dest"
    sed -i '' "1s|.*|#!$PYTHON|" "$dest"
    chmod +x "$dest"
    echo "Plugin: $dest"
done

# Launch / refresh SwiftBar
if pgrep -x SwiftBar &>/dev/null; then
    open -g "swiftbar://refreshplugin?name=claude-usage"
    open -g "swiftbar://refreshplugin?name=claude-settings"
else
    open -a SwiftBar
    sleep 3
    open -g "swiftbar://refreshplugin?name=claude-usage"
fi

echo ""
echo "Done. Log into claude.ai in Chrome and the bar will appear within seconds."
