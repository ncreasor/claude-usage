#!/usr/bin/env python3
import json
import logging
import sys
import threading
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".claude-usage"))

import AppKit
from Foundation import NSAttributedString
import rumps

from claude_shared import (
    CHART_PAD, CHART_W, SCALE,
    CHECK_UPDATE_URL, FETCH_NOW_URL, HISTORY_MAX_DAYS, INTERVALS,
    STD_FONT_SIZE, STD_LABEL_GAP,
    THEME_NAMES, TOGGLE_EXTRA_URL, UPDATE_URL, VERSION,
    load_config, load_data, load_font, load_history, load_update_info,
    render_bars, render_history_chart, render_weekly_bar,
    save_config, text_width, time_remaining,
)

logging.basicConfig(
    filename=Path.home() / "Library" / "Logs" / "claude-usage-systray.log",
    level=logging.ERROR,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("claude-usage-systray")

GITHUB_URL = "https://github.com/ncreasor/claude-usage"

STALE_AFTER_SEC = 600
POLL_INTERVAL = 30
DROPDOWN_BAR_WIDTH = 340  # total image width in pixels (SCALE=2 → 280 pts); bar fills remaining space
CACHE = Path.home() / ".claude-usage" / "systray"

_ZWSP = "\u200b"
_IMG_PAD_X = 14
_IMG_PAD_Y = 4
# Charts have internal CHART_PAD on the left; subtract it so the label aligns with bar content
_CHART_PAD_PTS = CHART_PAD // SCALE
_CHART_PAD_X = _IMG_PAD_X - _CHART_PAD_PTS

# NSStatusItem / NSButton constants
_NS_VARIABLE_LENGTH = -1   # NSVariableStatusItemLength
_NS_IMAGE_ONLY = 2         # NSCellImagePosition.imageOnly
_NS_NO_IMAGE = 0            # NSCellImagePosition.noImage
_NS_IMAGE_SCALE_NONE = 2   # NSImageScaleNone

CLAUDE_USAGE_URL = "https://claude.ai/settings/usage"


class _MenuWidthDelegate(AppKit.NSObject):
    def menuWillOpen_(self, menu):
        menu.setMinimumWidth_(0)


class _WakeObserver(AppKit.NSObject):
    _callback = None

    def handleWake_(self, notification):
        if self._callback:
            self._callback()


def _apply_image_view(ns_item, png_bytes: bytes, pad_x: int = _IMG_PAD_X) -> None:
    try:
        data = AppKit.NSData.dataWithBytes_length_(png_bytes, len(png_bytes))
        image = AppKit.NSImage.alloc().initWithData_(data)
        if image is None:
            log.error("NSImage initWithData_ returned nil")
            return
        sz = image.size()
        iw, ih = sz.width, sz.height
        if iw <= 0 or ih <= 0:
            log.error("image has zero size: %s x %s", iw, ih)
            return

        img_view = AppKit.NSImageView.alloc().initWithFrame_(((pad_x, _IMG_PAD_Y), (iw, ih)))
        img_view.setImage_(image)
        img_view.setImageScaling_(_NS_IMAGE_SCALE_NONE)

        container = AppKit.NSView.alloc().initWithFrame_(
            ((0, 0), (iw + pad_x * 2, ih + _IMG_PAD_Y * 2))
        )
        container.addSubview_(img_view)
        ns_item.setView_(container)
    except Exception:
        log.exception("_apply_image_view failed")


def _extra_right(enabled: bool, account_balance: float | None) -> str:
    if not enabled:
        return "Off"
    if account_balance is not None:
        return f"${account_balance:.2f}"
    return "--"


def _earlier(a: str | None, b: str | None) -> str | None:
    if not a:
        return b
    if not b:
        return a
    try:
        return a if datetime.fromisoformat(a) <= datetime.fromisoformat(b) else b
    except ValueError:
        return a


class ClaudeUsageApp(rumps.App):
    def __init__(self):
        super().__init__("...", quit_button=None, template=False)
        AppKit.NSApplication.sharedApplication().setActivationPolicy_(
            AppKit.NSApplicationActivationPolicyAccessory
        )
        self._startup_done = False
        self._build_menu()

    # ── Menu construction ────────────────────────────────────────────────────

    def _build_menu(self):
        # Image-only items for bars and charts (ZWSP titles are unique but invisible)
        self._session_bar = rumps.MenuItem(_ZWSP)
        self._weekly_bar = rumps.MenuItem(_ZWSP * 2)
        self._design_bar = rumps.MenuItem(_ZWSP * 3)
        self._extra_bar = rumps.MenuItem(_ZWSP * 4)
        self._chart_session = rumps.MenuItem(_ZWSP * 5)
        self._chart_weekly = rumps.MenuItem(_ZWSP * 6)
        self._history_toggle = rumps.MenuItem("Hide history", callback=self._toggle_history)
        self._version_item = rumps.MenuItem(f"v{VERSION}", callback=self._on_version)

        # Style
        self._style_standard = rumps.MenuItem("Standard", callback=lambda _: self._set("style", "standard"))
        self._style_compact = rumps.MenuItem("Compact", callback=lambda _: self._set("style", "compact"))
        self._style_text = rumps.MenuItem("Text", callback=lambda _: self._set("style", "text"))
        style_menu = rumps.MenuItem("Style")
        style_menu.add(self._style_standard)
        style_menu.add(self._style_compact)
        style_menu.add(self._style_text)

        # Color
        self._theme_items: dict[str, rumps.MenuItem] = {}
        color_menu = rumps.MenuItem("Color")
        for name in THEME_NAMES:
            item = rumps.MenuItem(name.capitalize(), callback=self._make_cb("theme", name))
            self._theme_items[name] = item
            color_menu.add(item)

        # Refresh interval
        self._interval_items: dict[int, rumps.MenuItem] = {}
        interval_menu = rumps.MenuItem("Refresh Interval")
        for mins in INTERVALS:
            label = f"{mins} min" if mins > 1 else "1 min"
            item = rumps.MenuItem(label, callback=self._make_cb("fetch_interval_minutes", mins))
            self._interval_items[mins] = item
            interval_menu.add(item)

        # Time format
        self._fmt_rounded = rumps.MenuItem("Rounded  (3h, 6d)", callback=lambda _: self._set("time_format", "rounded"))
        self._fmt_exact = rumps.MenuItem("Exact  (1h 23m, 2d 6h)", callback=lambda _: self._set("time_format", "exact"))
        fmt_menu = rumps.MenuItem("Time Format")
        fmt_menu.add(self._fmt_rounded)
        fmt_menu.add(self._fmt_exact)

        # Visibility submenu
        self._weekly_show = rumps.MenuItem("Show Weekly Bar", callback=lambda _: self._set("show_weekly", not load_config().get("show_weekly", True)))
        self._history_show = rumps.MenuItem("Show History", callback=self._toggle_history)
        self._design_show = rumps.MenuItem("Show Claude Design", callback=lambda _: self._set("show_claude_design", not load_config().get("show_claude_design", False)))
        self._extra_show = rumps.MenuItem("Show Extra Usage", callback=lambda _: self._set("show_extra_usage", not load_config().get("show_extra_usage", False)))
        self._extra_toggle = rumps.MenuItem("Enable Extra Usage", callback=self._on_extra_toggle)
        visibility_menu = rumps.MenuItem("Visibility")
        visibility_menu.add(self._weekly_show)
        visibility_menu.add(self._history_show)
        visibility_menu.add(self._design_show)
        visibility_menu.add(self._extra_show)
        visibility_menu.add(None)
        visibility_menu.add(self._extra_toggle)

        settings = rumps.MenuItem("Settings")
        settings.add(style_menu)
        settings.add(color_menu)
        settings.add(None)
        settings.add(interval_menu)
        settings.add(fmt_menu)
        settings.add(None)
        settings.add(visibility_menu)

        self._refresh_item = rumps.MenuItem("Refresh now", callback=self._on_refresh)
        self._github_item = rumps.MenuItem("GitHub", callback=self._on_github)
        self._claude_item = rumps.MenuItem("Usage Page", callback=self._on_claude)
        about_menu = rumps.MenuItem("About")
        about_menu.add(self._github_item)
        about_menu.add(self._claude_item)

        self.menu = [
            self._version_item,
            self._refresh_item,
            None,
            self._session_bar,
            self._weekly_bar,
            self._design_bar,
            self._extra_bar,
            self._chart_session,
            self._chart_weekly,
            None,
            settings,
            about_menu,
            None,
            rumps.MenuItem("Quit", callback=self._on_quit),
        ]

    # ── Settings helpers ─────────────────────────────────────────────────────

    def _make_cb(self, key, value):
        return lambda _: self._set(key, value)

    def _set(self, key, value):
        save_config(key, value)
        self._update_display()

    def _toggle_history(self, _):
        self._set("show_history", not load_config().get("show_history", True))

    def _on_github(self, _):
        AppKit.NSWorkspace.sharedWorkspace().openURL_(
            AppKit.NSURL.URLWithString_(GITHUB_URL)
        )

    def _on_wake(self):
        self._on_refresh(None)

    def _on_claude(self, _):
        AppKit.NSWorkspace.sharedWorkspace().openURL_(
            AppKit.NSURL.URLWithString_(CLAUDE_USAGE_URL)
        )

    def _set_status_text(self, text: str) -> None:
        try:
            nsstatusitem = self._nsapp.nsstatusitem
            nsstatusitem.setLength_(_NS_VARIABLE_LENGTH)
            button = nsstatusitem.button()
            button.setImage_(None)
            button.setImagePosition_(_NS_NO_IMAGE)
            button.setTitle_(text)
        except Exception:
            log.exception("_set_status_text failed")

    def _on_quit(self, _):
        plist = Path.home() / "Library" / "LaunchAgents" / "com.claude.usage.systray.plist"
        import subprocess
        subprocess.Popen(
            ["/bin/launchctl", "unload", str(plist)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def _on_extra_toggle(self, _):
        data = load_data() or {}
        enabled = data.get("extra_usage_enabled", False)
        def _do():
            try:
                body = json.dumps({"enabled": not enabled}).encode()
                req = urllib.request.Request(
                    TOGGLE_EXTRA_URL,
                    data=body,
                    method="POST",
                    headers={"Content-Type": "application/json"},
                )
                urllib.request.urlopen(req, timeout=10)
            except Exception:
                log.exception("toggle extra usage failed")
            AppKit.NSOperationQueue.mainQueue().addOperationWithBlock_(
                lambda: self._update_display()
            )
        threading.Thread(target=_do, daemon=True).start()

    def _on_refresh(self, _):
        def _do():
            try:
                urllib.request.urlopen(
                    urllib.request.Request(FETCH_NOW_URL, method="POST"), timeout=5
                )
            except Exception:
                pass
            AppKit.NSOperationQueue.mainQueue().addOperationWithBlock_(
                lambda: self._update_display()
            )
        threading.Thread(target=_do, daemon=True).start()

    def _on_version(self, _):
        if getattr(self, '_update_in_flight', False):
            return
        self._update_in_flight = True
        url = UPDATE_URL if load_update_info() else CHECK_UPDATE_URL
        feedback = "Updating..." if url == UPDATE_URL else "Checking..."
        _grey = {AppKit.NSForegroundColorAttributeName: AppKit.NSColor.secondaryLabelColor()}
        self._version_item._menuitem.setAttributedTitle_(
            NSAttributedString.alloc().initWithString_attributes_(feedback, _grey)
        )
        is_check = url == CHECK_UPDATE_URL

        def _do():
            try:
                urllib.request.urlopen(
                    urllib.request.Request(url, method="POST"), timeout=5
                )
            except Exception:
                pass
            if is_check:
                import time as _time
                _time.sleep(4)
            def _done():
                self._update_in_flight = False
                self._update_display()
            AppKit.NSOperationQueue.mainQueue().addOperationWithBlock_(_done)
        threading.Thread(target=_do, daemon=True).start()

    # ── Sync checkmarks ──────────────────────────────────────────────────────

    def _sync_checks(self, cfg: dict) -> None:
        style = cfg.get("style", "standard")
        self._style_standard.state = style == "standard"
        self._style_compact.state = style == "compact"
        self._style_text.state = style == "text"

        theme = cfg.get("theme", "orange")
        for name, item in self._theme_items.items():
            item.state = name == theme

        interval = cfg.get("fetch_interval_minutes", 5)
        for mins, item in self._interval_items.items():
            item.state = mins == interval

        fmt = cfg.get("time_format", "rounded")
        self._fmt_rounded.state = fmt == "rounded"
        self._fmt_exact.state = fmt == "exact"

        self._weekly_show.state = cfg.get("show_weekly", True)

        self._design_show.state = cfg.get("show_claude_design", False)
        self._extra_show.state = cfg.get("show_extra_usage", False)
        self._history_show.state = cfg.get("show_history", True)

    # ── Status bar icon ──────────────────────────────────────────────────────

    def _set_status_icon(self, png_bytes: bytes) -> None:
        try:
            CACHE.mkdir(parents=True, exist_ok=True)
            p = CACHE / "status.png"
            p.write_bytes(png_bytes)

            data = AppKit.NSData.dataWithContentsOfFile_(str(p))
            image = AppKit.NSImage.alloc().initWithData_(data)
            image.setTemplate_(False)
            self._icon_pts = image.size().width

            nsstatusitem = self._nsapp.nsstatusitem
            nsstatusitem.setLength_(_NS_VARIABLE_LENGTH)

            button = nsstatusitem.button()
            button.setImageScaling_(_NS_IMAGE_SCALE_NONE)
            button.setImagePosition_(_NS_IMAGE_ONLY)
            button.setImage_(image)
            button.setTitle_("")
        except Exception:
            log.exception("_set_status_icon failed")
            self.title = "..."

    # ── Main update ──────────────────────────────────────────────────────────

    @rumps.timer(1)
    def _startup(self, _):
        if not self._startup_done:
            self._startup_done = True
            try:
                self._menu_delegate = _MenuWidthDelegate.alloc().init()
                self._nsapp.nsstatusitem.menu().setDelegate_(self._menu_delegate)
            except Exception:
                log.exception("menu delegate setup failed")
            try:
                self._wake_observer = _WakeObserver.alloc().init()
                self._wake_observer._callback = self._on_wake
                AppKit.NSWorkspace.sharedWorkspace().notificationCenter().addObserver_selector_name_object_(
                    self._wake_observer,
                    b"handleWake:",
                    AppKit.NSWorkspaceDidWakeNotification,
                    None,
                )
            except Exception:
                log.exception("wake observer setup failed")
            self._update_display()

    @rumps.timer(POLL_INTERVAL)
    def _poll(self, _):
        self._update_display()

    def _update_display(self):
        try:
            cfg = load_config()
            data = load_data()
            style = cfg.get("style", "standard")
            show_weekly = cfg.get("show_weekly", True)
            show_history = cfg.get("show_history", True)

            sp = wp = sr = wr = None
            claude_design_pct = extra_pct = extra_spent = account_balance = None
            extra_enabled = False
            if data is not None:
                sp = data.get("session_percent")
                wp = data.get("weekly_percent")
                sr = data.get("session_resets_at")
                wr = data.get("weekly_resets_at")
                claude_design_pct = data.get("claude_design_percent")
                extra_enabled = data.get("extra_usage_enabled", False)
                extra_pct = data.get("extra_usage_percent")
                extra_spent = data.get("extra_usage_spent")
                account_balance = data.get("account_balance")
                if data.get("updated_at"):
                    try:
                        age = (
                            datetime.now(timezone.utc)
                            - datetime.fromisoformat(data["updated_at"])
                        ).total_seconds()
                        if age > STALE_AFTER_SEC:
                            sp = wp = None
                    except ValueError:
                        pass

            show_claude_design = cfg.get("show_claude_design", False)
            show_extra_usage = cfg.get("show_extra_usage", False)

            # Status bar icon / text
            if style == "text":
                sp_str = f"{sp}%" if sp is not None else "--"
                wp_str = f"  {wp}%" if wp is not None and show_weekly else ""
                self._set_status_text(f"{sp_str}{wp_str}")
            else:
                self._set_status_icon(render_bars(sp, sr, wp, wr, cfg, weekly_visible=show_weekly))

            # Dropdown bar logic mirrors SwiftBar:
            # compact → show session + weekly in standard style (status bar has no text)
            # standard + weekly hidden → show weekly only (not visible in status bar)
            # standard + weekly shown → no bars in dropdown (already in status bar)
            std_cfg = {**cfg, "style": "standard"}
            show_session_bar = style in ("compact", "text")
            show_weekly_bar = style in ("compact", "text") or not show_weekly

            # In compact the icon is narrow — DROPDOWN_BAR_WIDTH drives menu width.
            # In standard the icon is wide (text + bars) — it drives menu width instead.
            if style in ("compact", "text"):
                _menu_w = DROPDOWN_BAR_WIDTH
            else:
                icon_pts = getattr(self, '_icon_pts', 0)
                _menu_w = max(DROPDOWN_BAR_WIDTH, int(icon_pts * SCALE)) if icon_pts else DROPDOWN_BAR_WIDTH

            self._session_bar._menuitem.setHidden_(not show_session_bar)
            self._weekly_bar._menuitem.setHidden_(not show_weekly_bar)

            _any_bar = show_session_bar or show_weekly_bar or show_claude_design or show_extra_usage
            if _any_bar:
                _font = load_font(STD_FONT_SIZE)
                _time_fmt = std_cfg.get("time_format", "rounded")
                _pcts = []
                _times = []
                if show_session_bar:
                    _pcts.append(f"{sp}%" if sp is not None else "--")
                    _times.append(time_remaining(sr, _time_fmt))
                if show_weekly_bar:
                    _pcts.append(f"{wp}%" if wp is not None else "--")
                    _times.append(time_remaining(wr, _time_fmt))
                if show_claude_design:
                    _pcts.append(f"{claude_design_pct}%" if claude_design_pct is not None else "--")
                    _times.append("")
                if show_extra_usage:
                    _pcts.append(f"{extra_pct}%" if extra_pct is not None else "0%")
                    _times.append(_extra_right(extra_enabled, account_balance))
                _prefix_col_w = max(text_width(_font, c) for c in ("s", "w", "d", "e")) + STD_LABEL_GAP
                _bar_x = _prefix_col_w + max(text_width(_font, p) for p in _pcts) + STD_LABEL_GAP
                _tw_time = max(text_width(_font, t) for t in _times)
                _time_col_w = STD_LABEL_GAP + _tw_time if _tw_time else 0
            else:
                _bar_x = None
                _time_col_w = 0

            if show_session_bar:
                _apply_image_view(self._session_bar._menuitem, render_weekly_bar(sp, sr, std_cfg, _menu_w, bar_x=_bar_x, time_col_w=_time_col_w, prefix="s", prefix_col_w=_prefix_col_w))
            else:
                self._session_bar._menuitem.setView_(None)
            if show_weekly_bar:
                _apply_image_view(self._weekly_bar._menuitem, render_weekly_bar(wp, wr, std_cfg, _menu_w, bar_x=_bar_x, time_col_w=_time_col_w, prefix="w", prefix_col_w=_prefix_col_w))
            else:
                self._weekly_bar._menuitem.setView_(None)

            self._design_bar._menuitem.setHidden_(not show_claude_design)
            if show_claude_design:
                _apply_image_view(self._design_bar._menuitem, render_weekly_bar(claude_design_pct, None, std_cfg, _menu_w, bar_x=_bar_x, time_col_w=_time_col_w, prefix="d", prefix_col_w=_prefix_col_w))
            else:
                self._design_bar._menuitem.setView_(None)

            _toggle_label = "Disable Extra Usage" if extra_enabled else "Enable Extra Usage"
            self._extra_toggle.title = _toggle_label

            self._extra_bar._menuitem.setHidden_(not show_extra_usage)
            if show_extra_usage:
                _extra_pct_label = f"{extra_pct}%" if extra_pct is not None else "0%"
                _apply_image_view(self._extra_bar._menuitem, render_weekly_bar(extra_pct or 0, None, std_cfg, _menu_w, bar_x=_bar_x, time_col_w=_time_col_w, label_override=_extra_pct_label, right_label=_extra_right(extra_enabled, account_balance), prefix="e", prefix_col_w=_prefix_col_w))
            else:
                self._extra_bar._menuitem.setView_(None)

            # Charts always match DROPDOWN_BAR_WIDTH so the dropdown is consistent width
            self._chart_session._menuitem.setHidden_(not show_history)
            self._chart_weekly._menuitem.setHidden_(not show_history)
            if show_history:
                target_cw = max(CHART_W, _menu_w + 2 * CHART_PAD)
                h24 = load_history(24)
                h7d = load_history(HISTORY_MAX_DAYS * 24)
                _apply_image_view(
                    self._chart_session._menuitem,
                    render_history_chart(h24, "sp", 24, cfg, "Session · 24h", chart_w=target_cw),
                    pad_x=_CHART_PAD_X,
                )
                _apply_image_view(
                    self._chart_weekly._menuitem,
                    render_history_chart(h7d, "wp", HISTORY_MAX_DAYS * 24, cfg, "Weekly · 7d", chart_w=target_cw),
                    pad_x=_CHART_PAD_X,
                )

            # Version / update
            if not getattr(self, '_update_in_flight', False):
                latest = load_update_info()
                if latest:
                    ver_label = f"v{VERSION}  →  v{latest}"
                    ver_color = AppKit.NSColor.systemOrangeColor()
                else:
                    ver_label = f"v{VERSION}  ↻"
                    ver_color = AppKit.NSColor.secondaryLabelColor()
                self._version_item._menuitem.setAttributedTitle_(
                    NSAttributedString.alloc().initWithString_attributes_(
                        ver_label,
                        {AppKit.NSForegroundColorAttributeName: ver_color},
                    )
                )

            self._sync_checks(cfg)
        except Exception:
            log.exception("_update_display failed")


if __name__ == "__main__":
    ClaudeUsageApp().run()
