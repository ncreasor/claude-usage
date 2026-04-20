import base64
import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

VERSION = "1.5.2"
PORT = 18247
UPDATE_URL = f"http://127.0.0.1:{PORT}/update"
CHECK_UPDATE_URL = f"http://127.0.0.1:{PORT}/check-update"
FETCH_NOW_URL = f"http://127.0.0.1:{PORT}/fetch-now"

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

CMP_BAR_GAP = 2 * SCALE

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
                return f"{h}h {m:02d}m"
            d = h // 24
            rh = h % 24
            return f"{d}d {rh}h" if rh else f"{d}d"
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
        total_h = CANVAS_PAD + BAR_H + CANVAS_PAD
        img = Image.new("RGBA", (STD_BAR_W, total_h), (0, 0, 0, 0))
        draw_progress_bar(img, 0, CANVAS_PAD, fill_color, wp, STD_BAR_W)
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


def load_data() -> dict | None:
    try:
        return json.loads(DATA_FILE.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def load_bar_data():
    data = load_data()
    if data is None:
        return None, None, None, None
    return (
        data.get("session_percent"), data.get("session_resets_at"),
        data.get("weekly_percent"), data.get("weekly_resets_at"),
    )


def load_update_info():
    data = load_data()
    if data and data.get("update_available") and data.get("latest_version"):
        return data["latest_version"]
    return None


def print_settings_dropdown(cfg, settings_script, sp=None, sr=None, wp=None, wr=None, latest_version=None):
    def opt(label, key, value):
        cfg_val = cfg[key]
        if isinstance(cfg_val, bool):
            match = cfg_val == (value == "true")
        else:
            match = cfg_val == value
        mark = "✓" if match else " "
        return (
            f"-- {mark} {label} | bash={sys.executable} param1={settings_script} "
            f"param2=--set param3={key} param4={value} "
            f"terminal=false refresh=true"
        )

    print("---")
    if latest_version:
        print(
            f"v{VERSION} → v{latest_version} | bash=/usr/bin/curl "
            f"param1=-s param2=-X param3=POST param4={UPDATE_URL} "
            f"terminal=false color=#ff9500"
        )
    else:
        print(
            f"v{VERSION}  ↻ | bash=/usr/bin/curl "
            f"param1=-s param2=-X param3=POST param4={CHECK_UPDATE_URL} "
            f"terminal=false color=#888888"
        )
    print("---")
    std_cfg = {**cfg, "style": "standard"}
    if cfg.get("style", "standard") == "compact":
        print(f"Session | image={b64img(render_weekly_bar(sp, sr, std_cfg))}")
        print(f"Weekly | image={b64img(render_weekly_bar(wp, wr, std_cfg))}")
        print("---")
    elif not cfg.get("show_weekly", True):
        print(f"Weekly | image={b64img(render_weekly_bar(wp, wr, std_cfg))}")
        print("---")
    print("Style")
    print(opt("Standard", "style", "standard"))
    print(opt("Compact", "style", "compact"))
    print("Color")
    for theme in THEME_NAMES:
        print(opt(theme.capitalize(), "theme", theme))
    print("Refresh Interval")
    for mins in INTERVALS:
        label = f"{mins} min" if mins > 1 else "1 min"
        print(opt(label, "fetch_interval_minutes", mins))
    print("Time Format")
    print(opt("Rounded  (3h, 6d)", "time_format", "rounded"))
    print(opt("Exact  (1h 23m, 2d 6h)", "time_format", "exact"))
    print("Weekly Bar")
    print(opt("Show", "show_weekly", "true"))
    print(opt("Hide (show in settings)", "show_weekly", "false"))
    print("Bar Click Action")
    print(opt("Refresh data", "click_action", "refresh"))
    print(opt("Open settings (hide gear)", "click_action", "settings"))
    print("---")
    print(
        f"Refresh now | bash=/usr/bin/curl param1=-s param2=-X "
        f"param3=POST param4={FETCH_NOW_URL} terminal=false"
    )
