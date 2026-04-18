import hashlib
import logging
import os
import shutil
import sqlite3
import subprocess
import tempfile
from pathlib import Path

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

log = logging.getLogger(__name__)

KEYCHAIN_SERVICE = "Chrome Safe Storage"

PBKDF2_ITERATIONS = 1003
PBKDF2_KEY_LEN = 16
AES_IV = b" " * 16
COOKIE_PREFIX_LEN = 3
SHA256_DOMAIN_PREFIX_LEN = 32

_KNOWN_PATHS = {
    "chrome": Path.home() / "Library" / "Application Support" / "Google" / "Chrome" / "Default" / "Cookies",
    "arc":    Path.home() / "Library" / "Application Support" / "Arc" / "User Data" / "Default" / "Cookies",
    "brave":  Path.home() / "Library" / "Application Support" / "BraveSoftware" / "Brave-Browser" / "Default" / "Cookies",
}


class ChromeBrowser:
    def __init__(self, cookies_db: Path | None = None):
        self._cookies_db = cookies_db or _KNOWN_PATHS["chrome"]

    @classmethod
    def for_browser(cls, name: str) -> "ChromeBrowser":
        path = _KNOWN_PATHS.get(name)
        if path is None:
            raise ValueError(f"Unknown Chromium-based browser: {name!r}")
        return cls(path)

    def read_cookies(self, domain: str) -> dict[str, str]:
        if not self._cookies_db.exists():
            raise FileNotFoundError(f"Cookies DB not found: {self._cookies_db}")
        key = self._key()
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            tmp_path = tmp.name
        try:
            shutil.copy(self._cookies_db, tmp_path)
            conn = sqlite3.connect(tmp_path)
            try:
                cur = conn.cursor()
                cur.execute(
                    "SELECT name, encrypted_value FROM cookies WHERE host_key LIKE ?",
                    (f"%{domain}",),
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
                val = self._decrypt(blob, key)
                if val is not None:
                    cookies[name] = val
            except (ValueError, UnicodeDecodeError) as e:
                log.warning("cookie decrypt failed for %s: %s", name, e)
        return cookies

    @staticmethod
    def _key() -> bytes:
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

    @staticmethod
    def _decrypt(blob: bytes, key: bytes) -> str | None:
        if not blob or len(blob) < COOKIE_PREFIX_LEN:
            return None
        payload = blob[COOKIE_PREFIX_LEN:]
        cipher = Cipher(algorithms.AES(key), modes.CBC(AES_IV), backend=default_backend())
        d = cipher.decryptor()
        raw = d.update(payload) + d.finalize()
        pad = raw[-1]
        raw = raw[:-pad]
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            return raw[SHA256_DOMAIN_PREFIX_LEN:].decode("utf-8")
