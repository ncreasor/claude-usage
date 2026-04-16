#!/usr/bin/env python3
import base64
import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".claude-usage"))
from claude_shared import DATA_FILE, load_config  # noqa: E402

from PIL import Image, ImageDraw, ImageFont

FETCH_NOW_URL = "http://127.0.0.1:18247/fetch-now"

SCALE = 2
STALE_AFTER_SEC = 600

STD_FONT_SIZE = 13 * SCALE
CMP_FONT_SIZE = 11 * SCALE
BAR_H = 3 * SCALE
BAR_R = 1 * SCALE
CANVAS_PAD = 2 * SCALE
TRACK_COLOR = (75, 75, 75, 180)

# Standard (E-style)
STD_BAR_W = 52 * SCALE
STD_LABEL_GAP = 5 * SCALE
STD_PAIR_GAP = 14 * SCALE

# Compact (C-style)
CMP_BAR_W = 40 * SCALE
CMP_COL_GAP = 10 * SCALE
CMP_TEXT_BAR_GAP = 3 * SCALE

_FONT_PATHS = [
    "/System/Library/Fonts/Helvetica.ttc",
    "/System/Library/Fonts/SFNS.ttf",
    "/System/Library/Fonts/SFNSText.ttf",
]

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


def _load_font(size):
    for path in _FONT_PATHS:
        try:
            return ImageFont.truetype(path, size=size)
        except (OSError, IOError):
            pass
    return ImageFont.load_default(size=size)


def time_remaining(iso_str):
    if not iso_str:
        return ""
    try:
        dt = datetime.fromisoformat(iso_str)
        delta = dt - datetime.now(tz=dt.tzinfo or timezone.utc)
        secs = delta.total_seconds()
        if secs <= 0:
            return ""
        mins = secs / 60
        if mins < 60:
            return f"{round(mins)}m"
        hours = mins / 60
        if hours < 24:
            return f"{round(hours)}h"
        return f"{round(hours / 24)}d"
    except ValueError:
        return ""


def _tw(font, text):
    if not text:
        return 0
    bbox = font.getbbox(text)
    return bbox[2] - bbox[0]


def _draw_progress_bar(img, x0, y0, fill_color, pct, bar_w):
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([x0, y0, x0 + bar_w, y0 + BAR_H], radius=BAR_R, fill=TRACK_COLOR)
    fill_w = max(0, min(bar_w, round(bar_w * pct / 100))) if pct is not None else 0
    if fill_w > 0:
        temp = Image.new("RGBA", img.size, (0, 0, 0, 0))
        tdraw = ImageDraw.Draw(temp)
        tdraw.rounded_rectangle([x0, y0, x0 + bar_w, y0 + BAR_H], radius=BAR_R, fill=(*fill_color, 255))
        tdraw.rectangle([x0 + fill_w, 0, x0 + bar_w + 1, img.height], fill=(0, 0, 0, 0))
        img.alpha_composite(temp)


def render_bars(sp, sr, wp, wr, cfg):
    theme = THEMES.get(cfg["theme"], THEMES["orange"])
    fill_color = theme["fill"]
    text_color = (*theme["text"], 255)
    style = cfg.get("style", "standard")
    font = _load_font(STD_FONT_SIZE if style == "standard" else CMP_FONT_SIZE)

    s_pct = f"{sp}%" if sp is not None else "--"
    s_time = time_remaining(sr)
    w_pct = f"{wp}%" if wp is not None else "--"
    w_time = time_remaining(wr)

    ref_bbox = font.getbbox("0%")
    ref_h = ref_bbox[3] - ref_bbox[1]

    if style == "compact":
        s_lbl = f"{s_pct} {s_time}".strip()
        w_lbl = f"{w_pct} {w_time}".strip()
        tw_sl = _tw(font, s_lbl)
        tw_wl = _tw(font, w_lbl)

        col_w_s = max(CMP_BAR_W, tw_sl)
        col_w_w = max(CMP_BAR_W, tw_wl)
        total_w = col_w_s + CMP_COL_GAP + col_w_w
        total_h = CANVAS_PAD + BAR_H + CMP_TEXT_BAR_GAP + ref_h + CANVAS_PAD

        img = Image.new("RGBA", (total_w, total_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        ty_bar = CANVAS_PAD
        ty_text = ty_bar + BAR_H + CMP_TEXT_BAR_GAP

        bar_x_s = (col_w_s - CMP_BAR_W) // 2
        _draw_progress_bar(img, bar_x_s, ty_bar, fill_color, sp, CMP_BAR_W)
        draw.text(((col_w_s - tw_sl) // 2, ty_text), s_lbl, font=font, fill=text_color, anchor="lt")

        x2 = col_w_s + CMP_COL_GAP
        bar_x_w = x2 + (col_w_w - CMP_BAR_W) // 2
        _draw_progress_bar(img, bar_x_w, ty_bar, fill_color, wp, CMP_BAR_W)
        draw.text((x2 + (col_w_w - tw_wl) // 2, ty_text), w_lbl, font=font, fill=text_color, anchor="lt")
    else:
        tw_sp = _tw(font, s_pct)
        tw_st = _tw(font, s_time)
        tw_wp = _tw(font, w_pct)
        tw_wt = _tw(font, w_time)

        total_h = max(ref_h, BAR_H) + CANVAS_PAD * 2

        def pair_w(tw_pct, tw_time):
            return tw_pct + STD_LABEL_GAP + STD_BAR_W + (STD_LABEL_GAP + tw_time if tw_time else 0)

        total_w = pair_w(tw_sp, tw_st) + STD_PAIR_GAP + pair_w(tw_wp, tw_wt)

        img = Image.new("RGBA", (total_w, total_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        cy = total_h // 2
        ty_bar = cy - BAR_H // 2

        def draw_pair(x, pct_lbl, time_lbl, tw_pct, tw_time, pct):
            draw.text((x, cy), pct_lbl, font=font, fill=text_color, anchor="lm")
            bx = x + tw_pct + STD_LABEL_GAP
            _draw_progress_bar(img, bx, ty_bar, fill_color, pct, STD_BAR_W)
            end_x = bx + STD_BAR_W
            if time_lbl:
                end_x += STD_LABEL_GAP
                draw.text((end_x, cy), time_lbl, font=font, fill=text_color, anchor="lm")
                end_x += tw_time
            return end_x

        end1 = draw_pair(0, s_pct, s_time, tw_sp, tw_st, sp)
        draw_pair(end1 + STD_PAIR_GAP, w_pct, w_time, tw_wp, tw_wt, wp)

    buf = io.BytesIO()
    img.save(buf, format="PNG", dpi=(round(SCALE * 72), round(SCALE * 72)))
    return buf.getvalue()


def b64img(png_bytes):
    return base64.b64encode(png_bytes).decode()


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
