#!/usr/bin/env python3
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
    THEME_NAMES, UPDATE_URL, VERSION,
    load_config, load_data, load_history, load_update_info,
    render_bars, render_history_chart, render_weekly_bar,
    save_config,
)

logging.basicConfig(
    filename=Path.home() / "Library" / "Logs" / "claude-usage-systray.log",
    level=logging.ERROR,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("claude-usage-systray")

STALE_AFTER_SEC = 600
POLL_INTERVAL = 30
DROPDOWN_BAR_WIDTH = 200  # set to e.g. 400 to fix dropdown bar width; None = auto
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
_NS_IMAGE_SCALE_NONE = 2   # NSImageScaleNone


class _MenuWidthDelegate(AppKit.NSObject):
    def menuWillOpen_(self, menu):
        menu.setMinimumWidth_(0)


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
        self._chart_session = rumps.MenuItem(_ZWSP * 3)
        self._chart_weekly = rumps.MenuItem(_ZWSP * 4)
        self._history_toggle = rumps.MenuItem("Hide history", callback=self._toggle_history)
        self._version_item = rumps.MenuItem(f"v{VERSION}", callback=self._on_version)

        # Style
        self._style_standard = rumps.MenuItem("Standard", callback=lambda _: self._set("style", "standard"))
        self._style_compact = rumps.MenuItem("Compact", callback=lambda _: self._set("style", "compact"))
        style_menu = rumps.MenuItem("Style")
        style_menu.add(self._style_standard)
        style_menu.add(self._style_compact)

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

        # Weekly bar
        self._weekly_show = rumps.MenuItem("Show", callback=lambda _: self._set("show_weekly", True))
        self._weekly_hide = rumps.MenuItem(
            "Hide  (show in settings)", callback=lambda _: self._set("show_weekly", False)
        )
        weekly_menu = rumps.MenuItem("Weekly Bar")
        weekly_menu.add(self._weekly_show)
        weekly_menu.add(self._weekly_hide)

        settings = rumps.MenuItem("Settings")
        settings.add(style_menu)
        settings.add(color_menu)
        settings.add(interval_menu)
        settings.add(fmt_menu)
        settings.add(weekly_menu)

        self._refresh_item = rumps.MenuItem("Refresh now", callback=self._on_refresh)

        self.menu = [
            self._version_item,
            self._refresh_item,
            None,
            self._session_bar,
            self._weekly_bar,
            self._chart_session,
            self._chart_weekly,
            self._history_toggle,
            None,
            settings,
            None,
            rumps.MenuItem("Quit", callback=rumps.quit_application),
        ]

    # ── Settings helpers ─────────────────────────────────────────────────────

    def _make_cb(self, key, value):
        return lambda _: self._set(key, value)

    def _set(self, key, value):
        save_config(key, value)
        self._update_display()

    def _toggle_history(self, _):
        self._set("show_history", not load_config().get("show_history", True))

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
        def _do():
            try:
                urllib.request.urlopen(
                    urllib.request.Request(url, method="POST"), timeout=5
                )
            except Exception:
                pass
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

        theme = cfg.get("theme", "orange")
        for name, item in self._theme_items.items():
            item.state = name == theme

        interval = cfg.get("fetch_interval_minutes", 5)
        for mins, item in self._interval_items.items():
            item.state = mins == interval

        fmt = cfg.get("time_format", "rounded")
        self._fmt_rounded.state = fmt == "rounded"
        self._fmt_exact.state = fmt == "exact"

        show_weekly = cfg.get("show_weekly", True)
        self._weekly_show.state = show_weekly
        self._weekly_hide.state = not show_weekly

        show_history = cfg.get("show_history", True)
        label = "Hide history" if show_history else "Show history"
        attrs = {AppKit.NSForegroundColorAttributeName: AppKit.NSColor.secondaryLabelColor()}
        self._history_toggle._menuitem.setAttributedTitle_(
            NSAttributedString.alloc().initWithString_attributes_(label, attrs)
        )

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
            if data is not None:
                sp = data.get("session_percent")
                wp = data.get("weekly_percent")
                sr = data.get("session_resets_at")
                wr = data.get("weekly_resets_at")
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

            # Status bar icon
            self._set_status_icon(render_bars(sp, sr, wp, wr, cfg, weekly_visible=show_weekly))

            # Dropdown bar logic mirrors SwiftBar:
            # compact → show session + weekly in standard style (status bar has no text)
            # standard + weekly hidden → show weekly only (not visible in status bar)
            # standard + weekly shown → no bars in dropdown (already in status bar)
            std_cfg = {**cfg, "style": "standard"}
            show_session_bar = style == "compact"
            show_weekly_bar = style == "compact" or not show_weekly

            self._session_bar._menuitem.setHidden_(not show_session_bar)
            self._weekly_bar._menuitem.setHidden_(not show_weekly_bar)

            if show_session_bar:
                _apply_image_view(self._session_bar._menuitem, render_weekly_bar(sp, sr, std_cfg, DROPDOWN_BAR_WIDTH))
            else:
                self._session_bar._menuitem.setView_(None)
            if show_weekly_bar:
                _apply_image_view(self._weekly_bar._menuitem, render_weekly_bar(wp, wr, std_cfg, DROPDOWN_BAR_WIDTH))
            else:
                self._weekly_bar._menuitem.setView_(None)

            # Charts — expand to fill dropdown width forced by the status icon
            self._chart_session._menuitem.setHidden_(not show_history)
            self._chart_weekly._menuitem.setHidden_(not show_history)
            if show_history:
                icon_pts = getattr(self, '_icon_pts', 0)
                target_cw = max(CHART_W, int((icon_pts - 2 * _CHART_PAD_X) * SCALE))
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
