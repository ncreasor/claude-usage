import io
import json
import math
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

VERSION = "1.8.0"
PORT = 18247
UPDATE_URL = f"http://127.0.0.1:{PORT}/update"
CHECK_UPDATE_URL = f"http://127.0.0.1:{PORT}/check-update"
FETCH_NOW_URL = f"http://127.0.0.1:{PORT}/fetch-now"
TOGGLE_EXTRA_URL = f"http://127.0.0.1:{PORT}/toggle-extra-usage"

CONFIG_FILE = Path.home() / ".claude-usage" / "config.json"
DATA_FILE = Path.home() / ".claude-usage" / "data.json"
HISTORY_FILE = Path.home() / ".claude-usage" / "history.jsonl"
HISTORY_MAX_DAYS = 7
HISTORY_PRUNE_BYTES = 500_000

THEME_NAMES = ["orange", "blue", "green", "purple", "red", "teal", "pink", "yellow"]
INTERVALS = [1, 2, 5, 10, 15, 30]

DEFAULT_CONFIG = {
    "style": "standard",
    "theme": "orange",
    "fetch_interval_minutes": 5,
    "time_format": "rounded",
    "show_weekly": True,
    "show_history": True,
    "show_claude_design": False,
    "show_extra_usage": False,
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
STD_PAIR_GAP = 14 * SCALE

CMP_BAR_GAP = 2 * SCALE

CHART_W = 180 * SCALE
CHART_H = 48 * SCALE
CHART_PAD = 5 * SCALE
CHART_LINE_W = 2
CHART_LABEL_SIZE = 10 * SCALE
CHART_LABEL_H = 14 * SCALE
CHART_TIME_FONT_SIZE = 9 * SCALE
CHART_TIME_H = 13 * SCALE

_FONT_PATHS = [
    "/System/Library/Fonts/Helvetica.ttc",
    "/System/Library/Fonts/SFNS.ttf",
    "/System/Library/Fonts/SFNSText.ttf",
]


def _system_uses_24h() -> bool:
    try:
        r = subprocess.run(
            ["defaults", "read", "NSGlobalDomain", "AppleICUForce24HourTime"],
            capture_output=True, text=True, timeout=2,
        )
        if r.returncode == 0:
            return r.stdout.strip() != "0"
    except Exception:
        pass
    return True


def _chart_ticks(
    t_start: float, t_end: float, max_hours: float, use_12h: bool, chart_w: int = CHART_W
) -> list[tuple[int, str]]:
    span = max(t_end - t_start, 1)
    pw = chart_w - 2 * CHART_PAD
    tz_offset = datetime.now().astimezone().utcoffset().total_seconds()
    step = 6 * 3600 if max_hours <= 24 else 86400
    local_start = t_start + tz_offset
    t = (math.floor(local_start / step) + 1) * step - tz_offset
    ticks: list[tuple[int, str]] = []
    while t < t_end:
        x = CHART_PAD + round((t - t_start) / span * pw)
        dt = datetime.fromtimestamp(t)
        if max_hours <= 24:
            if use_12h:
                h = dt.hour % 12 or 12
                suffix = "AM" if dt.hour < 12 else "PM"
                label = f"{h}{suffix}"
            else:
                label = dt.strftime("%H:%M")
        else:
            label = dt.strftime("%a")
        ticks.append((x, label))
        t += step
    return ticks


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


def render_bars(sp, sr, wp, wr, cfg, *, weekly_visible=True, bar_width=None):
    theme = THEMES.get(cfg["theme"], THEMES["orange"])
    fill_color = theme["fill"]
    style = cfg.get("style", "standard")
    bar_w = bar_width if bar_width is not None else STD_BAR_W

    if style == "compact":
        if weekly_visible:
            total_h = CANVAS_PAD + BAR_H + CMP_BAR_GAP + BAR_H + CANVAS_PAD
        else:
            total_h = CANVAS_PAD + BAR_H + CANVAS_PAD
        img = Image.new("RGBA", (bar_w, total_h), (0, 0, 0, 0))
        draw_progress_bar(img, 0, CANVAS_PAD, fill_color, sp, bar_w)
        if weekly_visible:
            draw_progress_bar(img, 0, CANVAS_PAD + BAR_H + CMP_BAR_GAP, fill_color, wp, bar_w)
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
            return tw_pct + STD_LABEL_GAP + bar_w + (STD_LABEL_GAP + tw_time if tw_time else 0)

        total_w = pair_w(tw_sp, tw_st) + (STD_PAIR_GAP + pair_w(tw_wp, tw_wt) if weekly_visible else 0)

        img = Image.new("RGBA", (total_w, total_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        cy = total_h // 2
        ty_bar = cy - BAR_H // 2

        def draw_pair(x, pct_lbl, time_lbl, tw_pct, tw_time, pct):
            draw.text((x, cy), pct_lbl, font=font, fill=text_color, anchor="lm")
            bx = x + tw_pct + STD_LABEL_GAP
            draw_progress_bar(img, bx, ty_bar, fill_color, pct, bar_w)
            end_x = bx + bar_w
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


_PREFIX_COLOR = (130, 130, 130, 255)


def render_weekly_bar(wp, wr, cfg, bar_width=None, *, bar_x: int | None = None, time_col_w: int = 0, label_override: str | None = None, right_label: str | None = None, prefix: str | None = None, prefix_col_w: int = 0):
    theme = THEMES.get(cfg["theme"], THEMES["orange"])
    fill_color = theme["fill"]
    text_color = (*theme["text"], 255)
    style = cfg.get("style", "standard")
    time_fmt = cfg.get("time_format", "rounded")
    bar_w = bar_width if bar_width is not None else STD_BAR_W

    w_pct = label_override if label_override is not None else (f"{wp}%" if wp is not None else "--")
    w_time = right_label if right_label is not None else time_remaining(wr, time_fmt)

    if style == "compact":
        total_h = CANVAS_PAD + BAR_H + CANVAS_PAD
        img = Image.new("RGBA", (bar_w, total_h), (0, 0, 0, 0))
        draw_progress_bar(img, 0, CANVAS_PAD, fill_color, wp, bar_w)
    else:
        font = load_font(STD_FONT_SIZE)
        ref_h = font.getbbox("0%")[3] - font.getbbox("0%")[1]
        tw_wt = text_width(font, w_time)
        total_h = max(ref_h, BAR_H) + CANVAS_PAD * 2
        pcol = prefix_col_w or (text_width(font, prefix) if prefix else 0)

        if bar_x is not None:
            total_w = bar_w
            bx = bar_x
            bar_w = max(STD_LABEL_GAP, total_w - bx - time_col_w)
        else:
            tw_wp = text_width(font, w_pct)
            bx = pcol + tw_wp + STD_LABEL_GAP
            total_w = bx + bar_w + (STD_LABEL_GAP + tw_wt if w_time else 0)

        img = Image.new("RGBA", (total_w, total_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        cy = total_h // 2
        if prefix:
            draw.text(((pcol - STD_LABEL_GAP) // 2, cy), prefix.strip(), font=font, fill=_PREFIX_COLOR, anchor="mm")
        draw.text((pcol, cy), w_pct, font=font, fill=text_color, anchor="lm")
        draw_progress_bar(img, bx, cy - BAR_H // 2, fill_color, wp, bar_w)
        if w_time:
            if bar_x is not None:
                draw.text((total_w, cy), w_time, font=font, fill=text_color, anchor="rm")
            else:
                draw.text((bx + bar_w + STD_LABEL_GAP, cy), w_time, font=font, fill=text_color, anchor="lm")

    buf = io.BytesIO()
    img.save(buf, format="PNG", dpi=(round(SCALE * 72), round(SCALE * 72)))
    return buf.getvalue()


def append_history(sp: int | None, wp: int | None) -> None:
    entry = json.dumps({"ts": datetime.now(timezone.utc).isoformat(), "sp": sp, "wp": wp})
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with HISTORY_FILE.open("a") as f:
        f.write(entry + "\n")
    try:
        if HISTORY_FILE.stat().st_size > HISTORY_PRUNE_BYTES:
            _prune_history()
    except OSError:
        pass


def _prune_history() -> None:
    entries = load_history(HISTORY_MAX_DAYS * 24)
    lines = [
        json.dumps({
            "ts": datetime.fromtimestamp(e["ts"], tz=timezone.utc).isoformat(),
            "sp": e["sp"],
            "wp": e["wp"],
        })
        for e in entries
    ]
    HISTORY_FILE.write_text("\n".join(lines) + ("\n" if lines else ""))


def load_history(max_hours: float = 24) -> list[dict]:
    if not HISTORY_FILE.exists():
        return []
    cutoff = datetime.now(timezone.utc).timestamp() - max_hours * 3600
    entries = []
    try:
        with HISTORY_FILE.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                    ts = datetime.fromisoformat(e["ts"]).timestamp()
                    if ts >= cutoff:
                        entries.append({"ts": ts, "sp": e.get("sp"), "wp": e.get("wp")})
                except (json.JSONDecodeError, KeyError, ValueError):
                    pass
    except OSError:
        pass
    return sorted(entries, key=lambda e: e["ts"])


def _chart_pts(
    entries: list[dict], key: str, t_start: float, t_end: float, chart_w: int
) -> list[tuple[int, int]]:
    pw = chart_w - 2 * CHART_PAD
    ph = CHART_H - 2 * CHART_PAD
    span = max(t_end - t_start, 1)
    pts = []
    for e in entries:
        v = e.get(key)
        if v is None:
            continue
        x = CHART_PAD + round((e["ts"] - t_start) / span * pw)
        y = (CHART_H - CHART_PAD) - round(v / 100 * ph)
        pts.append((x, y))
    return pts


def render_history_chart(
    entries: list[dict], key: str, max_hours: float, cfg: dict, label: str,
    chart_w: int = CHART_W,
) -> bytes:
    theme = THEMES.get(cfg.get("theme", "orange"), THEMES["orange"])
    fc = theme["fill"]

    now = datetime.now(timezone.utc).timestamp()
    t_start = now - max_hours * 3600
    t_end = now

    chart = Image.new("RGBA", (chart_w, CHART_H), (0, 0, 0, 0))
    cdraw = ImageDraw.Draw(chart)

    left = CHART_PAD
    right = chart_w - CHART_PAD
    top = CHART_PAD
    bottom = CHART_H - CHART_PAD

    use_12h = not _system_uses_24h()
    ticks = _chart_ticks(t_start, t_end, max_hours, use_12h, chart_w)

    GRID = (80, 80, 80, 65)
    cdraw.line([(left, top + (bottom - top) // 2), (right, top + (bottom - top) // 2)], fill=GRID, width=1)

    for gx, _ in ticks:
        cdraw.line([(gx, top), (gx, bottom)], fill=GRID, width=1)

    pts = _chart_pts(entries, key, t_start, t_end, chart_w)

    if len(pts) >= 2:
        last_real = pts[-1]
        if last_real[0] < right:
            pts = pts + [(right, last_real[1])]

        poly = [(left, bottom)] + pts + [(pts[-1][0], bottom)]
        fill_layer = Image.new("RGBA", (chart_w, CHART_H), (0, 0, 0, 0))
        ImageDraw.Draw(fill_layer).polygon(poly, fill=(*fc, 55))
        chart.alpha_composite(fill_layer)

        line_layer = Image.new("RGBA", (chart_w, CHART_H), (0, 0, 0, 0))
        ImageDraw.Draw(line_layer).line(pts, fill=(*fc, 210), width=CHART_LINE_W)
        chart.alpha_composite(line_layer)

        lx, ly = pts[-1]
        r = CHART_LINE_W + 2
        cdraw.ellipse([(lx - r, ly - r), (lx + r, ly + r)], fill=(*fc, 255))

    total_h = CHART_LABEL_H + CHART_H + CHART_TIME_H
    img = Image.new("RGBA", (chart_w, total_h), (0, 0, 0, 0))
    font = load_font(CHART_LABEL_SIZE)
    time_font = load_font(CHART_TIME_FONT_SIZE)
    idraw = ImageDraw.Draw(img)
    idraw.text(
        (CHART_PAD, CHART_LABEL_H // 2),
        label,
        font=font,
        fill=(160, 160, 160, 200),
        anchor="lm",
    )
    img.alpha_composite(chart, dest=(0, CHART_LABEL_H))

    ty = CHART_LABEL_H + CHART_H + CHART_TIME_H // 2
    for gx, time_label in ticks:
        idraw.text((gx, ty), time_label, font=time_font, fill=(130, 130, 130, 170), anchor="mm")

    buf = io.BytesIO()
    img.save(buf, format="PNG", dpi=(round(SCALE * 72), round(SCALE * 72)))
    return buf.getvalue()


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
        latest = data["latest_version"]
        if latest != VERSION:
            return latest
    return None


