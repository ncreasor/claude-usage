import shutil
import struct
import tempfile
from pathlib import Path

MAGIC = b"cook"
UINT32_LEN = 4

PAGE_COOKIE_COUNT_OFFSET = 4
PAGE_COOKIE_OFFSETS_START = 8

RECORD_DOMAIN_OFFSET_POS = 16
RECORD_NAME_OFFSET_POS = 20
RECORD_VALUE_OFFSET_POS = 28

_COOKIES_FILE = (
    Path.home() / "Library" / "Containers" / "com.apple.Safari" / "Data"
    / "Library" / "Cookies" / "Cookies.binarycookies"
)


class SafariBrowser:
    def __init__(self, cookies_file: Path | None = None):
        self._cookies_file = cookies_file or _COOKIES_FILE

    def is_available(self) -> bool:
        return self._cookies_file.exists()

    def read_cookies(self, domain: str) -> dict[str, str]:
        if not self._cookies_file.exists():
            raise FileNotFoundError(f"Cookies file not found: {self._cookies_file}")
        with tempfile.NamedTemporaryFile(suffix=".binarycookies", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            shutil.copy(self._cookies_file, tmp_path)
            data = tmp_path.read_bytes()
        finally:
            try:
                tmp_path.unlink()
            except OSError:
                pass
        return self._parse(data, domain)

    @staticmethod
    def _parse(data: bytes, domain: str) -> dict[str, str]:
        if data[: len(MAGIC)] != MAGIC:
            raise ValueError("not a Safari binary cookies file")

        offset = len(MAGIC)
        num_pages = struct.unpack_from(">I", data, offset)[0]
        offset += UINT32_LEN

        page_sizes = []
        for _ in range(num_pages):
            page_sizes.append(struct.unpack_from(">I", data, offset)[0])
            offset += UINT32_LEN

        cookies: dict[str, str] = {}
        for size in page_sizes:
            page = data[offset : offset + size]
            offset += size
            cookies.update(SafariBrowser._parse_page(page, domain))
        return cookies

    @staticmethod
    def _parse_page(page: bytes, domain: str) -> dict[str, str]:
        num_cookies = struct.unpack_from("<I", page, PAGE_COOKIE_COUNT_OFFSET)[0]
        cookies: dict[str, str] = {}
        for i in range(num_cookies):
            record_offset = struct.unpack_from(
                "<I", page, PAGE_COOKIE_OFFSETS_START + i * UINT32_LEN
            )[0]
            name, value, cookie_domain = SafariBrowser._parse_record(page[record_offset:])
            if cookie_domain.endswith(domain):
                cookies[name] = value
        return cookies

    @staticmethod
    def _parse_record(record: bytes) -> tuple[str, str, str]:
        size = struct.unpack_from("<I", record, 0)[0]
        record = record[:size]
        domain_offset = struct.unpack_from("<I", record, RECORD_DOMAIN_OFFSET_POS)[0]
        name_offset = struct.unpack_from("<I", record, RECORD_NAME_OFFSET_POS)[0]
        value_offset = struct.unpack_from("<I", record, RECORD_VALUE_OFFSET_POS)[0]

        def read_cstr(start: int) -> str:
            end = record.index(b"\x00", start)
            return record[start:end].decode("utf-8", errors="replace")

        return read_cstr(name_offset), read_cstr(value_offset), read_cstr(domain_offset)
