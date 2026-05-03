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
    cfg = {"style": "compact", "theme": "blue", "time_format": "rounded"}
    from datetime import datetime, timezone, timedelta
    sr = (datetime.now(timezone.utc) + timedelta(hours=2, minutes=14)).isoformat()
    wr = (datetime.now(timezone.utc) + timedelta(days=5, hours=1)).isoformat()

    bar_png = render_bars(65, sr, 32, wr, cfg, weekly_visible=True)
    bar_img = _png_to_image(bar_png)
    bw = bar_img.width // SCALE_P

    strip_h = 24
    fn = _font(11)

    # Measure system icons to size canvas tightly
    dummy = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    sys_items = ["Sat 3 May", "9:41 PM"]
    sys_w = sum(int(dummy.textlength(t, font=fn)) for t in sys_items) + 14 * SCALE_P * len(sys_items)

    GAP = 16   # pts between bar and system icons
    strip_w = bw + GAP + sys_w // SCALE_P + 12
    canvas_w = strip_w * SCALE_P
    canvas_h = strip_h * SCALE_P

    canvas = Image.new("RGBA", (canvas_w, canvas_h), MENU_BG)

    bar_x = 8 * SCALE_P
    bar_y = (canvas_h - bar_img.height) // 2
    canvas.alpha_composite(bar_img, (bar_x, bar_y))

    draw = ImageDraw.Draw(canvas)
    rx = canvas_w - 12 * SCALE_P
    for label in reversed(sys_items):
        tw = int(draw.textlength(label, font=fn))
        rx -= tw
        draw.text((rx, canvas_h // 2), label, font=fn, fill=TEXT_SECONDARY, anchor="lm")
        rx -= 14 * SCALE_P

    canvas.save(OUT / "preview.png")
    print("preview.png saved")


# ── settings.png — compact dropdown + Visibility submenu ─────────────────────

def _rounded_panel(w_pts: int, h_pts: int, color=DROPDOWN_BG, radius_pts: int = 10):
    w, h, r = w_pts * SCALE_P, h_pts * SCALE_P, radius_pts * SCALE_P
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    bg  = Image.new("RGBA", (w, h), color)
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle([(0, 0), (w - 1, h - 1)], radius=r, fill=255)
    img.paste(bg, mask=mask)
    return img, mask


def make_settings():
    cfg_blue = {"style": "compact", "theme": "blue", "time_format": "rounded"}
    from datetime import datetime, timezone, timedelta
    sr = (datetime.now(timezone.utc) + timedelta(hours=2, minutes=14)).isoformat()
    wr = (datetime.now(timezone.utc) + timedelta(days=5, hours=1)).isoformat()

    BAR_PAD = 14
    bar_w_px = DROPDOWN_W * SCALE_P
    font_bar = load_font(STD_FONT_SIZE)

    pcts = ["65%", "32%"]
    times = ["2h", "5d"]
    prefix_col_w = max(text_width(font_bar, c) for c in ("s", "w")) + STD_LABEL_GAP
    bar_x = prefix_col_w + max(text_width(font_bar, p) for p in pcts) + STD_LABEL_GAP
    time_col_w = STD_LABEL_GAP + max(text_width(font_bar, t) for t in times)

    # Use standard cfg for dropdown bars (compact style only affects status bar icon)
    cfg_bar = {**cfg_blue, "style": "standard"}
    s_bar = _png_to_image(render_weekly_bar(65, sr, cfg_bar, bar_w_px, bar_x=bar_x, time_col_w=time_col_w, prefix="s", prefix_col_w=prefix_col_w))
    w_bar = _png_to_image(render_weekly_bar(32, wr, cfg_bar, bar_w_px, bar_x=bar_x, time_col_w=time_col_w, prefix="w", prefix_col_w=prefix_col_w))
    bar_img_h = s_bar.height // SCALE_P

    # Main dropdown rows; "highlighted" = blue bg row
    rows = [
        ("item",        "v1.9.0"),
        ("item",        "Refresh now"),
        ("sep",         ""),
        ("bar_img",     s_bar),
        ("bar_img",     w_bar),
        ("sep",         ""),
        ("item_grey",   "Session · 24h"),
        ("item_grey",   "Weekly · 7d"),
        ("sep",         ""),
        ("highlighted", "Settings"),
        ("item_arrow",  "About"),
        ("sep",         ""),
        ("item",        "Quit"),
    ]

    def row_h(r):
        if r[0] == "sep":     return SEP_H
        if r[0] == "bar_img": return bar_img_h + 2
        return ITEM_H

    total_h = sum(row_h(r) for r in rows) + 8
    main_w   = DROPDOWN_W + BAR_PAD * 2

    main_panel, main_mask = _rounded_panel(main_w, total_h)
    draw = ImageDraw.Draw(main_panel)
    fn_normal = _font(13)
    fn_small  = _font(11)

    y = 4
    settings_cy = 0
    for row_type, content in rows:
        h = row_h((row_type, content))
        cy = (y + h // 2) * SCALE_P
        lx = (SIDE_PAD + BAR_PAD) * SCALE_P
        rx = (DROPDOWN_W + BAR_PAD - SIDE_PAD) * SCALE_P

        if row_type == "sep":
            draw.line([(lx, (y + h // 2) * SCALE_P), (rx, (y + h // 2) * SCALE_P)],
                      fill=SEP_COLOR, width=1)

        elif row_type == "bar_img":
            img = content
            main_panel.alpha_composite(img, (BAR_PAD * SCALE_P,
                                             y * SCALE_P + (h * SCALE_P - img.height) // 2))

        elif row_type == "highlighted":
            settings_cy = cy
            hy = y * SCALE_P
            hh = h * SCALE_P
            hl = Image.new("RGBA", (main_panel.width, hh), (50, 110, 215, 255))
            main_panel.alpha_composite(hl, (0, hy))
            draw.text((lx, cy), content, font=fn_normal, fill=TEXT_PRIMARY, anchor="lm")
            draw.text((rx, cy), "›", font=fn_normal, fill=(200, 200, 255, 255), anchor="rm")

        elif row_type == "item":
            draw.text((lx, cy), content, font=fn_normal, fill=TEXT_PRIMARY, anchor="lm")

        elif row_type == "item_grey":
            draw.text((lx, cy), content, font=fn_small, fill=TEXT_SECONDARY, anchor="lm")

        elif row_type == "item_arrow":
            draw.text((lx, cy), content, font=fn_normal, fill=TEXT_PRIMARY, anchor="lm")
            draw.text((rx, cy), "›", font=fn_normal, fill=TEXT_SECONDARY, anchor="rm")

        y += h

    # ── Visibility submenu panel ──────────────────────────────────────────────
    vis_rows = [
        ("check", True,  "Show Weekly Bar"),
        ("check", True,  "Show History"),
        ("check", False, "Show Claude Design"),
        ("check", False, "Show Extra Usage"),
        ("sep",   None,  ""),
        ("item",  None,  "Enable Extra Usage"),
    ]

    def vis_row_h(r): return SEP_H if r[0] == "sep" else ITEM_H
    vis_total_h = sum(vis_row_h(r) for r in vis_rows) + 8
    sub_w = 210
    sub_panel, sub_mask = _rounded_panel(sub_w, vis_total_h, color=(48, 48, 48, 255))
    sdraw = ImageDraw.Draw(sub_panel)

    DOT_R     = 3 * SCALE_P   # checkmark dot radius
    CHECK_CX  = 9 * SCALE_P   # center x of checkmark column
    text_lx   = 18 * SCALE_P
    sub_lx    = 8 * SCALE_P
    sub_rx    = (sub_w - 8) * SCALE_P

    vy = 4
    for kind, checked, label in vis_rows:
        h = vis_row_h((kind, checked, label))
        cy = (vy + h // 2) * SCALE_P
        if kind == "sep":
            sdraw.line([(sub_lx, cy), (sub_rx, cy)], fill=SEP_COLOR, width=1)
        else:
            if checked:
                sdraw.ellipse(
                    [(CHECK_CX - DOT_R, cy - DOT_R), (CHECK_CX + DOT_R, cy + DOT_R)],
                    fill=TEXT_PRIMARY,
                )
            sdraw.text((text_lx, cy), label, font=fn_normal, fill=TEXT_PRIMARY, anchor="lm")
        vy += h

    # ── Compose final image ───────────────────────────────────────────────────
    SHADOW = 14
    OVERLAP = 4

    # Position submenu aligned to Settings row
    sub_x_pts = main_w - OVERLAP
    sub_y_pts = max(0, settings_cy // SCALE_P - ITEM_H // 2 - 4)
    sub_bottom = sub_y_pts + vis_total_h

    total_w_pts    = sub_x_pts + sub_w + SHADOW
    total_h_pts    = max(total_h, sub_bottom) + SHADOW

    result = Image.new("RGBA", (total_w_pts * SCALE_P, total_h_pts * SCALE_P), (0, 0, 0, 0))

    sh_main = Image.new("RGBA", (main_panel.width, main_panel.height), (0, 0, 0, 70))
    sh_main.putalpha(main_mask)
    result.alpha_composite(sh_main, (SHADOW * SCALE_P // 2, SHADOW * SCALE_P // 2))
    result.alpha_composite(main_panel, (0, 0))

    sub_x = sub_x_pts * SCALE_P
    sub_y = sub_y_pts * SCALE_P

    sh_sub = Image.new("RGBA", (sub_panel.width, sub_panel.height), (0, 0, 0, 70))
    sh_sub.putalpha(sub_mask)
    result.alpha_composite(sh_sub, (sub_x + SHADOW * SCALE_P // 2, sub_y + SHADOW * SCALE_P // 2))
    result.alpha_composite(sub_panel, (sub_x, sub_y))

    result.save(OUT / "settings.png")
    print("settings.png saved")


if __name__ == "__main__":
    make_preview()
    make_settings()
