#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
SERVER_PATH="$REPO_DIR/server/server.py"
SYSTRAY_PATH="$REPO_DIR/displays/systray/claude-usage.py"
PLIST_DIR="$HOME/Library/LaunchAgents"
SERVER_PLIST_TEMPLATE="$REPO_DIR/server/com.claude.usage.plist.template"
SERVER_PLIST_DEST="$PLIST_DIR/com.claude.usage.plist"
SYSTRAY_PLIST_TEMPLATE="$REPO_DIR/displays/systray/com.claude.usage.systray.plist.template"
SYSTRAY_PLIST_DEST="$PLIST_DIR/com.claude.usage.systray.plist"
SERVER_LOG_PATH="$HOME/Library/Logs/claude-usage.log"
SYSTRAY_LOG_PATH="$HOME/Library/Logs/claude-usage-systray.log"
VENV_DIR="$REPO_DIR/.venv"

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
    uv pip install --python "$VENV_DIR/bin/python" --quiet curl_cffi cryptography pillow rumps
else
    [ -d "$VENV_DIR" ] || "$BASE_PYTHON" -m venv "$VENV_DIR"
    "$VENV_DIR/bin/pip" install --quiet curl_cffi cryptography pillow rumps
fi

PYTHON="$VENV_DIR/bin/python"

# ── 4. Shared library ─────────────────────────────────────────────────────────
mkdir -p "$HOME/.claude-usage"
cp "$REPO_DIR/claude_shared.py" "$HOME/.claude-usage/claude_shared.py"
echo "Shared lib: ~/.claude-usage/claude_shared.py"

# ── 5. Server daemon ──────────────────────────────────────────────────────────
mkdir -p "$HOME/Library/Logs"
sed \
    -e "s|__PYTHON_BIN__|$PYTHON|g" \
    -e "s|__SERVER_PATH__|$SERVER_PATH|g" \
    -e "s|__LOG_PATH__|$SERVER_LOG_PATH|g" \
    "$SERVER_PLIST_TEMPLATE" > "$SERVER_PLIST_DEST"

launchctl bootout "gui/$(id -u)" "$SERVER_PLIST_DEST" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$SERVER_PLIST_DEST"
echo "Server daemon: loaded (logs: tail -f $SERVER_LOG_PATH)"

# ── 6. Systray app ────────────────────────────────────────────────────────────
sed \
    -e "s|__PYTHON_BIN__|$PYTHON|g" \
    -e "s|__SYSTRAY_PATH__|$SYSTRAY_PATH|g" \
    -e "s|__LOG_PATH__|$SYSTRAY_LOG_PATH|g" \
    "$SYSTRAY_PLIST_TEMPLATE" > "$SYSTRAY_PLIST_DEST"

launchctl bootout "gui/$(id -u)" "$SYSTRAY_PLIST_DEST" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$SYSTRAY_PLIST_DEST"
echo "Systray app: loaded (logs: tail -f $SYSTRAY_LOG_PATH)"

echo ""
echo "Done. Log into claude.ai in Chrome and the bar will appear within seconds."
