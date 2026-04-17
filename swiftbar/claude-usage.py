#!/usr/bin/env python3
import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".claude-usage"))
from claude_shared import (  # noqa: E402
    BAR_H, CANVAS_PAD, CMP_BAR_W, CMP_COL_GAP, CMP_FONT_SIZE, CMP_TEXT_BAR_GAP,
    DATA_FILE, INTERVALS, SCALE, STD_BAR_W, STD_FONT_SIZE, STD_LABEL_GAP,
    THEME_NAMES, THEMES, TRACK_COLOR, UPDATE_URL, VERSION,
    b64img, draw_progress_bar, load_config, load_font, render_weekly_bar,
    text_width, time_remaining,
)

from PIL import Image, ImageDraw

FETCH_NOW_URL = "http://127.0.0.1:18247/fetch-now"
STALE_AFTER_SEC = 600
STD_PAIR_GAP = 14 * SCALE


def render_bars(sp, sr, wp, wr, cfg, *, weekly_visible=True):
    theme = THEMES.get(cfg["theme"], THEMES["orange"])
    fill_color = theme["fill"]
    text_color = (*theme["text"], 255)
    style = cfg.get("style", "standard")
    font = load_font(STD_FONT_SIZE if style == "standard" else CMP_FONT_SIZE)

    time_fmt = cfg.get("time_format", "rounded")
    s_pct = f"{sp}%" if sp is not None else "--"
    s_time = time_remaining(sr, time_fmt)
    w_pct = f"{wp}%" if wp is not None else "--"
    w_time = time_remaining(wr, time_fmt)

    ref_h = font.getbbox("0%")[3] - font.getbbox("0%")[1]

    if style == "compact":
        s_lbl = f"{s_pct} {s_time}".strip()
        col_w_s = max(CMP_BAR_W, text_width(font, s_lbl))

        if weekly_visible:
            w_lbl = f"{w_pct} {w_time}".strip()
            col_w_w = max(CMP_BAR_W, text_width(font, w_lbl))
            total_w = col_w_s + CMP_COL_GAP + col_w_w
        else:
            total_w = col_w_s

        total_h = CANVAS_PAD + BAR_H + CMP_TEXT_BAR_GAP + ref_h + CANVAS_PAD
        img = Image.new("RGBA", (total_w, total_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        ty_bar = CANVAS_PAD
        ty_text = ty_bar + BAR_H + CMP_TEXT_BAR_GAP

        tw_sl = text_width(font, s_lbl)
        bar_x_s = (col_w_s - CMP_BAR_W) // 2
        draw_progress_bar(img, bar_x_s, ty_bar, fill_color, sp, CMP_BAR_W)
        draw.text(((col_w_s - tw_sl) // 2, ty_text), s_lbl, font=font, fill=text_color, anchor="lt")

        if weekly_visible:
            tw_wl = text_width(font, w_lbl)
            x2 = col_w_s + CMP_COL_GAP
            bar_x_w = x2 + (col_w_w - CMP_BAR_W) // 2
            draw_progress_bar(img, bar_x_w, ty_bar, fill_color, wp, CMP_BAR_W)
            draw.text((x2 + (col_w_w - tw_wl) // 2, ty_text), w_lbl, font=font, fill=text_color, anchor="lt")
    else:
        tw_sp = text_width(font, s_pct)
        tw_st = text_width(font, s_time)
        tw_wp = text_width(font, w_pct)
        tw_wt = text_width(font, w_time)

        total_h = max(ref_h, BAR_H) + CANVAS_PAD * 2

        def pair_w(tw_pct, tw_time):
            return tw_pct + STD_LABEL_GAP + STD_BAR_W + (STD_LABEL_GAP + tw_time if tw_time else 0)

        total_w = pair_w(tw_sp, tw_st) + (STD_PAIR_GAP + pair_w(tw_wp, tw_wt) if weekly_visible else 0)

        img = Image.new("RGBA", (total_w, total_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        cy = total_h // 2
        ty_bar = cy - BAR_H // 2

        def draw_pair(x, pct_lbl, time_lbl, tw_pct, tw_time, pct):
            draw.text((x, cy), pct_lbl, font=font, fill=text_color, anchor="lm")
            bx = x + tw_pct + STD_LABEL_GAP
            draw_progress_bar(img, bx, ty_bar, fill_color, pct, STD_BAR_W)
            end_x = bx + STD_BAR_W
            if time_lbl:
                end_x += STD_LABEL_GAP
                draw.text((end_x, cy), time_lbl, font=font, fill=text_color, anchor="lm")
                end_x += tw_time
            return end_x

        end1 = draw_pair(0, s_pct, s_time, tw_sp, tw_st, sp)
        if weekly_visible:
            draw_pair(end1 + STD_PAIR_GAP, w_pct, w_time, tw_wp, tw_wt, wp)

    buf = io.BytesIO()
    img.save(buf, format="PNG", dpi=(round(SCALE * 72), round(SCALE * 72)))
    return buf.getvalue()


_BOOL_KEYS = {"show_weekly"}


def _cfg_matches(cfg_val, opt_val):
    if isinstance(cfg_val, bool):
        return cfg_val == (opt_val == "true")
    return cfg_val == opt_val


def _settings_opt(label, key, value, cfg):
    mark = "✓" if _cfg_matches(cfg[key], value) else " "
    py = sys.executable
    settings_pl = Path(__file__).parent / "claude-settings.py"
    return (
        f"-- {mark} {label} | bash={py} param1={settings_pl} "
        f"param2=--set param3={key} param4={value} "
        f"terminal=false refresh=true"
    )


def _print_settings_dropdown(cfg, wp=None, wr=None, latest_version=None):
    print("---")
    if latest_version:
        print(
            f"v{VERSION} → v{latest_version} | bash=/usr/bin/curl "
            f"param1=-s param2=-X param3=POST param4={UPDATE_URL} "
            f"terminal=false color=#ff9500"
        )
    else:
        print(f"v{VERSION} | color=#888888")
    print("---")
    if not cfg.get("show_weekly", True):
        weekly_img = b64img(render_weekly_bar(wp, wr, cfg))
        print(f"Weekly | image={weekly_img}")
        print("---")
    print("Style")
    print(_settings_opt("Standard", "style", "standard", cfg))
    print(_settings_opt("Compact", "style", "compact", cfg))
    print("Color")
    for theme in THEME_NAMES:
        print(_settings_opt(theme.capitalize(), "theme", theme, cfg))
    print("Refresh Interval")
    for mins in INTERVALS:
        label = f"{mins} min" if mins > 1 else "1 min"
        print(_settings_opt(label, "fetch_interval_minutes", mins, cfg))
    print("Time Format")
    print(_settings_opt("Rounded  (5m, 2h)", "time_format", "rounded", cfg))
    print(_settings_opt("Exact  (4m32s, 1h23m)", "time_format", "exact", cfg))
    print("Weekly Bar")
    print(_settings_opt("Show", "show_weekly", "true", cfg))
    print(_settings_opt("Hide (show in settings)", "show_weekly", "false", cfg))
    print("Bar Click Action")
    print(_settings_opt("Refresh data", "click_action", "refresh", cfg))
    print(_settings_opt("Open settings (hide gear)", "click_action", "settings", cfg))
    print("---")
    print(
        f"Refresh now | bash=/usr/bin/curl param1=-s param2=-X "
        f"param3=POST param4={FETCH_NOW_URL} terminal=false"
    )


def main():
    cfg = load_config()
    refresh_action = (
        f"bash=/usr/bin/curl param1=-s param2=-X param3=POST "
        f"param4={FETCH_NOW_URL} terminal=false"
    )
    click_action = cfg.get("click_action", "refresh")

    if not DATA_FILE.exists():
        print(f"| {refresh_action}")
        return

    try:
        data = json.loads(DATA_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        print(f"| {refresh_action}")
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

    latest_version = None
    if data.get("update_available") and data.get("latest_version"):
        latest_version = data["latest_version"]

    show_weekly = cfg.get("show_weekly", True)
    img = b64img(render_bars(sp, sr, wp, wr, cfg, weekly_visible=show_weekly))

    if click_action == "settings":
        print(f"| image={img}")
        _print_settings_dropdown(cfg, wp, wr, latest_version)
    else:
        print(f"| image={img} {refresh_action}")


if __name__ == "__main__":
    main()
