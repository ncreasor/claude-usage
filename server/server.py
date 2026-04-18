#!/usr/bin/env python3
import json
import logging
import os
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

from claude_shared import DATA_FILE, PORT, VERSION, load_config  # noqa: E402
from curl_cffi import requests as curl_requests

GITHUB_REPO = "ncreasor/claude-usage"
REPO_DIR = Path(__file__).parent.parent

DEFAULT_FETCH_INTERVAL_MINUTES = 5
FETCH_RETRY_SECONDS = 30
HTTP_TIMEOUT_SECONDS = 20
UPDATE_CHECK_INTERVAL_SECONDS = 3600

_fetch_event = threading.Event()
_data_lock = threading.Lock()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("claude-usage")


def _build_source():
    cfg = load_config()
    source_name = cfg.get("source", "subscription")
    browser_name = cfg.get("browser", "chrome")

    if source_name == "api":
        from sources.api import ApiSource
        return ApiSource()

    if browser_name in ("arc", "brave"):
        from browsers.chrome import ChromeBrowser
        browser = ChromeBrowser.for_browser(browser_name)
    elif browser_name == "firefox":
        from browsers.firefox import FirefoxBrowser
        browser = FirefoxBrowser()
    elif browser_name == "safari":
        from browsers.safari import SafariBrowser
        browser = SafariBrowser()
    else:
        from browsers.chrome import ChromeBrowser
        browser = ChromeBrowser()

    from sources.subscription import SubscriptionSource
    return SubscriptionSource(browser)


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", dir=path.parent, suffix=".tmp", delete=False
    ) as f:
        f.write(text)
        tmp_path = f.name
    os.replace(tmp_path, path)


def _refresh_plugins(*names: str) -> None:
    for name in names:
        subprocess.Popen(
            ["/usr/bin/open", "-g", f"swiftbar://refreshplugin?name={name}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def _patch_data_file(updates: dict) -> None:
    with _data_lock:
        data = {}
        if DATA_FILE.exists():
            try:
                data = json.loads(DATA_FILE.read_text())
            except (OSError, json.JSONDecodeError):
                log.warning("failed to read data file")
        data.update(updates)
        _atomic_write(DATA_FILE, json.dumps(data, indent=2))


def run_fetch():
    source = _build_source()
    data = source.fetch()
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    _patch_data_file(data)
    log.info(
        "fetched: session=%s%% weekly=%s%%",
        data["session_percent"],
        data["weekly_percent"],
    )
    _refresh_plugins("claude-usage")
    return data


def _write_update_status(available: bool, latest_version: str) -> None:
    try:
        _patch_data_file({"update_available": available, "latest_version": latest_version})
    except OSError as e:
        log.warning("failed to write update status: %s", e)


def _run_update_check():
    try:
        r = curl_requests.get(
            f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest",
            headers={"Accept": "application/vnd.github+json"},
            impersonate="chrome",
            timeout=HTTP_TIMEOUT_SECONDS,
        )
        r.raise_for_status()
        latest = r.json().get("tag_name", "").lstrip("v")
        if latest:
            available = latest != VERSION
            _write_update_status(available, latest)
            if available:
                log.info("update available: v%s (current: v%s)", latest, VERSION)
            _refresh_plugins("claude-usage", "claude-settings")
    except Exception as e:
        log.warning("update check failed: %s", e)


def update_check_loop():
    while True:
        _run_update_check()
        time.sleep(UPDATE_CHECK_INTERVAL_SECONDS)


def _fetch_interval_seconds():
    minutes = load_config()["fetch_interval_minutes"]
    return max(1, int(minutes)) * 60


def scheduler_loop():
    while True:
        try:
            run_fetch()
            triggered = _fetch_event.wait(timeout=_fetch_interval_seconds())
            if triggered:
                _fetch_event.clear()
        except Exception as e:
            log.error("fetch failed: %s", e)
            triggered = _fetch_event.wait(timeout=FETCH_RETRY_SECONDS)
            if triggered:
                _fetch_event.clear()


class UsageHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path == "/fetch-now":
            _fetch_event.set()
            self._respond(200, {"status": "ok"})
            return
        if self.path == "/check-update":
            threading.Thread(target=_run_update_check, daemon=True).start()
            self._respond(200, {"status": "ok"})
            return
        if self.path == "/update":
            update_cmd = (
                f"export PATH=/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin && "
                f"cd '{REPO_DIR}' && "
                f"git fetch origin && "
                f"git reset --hard origin/$(git rev-parse --abbrev-ref HEAD) && "
                f"./install.sh"
            )
            subprocess.Popen(
                ["/bin/bash", "-c", update_cmd],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            subprocess.Popen(
                ["/usr/bin/osascript", "-e",
                 'display notification "Restarting in a moment..." '
                 'with title "Updating Claude Usage"'],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            log.info("update triggered from %s", REPO_DIR)
            self._respond(200, {"status": "updating"})
            return
        self.send_error(404)

    def do_GET(self):
        if self.path == "/health":
            self._respond(200, {"status": "ok", "version": VERSION})
            return
        if self.path != "/usage":
            self.send_error(404)
            return
        if not DATA_FILE.exists():
            self._respond(200, {"status": "no data yet"})
            return
        self._respond_raw(200, DATA_FILE.read_bytes())

    def _respond(self, code, body):
        self._respond_raw(code, json.dumps(body).encode())

    def _respond_raw(self, code, payload):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format, *args):
        pass


def _notify_if_updated():
    try:
        data = {}
        if DATA_FILE.exists():
            data = json.loads(DATA_FILE.read_text())
        prev = data.get("installed_version")
        if prev and prev != VERSION:
            subprocess.Popen(
                ["/usr/bin/osascript", "-e",
                 f'display notification "Updated from v{prev} to v{VERSION}" '
                 f'with title "Claude Usage"'],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            log.info("updated from v%s to v%s", prev, VERSION)
        _patch_data_file({"installed_version": VERSION})
    except (OSError, json.JSONDecodeError) as e:
        log.warning("failed to check install version: %s", e)


def main():
    _notify_if_updated()
    threading.Thread(target=scheduler_loop, daemon=True).start()
    threading.Thread(target=update_check_loop, daemon=True).start()
    server = ThreadingHTTPServer(("127.0.0.1", PORT), UsageHandler)
    log.info("Claude Usage server listening on http://127.0.0.1:%d", PORT)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("shutting down")
        server.shutdown()


if __name__ == "__main__":
    main()
