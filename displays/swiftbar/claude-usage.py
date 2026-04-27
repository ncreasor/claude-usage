#!/usr/bin/env python3
import io
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".claude-usage"))
from claude_shared import (  # noqa: E402
    BAR_H, CANVAS_PAD, CMP_BAR_GAP, FETCH_NOW_URL,
    SCALE, STD_BAR_W, STD_FONT_SIZE, STD_LABEL_GAP, THEMES,
    b64img, draw_progress_bar, load_config, load_data, load_font, load_update_info,
    print_settings_dropdown, text_width, time_remaining,
)

from PIL import Image, ImageDraw

STALE_AFTER_SEC = 600
STD_PAIR_GAP = 14 * SCALE


def render_bars(sp, sr, wp, wr, cfg, *, weekly_visible=True):
    theme = THEMES.get(cfg["theme"], THEMES["orange"])
    fill_color = theme["fill"]
    style = cfg.get("style", "standard")

    if style == "compact":
        if weekly_visible:
            total_h = CANVAS_PAD + BAR_H + CMP_BAR_GAP + BAR_H + CANVAS_PAD
        else:
            total_h = CANVAS_PAD + BAR_H + CANVAS_PAD
        img = Image.new("RGBA", (STD_BAR_W, total_h), (0, 0, 0, 0))
        draw_progress_bar(img, 0, CANVAS_PAD, fill_color, sp, STD_BAR_W)
        if weekly_visible:
            draw_progress_bar(img, 0, CANVAS_PAD + BAR_H + CMP_BAR_GAP, fill_color, wp, STD_BAR_W)
    else:
        text_color = (*theme["text"], 255)
        font = load_font(STD_FONT_SIZE)
        time_fmt = cfg.get("time_format", "rounded")
        s_pct = f"{sp}%" if sp is not None else "--"
        s_time = time_remaining(sr, time_fmt)
        w_pct = f"{wp}%" if wp is not None else "--"
        w_time = time_remaining(wr, time_fmt)
        ref_h = font.getbbox("0%")[3] - font.getbbox("0%")[1]

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


def main():
    cfg = load_config()
    settings_script = Path(__file__).parent / "claude-settings.py"
    refresh_action = (
        f"bash=/usr/bin/curl param1=-s param2=-X param3=POST "
        f"param4={FETCH_NOW_URL} terminal=false"
    )
    click_action = cfg.get("click_action", "refresh")

    data = load_data()
    if data is None:
        if click_action == "settings":
            print("| sfimage=exclamationmark.circle")
            print_settings_dropdown(cfg, settings_script, None, None, None, None, None)
        else:
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

    latest_version = load_update_info()
    show_weekly = cfg.get("show_weekly", True)
    img = b64img(render_bars(sp, sr, wp, wr, cfg, weekly_visible=show_weekly))

    if click_action == "settings":
        print(f"| image={img}")
        print_settings_dropdown(cfg, settings_script, sp, sr, wp, wr, latest_version)
    else:
        print(f"| image={img} {refresh_action}")


if __name__ == "__main__":
    main()
