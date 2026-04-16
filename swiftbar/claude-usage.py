#!/usr/bin/env python3
import base64
import json
import math
import struct
import sys
import zlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".claude-usage"))
from claude_shared import CONFIG_FILE, DATA_FILE, load_config  # noqa: E402

FETCH_NOW_URL = "http://127.0.0.1:18247/fetch-now"

SCALE = 2

BAR_W = 60 * SCALE
BAR_W_SLIM = 36 * SCALE
BAR_H = 18 * SCALE
BAR_R = 9 * SCALE
BAR_GAP = 4 * SCALE
LABEL_GAP = 5 * SCALE
PAIR_GAP = 8 * SCALE
FULL_THRESHOLD_PCT = 99
FONT_W = 5
FONT_H = 7
FONT_SCALE = SCALE
GLYPH_SPACING = 1 * SCALE
ALPHA = 255
STALE_AFTER_SEC = 600

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

THEMES = {
    "orange": {"fill": (212, 132, 94),  "bg": (55, 55, 55), "text": (255, 255, 255)},
    "blue":   {"fill": (91,  155, 213), "bg": (55, 55, 55), "text": (255, 255, 255)},
    "green":  {"fill": (91,  168, 95),  "bg": (55, 55, 55), "text": (255, 255, 255)},
    "purple": {"fill": (155, 89,  182), "bg": (55, 55, 55), "text": (255, 255, 255)},
    "red":    {"fill": (213, 94,  94),  "bg": (55, 55, 55), "text": (255, 255, 255)},
    "teal":   {"fill": (80,  195, 185), "bg": (55, 55, 55), "text": (255, 255, 255)},
    "pink":   {"fill": (213, 94,  160), "bg": (55, 55, 55), "text": (255, 255, 255)},
    "yellow": {"fill": (210, 185, 80),  "bg": (55, 55, 55), "text": (255, 255, 255)},
}

def _g(lines):
    return [int(row.replace(".", "0").replace("#", "1"), 2) for row in lines]


FONT = {
    " ": _g([".....", ".....", ".....", ".....", ".....", ".....", "....."]),
    "0": _g([".###.", "#...#", "#..##", "#.#.#", "##..#", "#...#", ".###."]),
    "1": _g(["..#..", ".##..", "..#..", "..#..", "..#..", "..#..", ".###."]),
    "2": _g([".###.", "#...#", "....#", "..##.", ".#...", "#....", "#####"]),
    "3": _g(["####.", "....#", "....#", ".###.", "....#", "....#", "####."]),
    "4": _g(["...#.", "..##.", ".#.#.", "#..#.", "#####", "...#.", "...#."]),
    "5": _g(["#####", "#....", "####.", "....#", "....#", "#...#", ".###."]),
    "6": _g([".###.", "#....", "#....", "####.", "#...#", "#...#", ".###."]),
    "7": _g(["#####", "....#", "....#", "...#.", "..#..", ".#...", "#...."]),
    "8": _g([".###.", "#...#", "#...#", ".###.", "#...#", "#...#", ".###."]),
    "9": _g([".###.", "#...#", "#...#", ".####", "....#", "....#", ".###."]),
    ":": _g([".....", "..#..", "..#..", ".....", "..#..", "..#..", "....."]),
    "%": _g(["##..#", "##.#.", "...#.", "..#..", ".#...", ".#.##", "#..##"]),
    ".": _g([".....", ".....", ".....", ".....", ".....", "..#..", "..#.."]),
    "A": _g([".###.", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"]),
    "D": _g(["####.", "#...#", "#...#", "#...#", "#...#", "#...#", "####."]),
    "F": _g(["#####", "#....", "#....", "####.", "#....", "#....", "#...."]),
    "J": _g(["..###", "....#", "....#", "....#", "....#", "#...#", ".###."]),
    "M": _g(["#...#", "##.##", "#.#.#", "#...#", "#...#", "#...#", "#...#"]),
    "N": _g(["#...#", "##..#", "#.#.#", "#.#.#", "#..##", "#...#", "#...#"]),
    "O": _g([".###.", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."]),
    "P": _g(["####.", "#...#", "#...#", "####.", "#....", "#....", "#...."]),
    "S": _g([".####", "#....", "#....", ".###.", "....#", "....#", "####."]),
    "a": _g([".....", ".....", ".###.", "....#", ".####", "#...#", ".####"]),
    "b": _g(["#....", "#....", "####.", "#...#", "#...#", "#...#", "####."]),
    "c": _g([".....", ".....", ".###.", "#....", "#....", "#....", ".###."]),
    "e": _g([".....", ".....", ".###.", "#...#", "#####", "#....", ".###."]),
    "g": _g([".....", ".####", "#...#", "#...#", ".####", "....#", ".###."]),
    "l": _g([".##..", "..#..", "..#..", "..#..", "..#..", "..#..", ".###."]),
    "n": _g([".....", ".....", "####.", "#...#", "#...#", "#...#", "#...#"]),
    "o": _g([".....", ".....", ".###.", "#...#", "#...#", "#...#", ".###."]),
    "p": _g([".....", "####.", "#...#", "#...#", "####.", "#....", "#...."]),
    "r": _g([".....", ".....", "#.##.", "##..#", "#....", "#....", "#...."]),
    "t": _g([".#...", "####.", ".#...", ".#...", ".#...", ".#...", "..##."]),
    "u": _g([".....", ".....", "#...#", "#...#", "#...#", "#...#", ".####"]),
    "v": _g([".....", ".....", "#...#", "#...#", "#...#", ".#.#.", "..#.."]),
    "y": _g([".....", ".....", "#...#", "#...#", "#...#", ".####", ".###."]),
}


def text_width(text):
    if not text:
        return 0
    return len(text) * (FONT_W * FONT_SCALE) + (len(text) - 1) * GLYPH_SPACING


def pill_alpha(x, y, w, h, r):
    px, py = x + 0.5, y + 0.5
    cx = max(float(r), min(float(w - r), px))
    cy = max(float(r), min(float(h - r), py))
    dist = math.sqrt((px - cx) ** 2 + (py - cy) ** 2)
    return max(0.0, min(1.0, r - dist + 0.5))


def in_rounded_rect(x, y, w, h, r):
    return pill_alpha(x, y, w, h, r) > 0


def encode_png(w, h, raw_data):
    sig = b"\x89PNG\r\n\x1a\n"

    def chunk(ctype, data):
        c = ctype + data
        crc = struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)
        return struct.pack(">I", len(data)) + c + crc

    ihdr = struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)
    ppm = round(SCALE * 72 / 0.0254)
    phys = struct.pack(">IIB", ppm, ppm, 1)
    idat = zlib.compress(raw_data)
    return sig + chunk(b"IHDR", ihdr) + chunk(b"pHYs", phys) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")


def make_pixels(w, h):
    return [[(0, 0, 0, 0) for _ in range(w)] for _ in range(h)]


def draw_bar(pixels, x0, y0, pct, w, h, r, fill, bg):
    fill_w = max(0, min(w, round(w * pct / 100))) if pct is not None else 0
    for y in range(h):
        for x in range(w):
            a = pill_alpha(x, y, w, h, r)
            if a <= 0:
                continue
            color = fill if x < fill_w else bg
            pixels[y0 + y][x0 + x] = (*color, round(a * ALPHA))


def draw_text(pixels, x0, y0, text, w, h, r, text_color):
    width = text_width(text)
    tx = x0 + (w - width) // 2
    for ch in text:
        glyph = FONT.get(ch)
        if glyph is None:
            tx += FONT_W * FONT_SCALE + GLYPH_SPACING
            continue
        for gy in range(FONT_H):
            bits = glyph[gy]
            for gx in range(FONT_W):
                if not (bits >> (FONT_W - 1 - gx)) & 1:
                    continue
                for sy in range(FONT_SCALE):
                    for sx in range(FONT_SCALE):
                        px = tx + gx * FONT_SCALE + sx
                        py = y0 + gy * FONT_SCALE + sy
                        bar_x = px - x0
                        if not (0 <= bar_x < w and 0 <= py - y0 < h):
                            continue
                        if not in_rounded_rect(bar_x, py - y0, w, h, r):
                            continue
                        pixels[py][px] = (*text_color, ALPHA)
        tx += FONT_W * FONT_SCALE + GLYPH_SPACING


def draw_text_raw(pixels, x0, y0, text, text_color):
    total_h = len(pixels)
    total_w = len(pixels[0]) if total_h else 0
    tx = x0
    for ch in text:
        glyph = FONT.get(ch)
        if glyph is None:
            tx += FONT_W * FONT_SCALE + GLYPH_SPACING
            continue
        for gy in range(FONT_H):
            bits = glyph[gy]
            for gx in range(FONT_W):
                if not (bits >> (FONT_W - 1 - gx)) & 1:
                    continue
                for sy in range(FONT_SCALE):
                    for sx in range(FONT_SCALE):
                        px = tx + gx * FONT_SCALE + sx
                        py = y0 + gy * FONT_SCALE + sy
                        if 0 <= px < total_w and 0 <= py < total_h:
                            pixels[py][px] = (*text_color, ALPHA)
        tx += FONT_W * FONT_SCALE + GLYPH_SPACING


def pixels_to_png(pixels):
    h = len(pixels)
    w = len(pixels[0]) if h else 0
    rows = []
    for row in pixels:
        rows.append(b"\x00" + b"".join(bytes(px) for px in row))
    return encode_png(w, h, b"".join(rows))


def b64img(png_bytes):
    return base64.b64encode(png_bytes).decode()


def round_to_nearest_hour(dt):
    base = dt.replace(minute=0, second=0, microsecond=0)
    if dt.minute >= 30:
        base += timedelta(hours=1)
    return base


def format_hour(dt, fmt):
    rounded = round_to_nearest_hour(dt)
    if fmt == "12h":
        h = str(int(rounded.strftime("%I")))
        suffix = "AM" if rounded.hour < 12 else "PM"
        return f"{h}{suffix}"
    return rounded.strftime("%H")


def format_session_reset(iso_str, fmt):
    if not iso_str:
        return ""
    try:
        return format_hour(datetime.fromisoformat(iso_str).astimezone(), fmt)
    except ValueError:
        return ""


def format_weekly_reset(iso_str, fmt):
    if not iso_str:
        return ""
    try:
        dt = datetime.fromisoformat(iso_str).astimezone()
    except ValueError:
        return ""
    rounded = round_to_nearest_hour(dt)
    return f"{MONTHS[rounded.month - 1]} {rounded.day} {format_hour(dt, fmt)}"


def session_label(pct, resets_at, fmt):
    if pct is None:
        return "--"
    reset = format_session_reset(resets_at, fmt)
    if pct >= FULL_THRESHOLD_PCT:
        return reset or f"{pct}%"
    return f"{pct}% {reset}".strip()


def weekly_label(pct, resets_at, fmt):
    if pct is None:
        return "--"
    if pct >= FULL_THRESHOLD_PCT:
        return format_weekly_reset(resets_at, fmt) or f"{pct}%"
    return f"{pct}%"


def render_bars(sp, sr, wp, wr, cfg):
    theme = THEMES.get(cfg["theme"], THEMES["orange"])
    fmt = cfg["time_format"]
    ty = (BAR_H - FONT_H * FONT_SCALE) // 2

    if cfg["percent_position"] == "inside":
        total_w = BAR_W * 2 + BAR_GAP
        pixels = make_pixels(total_w, BAR_H)
        draw_bar(pixels, 0, 0, sp, BAR_W, BAR_H, BAR_R, theme["fill"], theme["bg"])
        draw_bar(pixels, BAR_W + BAR_GAP, 0, wp, BAR_W, BAR_H, BAR_R, theme["fill"], theme["bg"])
        draw_text(pixels, 0, ty, session_label(sp, sr, fmt), BAR_W, BAR_H, BAR_R, theme["text"])
        draw_text(pixels, BAR_W + BAR_GAP, ty, weekly_label(wp, wr, fmt), BAR_W, BAR_H, BAR_R, theme["text"])
    else:
        s_lbl = session_label(sp, sr, fmt)
        w_lbl = weekly_label(wp, wr, fmt)
        s_w = text_width(s_lbl)
        w_w = text_width(w_lbl)
        total_w = BAR_W_SLIM + LABEL_GAP + s_w + PAIR_GAP + BAR_W_SLIM + LABEL_GAP + w_w
        pixels = make_pixels(total_w, BAR_H)
        draw_bar(pixels, 0, 0, sp, BAR_W_SLIM, BAR_H, BAR_R, theme["fill"], theme["bg"])
        draw_text_raw(pixels, BAR_W_SLIM + LABEL_GAP, ty, s_lbl, theme["text"])
        x2 = BAR_W_SLIM + LABEL_GAP + s_w + PAIR_GAP
        draw_bar(pixels, x2, 0, wp, BAR_W_SLIM, BAR_H, BAR_R, theme["fill"], theme["bg"])
        draw_text_raw(pixels, x2 + BAR_W_SLIM + LABEL_GAP, ty, w_lbl, theme["text"])

    return pixels_to_png(pixels)


def main():
    cfg = load_config()
    refresh = (
        f"bash=/usr/bin/curl param1=-s param2=-X param3=POST "
        f"param4={FETCH_NOW_URL} terminal=false"
    )

    if not DATA_FILE.exists():
        print(f"| {refresh}")
        return

    try:
        data = json.loads(DATA_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        print(f"| {refresh}")
        return

    sp = data.get("session_percent")
    wp = data.get("weekly_percent")
    sr = data.get("session_resets_at")
    wr = data.get("weekly_resets_at")

    if data.get("updated_at"):
        try:
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(data["updated_at"])).total_seconds()
            if age > STALE_AFTER_SEC:
                sp = wp = None
        except ValueError:
            pass

    img = b64img(render_bars(sp, sr, wp, wr, cfg))
    print(f"| image={img} {refresh}")


if __name__ == "__main__":
    main()
