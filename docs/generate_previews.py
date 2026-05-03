#!/usr/bin/env python3
"""Generates docs/preview.png and docs/settings.png for the README."""

import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path.home() / ".claude-usage"))

from PIL import Image, ImageDraw, ImageFont
from claude_shared import (
    SCALE, STD_FONT_SIZE, STD_LABEL_GAP,
    load_font, render_bars, render_weekly_bar, text_width,
)

OUT = Path(__file__).parent

# ── Shared colours (dark mode) ───────────────────────────────────────────────

MENU_BG      = (30, 30, 30, 255)
DROPDOWN_BG  = (38, 38, 38, 255)
SEP_COLOR    = (80, 80, 80, 100)
TEXT_PRIMARY = (255, 255, 255, 255)
TEXT_SECONDARY = (160, 160, 160, 255)
HIGHLIGHT_BG = (60, 100, 180, 200)

DROPDOWN_W = 340   # pts
SCALE_P = 2        # preview HiDPI

ITEM_H    = 22     # pts, standard menu row
SEP_H     = 8      # pts, separator row
SIDE_PAD  = 18     # pts, left/right text padding


def _font(size_pts: int, bold: bool = False):
    paths = [
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/SFNS.ttf",
        "/System/Library/Fonts/SFNSText.ttf",
    ]
    for p in paths:
        try:
            idx = 1 if bold else 0
            return ImageFont.truetype(p, size_pts * SCALE_P, index=idx)
        except Exception:
            try:
                return ImageFont.truetype(p, size_pts * SCALE_P)
            except Exception:
                continue
    return ImageFont.load_default()


def _png_to_image(png_bytes: bytes) -> Image.Image:
    return Image.open(io.BytesIO(png_bytes)).convert("RGBA")


def _paste_centered_y(canvas: Image.Image, img: Image.Image, x: int, cy: int):
    y = cy - img.height // 2
    canvas.alpha_composite(img, (x, y))


# ── preview.png — menu bar strip ─────────────────────────────────────────────

def make_preview():
    cfg = {"style": "standard", "theme": "blue", "time_format": "rounded"}
    from datetime import datetime, timezone, timedelta
    sr = (datetime.now(timezone.utc) + timedelta(hours=2, minutes=14)).isoformat()
    wr = (datetime.now(timezone.utc) + timedelta(days=5, hours=1)).isoformat()

    bar_png = render_bars(65, sr, 32, wr, cfg, weekly_visible=True)
    bar_img = _png_to_image(bar_png)
    bw = bar_img.width // SCALE_P
    bh = bar_img.height // SCALE_P

    strip_w = bw + 220   # extra space for fake system icons
    strip_h = 24
    canvas_w = strip_w * SCALE_P
    canvas_h = strip_h * SCALE_P

    canvas = Image.new("RGBA", (canvas_w, canvas_h), MENU_BG)

    # Paste bar at left with small margin
    bar_x = 8 * SCALE_P
    bar_y = (canvas_h - bar_img.height) // 2
    canvas.alpha_composite(bar_img, (bar_x, bar_y))

    # Fake system icons on the right (text placeholders)
    draw = ImageDraw.Draw(canvas)
    fn = _font(11)
    items = ["Sat 3 May", "9:41 PM"]
    rx = canvas_w - 12 * SCALE_P
    for label in reversed(items):
        tw = draw.textlength(label, font=fn)
        rx -= int(tw)
        draw.text((rx, canvas_h // 2), label, font=fn, fill=TEXT_SECONDARY, anchor="lm")
        rx -= 14 * SCALE_P

    canvas.save(OUT / "preview.png")
    print("preview.png saved")


# ── settings.png — dropdown mockup ───────────────────────────────────────────

def make_settings():
    cfg_blue = {"style": "standard", "theme": "blue", "time_format": "rounded"}
    from datetime import datetime, timezone, timedelta
    sr = (datetime.now(timezone.utc) + timedelta(hours=2, minutes=14)).isoformat()
    wr = (datetime.now(timezone.utc) + timedelta(days=5, hours=1)).isoformat()

    BAR_PAD = 14   # pts — matches _IMG_PAD_X in the real app
    bar_w_px = DROPDOWN_W * SCALE_P
    font_bar = load_font(STD_FONT_SIZE)

    pcts = ["65%", "32%", "8%"]
    times = ["2h", "5d 1h"]
    prefix_col_w = max(text_width(font_bar, c) for c in ("s", "w", "d")) + STD_LABEL_GAP
    bar_x = prefix_col_w + max(text_width(font_bar, p) for p in pcts) + STD_LABEL_GAP
    time_col_w = STD_LABEL_GAP + max(text_width(font_bar, t) for t in times)

    s_bar = _png_to_image(render_weekly_bar(65, sr, cfg_blue, bar_w_px, bar_x=bar_x, time_col_w=time_col_w, prefix="s", prefix_col_w=prefix_col_w))
    w_bar = _png_to_image(render_weekly_bar(32, wr, cfg_blue, bar_w_px, bar_x=bar_x, time_col_w=time_col_w, prefix="w", prefix_col_w=prefix_col_w))
    d_bar = _png_to_image(render_weekly_bar(8,  None, cfg_blue, bar_w_px, bar_x=bar_x, time_col_w=time_col_w, prefix="d", prefix_col_w=prefix_col_w))

    bar_img_h = s_bar.height // SCALE_P

    rows = [
        ("item",       "v1.9.0"),
        ("item",       "Refresh now"),
        ("sep",        ""),
        ("bar_img",    s_bar),
        ("bar_img",    w_bar),
        ("bar_img",    d_bar),
        ("sep",        ""),
        ("item_grey",  "Session · 24h"),
        ("item_grey",  "Weekly · 7d"),
        ("sep",        ""),
        ("item_arrow", "Settings"),
        ("item_arrow", "About"),
        ("sep",        ""),
        ("item",       "Quit"),
    ]

    def row_height(r):
        if r[0] == "sep":      return SEP_H
        if r[0] == "bar_img":  return bar_img_h + 2
        return ITEM_H

    total_h = sum(row_height(r) for r in rows) + 8
    canvas_w = (DROPDOWN_W + BAR_PAD * 2) * SCALE_P
    canvas_h = total_h * SCALE_P

    # Rounded-rect background
    RADIUS = 10 * SCALE_P
    canvas = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    bg = Image.new("RGBA", (canvas_w, canvas_h), DROPDOWN_BG)
    mask = Image.new("L", (canvas_w, canvas_h), 0)
    ImageDraw.Draw(mask).rounded_rectangle([(0, 0), (canvas_w - 1, canvas_h - 1)], radius=RADIUS, fill=255)
    canvas.paste(bg, mask=mask)

    draw = ImageDraw.Draw(canvas)
    fn_normal = _font(13)
    fn_small  = _font(11)

    y = 4
    for row_type, content in rows:
        h = row_height((row_type, content))
        cy = (y + h // 2) * SCALE_P
        lx = (SIDE_PAD + BAR_PAD) * SCALE_P
        rx = (DROPDOWN_W + BAR_PAD - SIDE_PAD) * SCALE_P

        if row_type == "sep":
            ly = (y + h // 2) * SCALE_P
            draw.line([(lx, ly), (rx, ly)], fill=SEP_COLOR, width=1)

        elif row_type == "bar_img":
            img = content
            px = BAR_PAD * SCALE_P
            py = y * SCALE_P + (h * SCALE_P - img.height) // 2
            canvas.alpha_composite(img, (px, py))

        elif row_type == "item":
            draw.text((lx, cy), content, font=fn_normal, fill=TEXT_PRIMARY, anchor="lm")

        elif row_type == "item_grey":
            draw.text((lx, cy), content, font=fn_small, fill=TEXT_SECONDARY, anchor="lm")

        elif row_type == "item_arrow":
            draw.text((lx, cy), content, font=fn_normal, fill=TEXT_PRIMARY, anchor="lm")
            draw.text((rx, cy), "›", font=fn_normal, fill=TEXT_SECONDARY, anchor="rm")

        y += h

    # Subtle drop shadow via offset duplicate
    shadow = Image.new("RGBA", (canvas_w + 20, canvas_h + 20), (0, 0, 0, 0))
    shadow_layer = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 80))
    shadow_layer.putalpha(mask)
    shadow.alpha_composite(shadow_layer, (10, 10))
    result = shadow.copy()
    result.alpha_composite(canvas, (0, 0))

    result.save(OUT / "settings.png")
    print("settings.png saved")


if __name__ == "__main__":
    make_preview()
    make_settings()
