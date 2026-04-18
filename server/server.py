#!/usr/bin/env python3
import hashlib
import json
import logging
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from claude_shared import CONFIG_FILE, DATA_FILE, load_config  # noqa: E402

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from curl_cffi import requests as curl_requests
COOKIES_DB = Path.home() / "Library" / "Application Support" / "Google" / "Chrome" / "Default" / "Cookies"
KEYCHAIN_SERVICE = "Chrome Safe Storage"

VERSION = "1.5.0"
GITHUB_REPO = "ncreasor/claude-usage"
REPO_DIR = Path(__file__).parent.parent

API_BASE = "https://claude.ai/api"
PORT = 18247

DEFAULT_FETCH_INTERVAL_MINUTES = 5
FETCH_RETRY_SECONDS = 30
HTTP_TIMEOUT_SECONDS = 20
UPDATE_CHECK_INTERVAL_SECONDS = 3600

PBKDF2_ITERATIONS = 1003
PBKDF2_KEY_LEN = 16
AES_IV = b" " * 16
CHROME_COOKIE_PREFIX_LEN = 3
SHA256_DOMAIN_PREFIX_LEN = 32

_fetch_event = threading.Event()
_data_lock = threading.Lock()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("claude-usage")


def _chrome_key():
    result = subprocess.run(
        ["/usr/bin/security", "find-generic-password", "-w", "-s", KEYCHAIN_SERVICE],
        capture_output=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Keychain access failed (exit {result.returncode}): "
            f"{result.stderr.decode(errors='replace').strip()}"
        )
    pw = result.stdout.strip()
    return hashlib.pbkdf2_hmac("sha1", pw, b"saltysalt", PBKDF2_ITERATIONS, PBKDF2_KEY_LEN)


def _decrypt_cookie(blob, key):
    if not blob or len(blob) < CHROME_COOKIE_PREFIX_LEN:
        return None
    payload = blob[CHROME_COOKIE_PREFIX_LEN:]
    cipher = Cipher(algorithms.AES(key), modes.CBC(AES_IV), backend=default_backend())
    d = cipher.decryptor()
    raw = d.update(payload) + d.finalize()
    pad = raw[-1]
    raw = raw[:-pad]
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw[SHA256_DOMAIN_PREFIX_LEN:].decode("utf-8")


def read_claude_cookies():
    if not COOKIES_DB.exists():
        raise FileNotFoundError(f"Chrome cookies DB not found at {COOKIES_DB}")
    key = _chrome_key()
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        shutil.copy(COOKIES_DB, tmp_path)
        conn = sqlite3.connect(tmp_path)
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT name, encrypted_value FROM cookies WHERE host_key LIKE '%claude.ai'"
            )
            rows = cur.fetchall()
        finally:
            conn.close()
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    cookies = {}
    for name, blob in rows:
        try:
            val = _decrypt_cookie(blob, key)
            if val is not None:
                cookies[name] = val
        except (ValueError, UnicodeDecodeError) as e:
            log.warning("cookie decrypt failed for %s: %s", name, e)
    return cookies


def fetch_usage():
    cookies = read_claude_cookies()
    if "sessionKey" not in cookies:
        raise RuntimeError("sessionKey cookie not found — log into claude.ai in Chrome")
    org = cookies.get("lastActiveOrg")
    if not org:
        r = curl_requests.get(
            f"{API_BASE}/organizations",
            cookies=cookies,
            impersonate="chrome",
            timeout=HTTP_TIMEOUT_SECONDS,
        )
        r.raise_for_status()
        orgs = r.json()
        if not orgs:
            raise RuntimeError("no organizations returned")
        org = orgs[0]["uuid"]

    r = curl_requests.get(
        f"{API_BASE}/organizations/{org}/usage",
        cookies=cookies,
        impersonate="chrome",
        timeout=HTTP_TIMEOUT_SECONDS,
    )
    r.raise_for_status()
    raw = r.json()
    return {
        "session_percent": round(raw.get("five_hour", {}).get("utilization", 0)),
        "session_resets_at": raw.get("five_hour", {}).get("resets_at"),
        "weekly_percent": round(raw.get("seven_day", {}).get("utilization", 0)),
        "weekly_resets_at": raw.get("seven_day", {}).get("resets_at"),
    }


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", dir=path.parent, suffix=".tmp", delete=False
    ) as f:
        f.write(text)
        tmp_path = f.name
    os.replace(tmp_path, path)


def refresh_swiftbar():
    subprocess.Popen(
        ["/usr/bin/open", "-g", "swiftbar://refreshplugin?name=claude-usage"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def run_fetch():
    with _data_lock:
        data = fetch_usage()
        data["updated_at"] = datetime.now(timezone.utc).isoformat()
        if DATA_FILE.exists():
            try:
                prev = json.loads(DATA_FILE.read_text())
                for key in ("update_available", "latest_version"):
                    if key in prev:
                        data[key] = prev[key]
            except (json.JSONDecodeError, OSError):
                pass
        _atomic_write(DATA_FILE, json.dumps(data, indent=2))
        log.info(
            "fetched: session=%s%% weekly=%s%%",
            data["session_percent"],
            data["weekly_percent"],
        )
    refresh_swiftbar()
    return data


def _write_update_status(available, latest_version):
    with _data_lock:
        try:
            data = {}
            if DATA_FILE.exists():
                data = json.loads(DATA_FILE.read_text())
            data["update_available"] = available
            data["latest_version"] = latest_version
            _atomic_write(DATA_FILE, json.dumps(data, indent=2))
        except (json.JSONDecodeError, OSError) as e:
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
            for plugin in ["claude-usage", "claude-settings"]:
                subprocess.Popen(
                    ["/usr/bin/open", "-g", f"swiftbar://refreshplugin?name={plugin}"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
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
        data["installed_version"] = VERSION
        _atomic_write(DATA_FILE, json.dumps(data, indent=2))
    except (OSError, json.JSONDecodeError):
        pass


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
