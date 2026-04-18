import base64
import io
import json
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

VERSION = "1.4.0"
UPDATE_URL = "http://127.0.0.1:18247/update"
CHECK_UPDATE_URL = "http://127.0.0.1:18247/check-update"

CONFIG_FILE = Path.home() / ".claude-usage" / "config.json"
DATA_FILE = Path.home() / ".claude-usage" / "data.json"

THEME_NAMES = ["orange", "blue", "green", "purple", "red", "teal", "pink", "yellow"]
INTERVALS = [1, 2, 5, 10, 15, 30]

DEFAULT_CONFIG = {
    "style": "standard",
    "theme": "orange",
    "fetch_interval_minutes": 5,
    "time_format": "rounded",
    "click_action": "refresh",
    "show_weekly": True,
}

THEMES = {
    "orange": {"fill": (212, 132, 94),  "text": (255, 255, 255)},
    "blue":   {"fill": (91,  155, 213), "text": (255, 255, 255)},
    "green":  {"fill": (91,  168, 95),  "text": (255, 255, 255)},
    "purple": {"fill": (155, 89,  182), "text": (255, 255, 255)},
    "red":    {"fill": (213, 94,  94),  "text": (255, 255, 255)},
    "teal":   {"fill": (80,  195, 185), "text": (255, 255, 255)},
    "pink":   {"fill": (213, 94,  160), "text": (255, 255, 255)},
    "yellow": {"fill": (210, 185, 80),  "text": (255, 255, 255)},
}

SCALE = 2
BAR_H = 3 * SCALE
BAR_R = 1 * SCALE
CANVAS_PAD = 2 * SCALE
TRACK_COLOR = (75, 75, 75, 180)

STD_FONT_SIZE = 13 * SCALE
STD_BAR_W = 52 * SCALE
STD_LABEL_GAP = 5 * SCALE

CMP_FONT_SIZE = 11 * SCALE
CMP_BAR_W = 40 * SCALE
CMP_COL_GAP = 10 * SCALE
CMP_TEXT_BAR_GAP = 3 * SCALE

_FONT_PATHS = [
    "/System/Library/Fonts/Helvetica.ttc",
    "/System/Library/Fonts/SFNS.ttf",
    "/System/Library/Fonts/SFNSText.ttf",
]


def load_font(size):
    for path in _FONT_PATHS:
        try:
            return ImageFont.truetype(path, size=size)
        except (OSError, IOError):
            pass
    return ImageFont.load_default(size=size)


def text_width(font, text):
    if not text:
        return 0
    bbox = font.getbbox(text)
    return bbox[2] - bbox[0]


def draw_progress_bar(img, x0, y0, fill_color, pct, bar_w):
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([x0, y0, x0 + bar_w, y0 + BAR_H], radius=BAR_R, fill=TRACK_COLOR)
    fill_w = max(0, min(bar_w, round(bar_w * pct / 100))) if pct is not None else 0
    if fill_w > 0:
        temp = Image.new("RGBA", img.size, (0, 0, 0, 0))
        tdraw = ImageDraw.Draw(temp)
        tdraw.rounded_rectangle([x0, y0, x0 + bar_w, y0 + BAR_H], radius=BAR_R, fill=(*fill_color, 255))
        tdraw.rectangle([x0 + fill_w, 0, x0 + bar_w + 1, img.height], fill=(0, 0, 0, 0))
        img.alpha_composite(temp)


def time_remaining(iso_str, fmt="rounded"):
    if not iso_str:
        return ""
    try:
        dt = datetime.fromisoformat(iso_str)
        delta = dt - datetime.now(tz=dt.tzinfo or timezone.utc)
        secs = delta.total_seconds()
        if secs <= 0:
            return ""
        mins = secs / 60
        if fmt == "exact":
            if mins < 60:
                return f"{int(secs // 60)}m"
            h = int(mins // 60)
            m = int(mins % 60)
            if h < 24:
                return f"{h}h{m:02d}m"
            d = h // 24
            rh = h % 24
            return f"{d}d{rh}h" if rh else f"{d}d"
        if mins < 60:
            return f"{round(mins)}m"
        hours = mins / 60
        if hours < 24:
            return f"{round(hours)}h"
        return f"{round(hours / 24)}d"
    except ValueError:
        return ""


def render_weekly_bar(wp, wr, cfg):
    theme = THEMES.get(cfg["theme"], THEMES["orange"])
    fill_color = theme["fill"]
    text_color = (*theme["text"], 255)
    style = cfg.get("style", "standard")
    time_fmt = cfg.get("time_format", "rounded")

    w_pct = f"{wp}%" if wp is not None else "--"
    w_time = time_remaining(wr, time_fmt)

    if style == "compact":
        font = load_font(CMP_FONT_SIZE)
        ref_h = font.getbbox("0%")[3] - font.getbbox("0%")[1]
        w_lbl = f"{w_pct} {w_time}".strip()
        tw_wl = text_width(font, w_lbl)
        col_w = max(CMP_BAR_W, tw_wl)
        total_w = col_w
        total_h = CANVAS_PAD + BAR_H + CMP_TEXT_BAR_GAP + ref_h + CANVAS_PAD

        img = Image.new("RGBA", (total_w, total_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        ty_bar = CANVAS_PAD
        ty_text = ty_bar + BAR_H + CMP_TEXT_BAR_GAP
        bar_x = (col_w - CMP_BAR_W) // 2
        draw_progress_bar(img, bar_x, ty_bar, fill_color, wp, CMP_BAR_W)
        draw.text(((col_w - tw_wl) // 2, ty_text), w_lbl, font=font, fill=text_color, anchor="lt")
    else:
        font = load_font(STD_FONT_SIZE)
        ref_h = font.getbbox("0%")[3] - font.getbbox("0%")[1]
        tw_wp = text_width(font, w_pct)
        tw_wt = text_width(font, w_time)
        total_h = max(ref_h, BAR_H) + CANVAS_PAD * 2
        total_w = tw_wp + STD_LABEL_GAP + STD_BAR_W + (STD_LABEL_GAP + tw_wt if w_time else 0)

        img = Image.new("RGBA", (total_w, total_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        cy = total_h // 2
        draw.text((0, cy), w_pct, font=font, fill=text_color, anchor="lm")
        bx = tw_wp + STD_LABEL_GAP
        draw_progress_bar(img, bx, cy - BAR_H // 2, fill_color, wp, STD_BAR_W)
        if w_time:
            draw.text((bx + STD_BAR_W + STD_LABEL_GAP, cy), w_time, font=font, fill=text_color, anchor="lm")

    buf = io.BytesIO()
    img.save(buf, format="PNG", dpi=(round(SCALE * 72), round(SCALE * 72)))
    return buf.getvalue()


def b64img(png_bytes):
    return base64.b64encode(png_bytes).decode()


def load_config():
    cfg = dict(DEFAULT_CONFIG)
    try:
        stored = json.loads(CONFIG_FILE.read_text())
        for k in DEFAULT_CONFIG:
            if k in stored:
                cfg[k] = stored[k]
    except (OSError, json.JSONDecodeError):
        pass
    return cfg


def save_config(key, value):
    cfg = load_config()
    cfg[key] = value
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2))
