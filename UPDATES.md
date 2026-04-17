# Changelog

## v1.3.0

- **One-click update** — when a new GitHub release is available, the version line in settings changes to `v1.3.0 → v1.4.0` (orange); clicking it runs `git pull && install.sh` in the background and restarts everything automatically

## v1.2.0

- **Time format** — choose between rounded (`5m`, `2h`) and exact (`4m32s`, `1h23m`) display
- **Weekly bar visibility** — hide the weekly bar from the menu bar; it stays visible as a rendered progress bar inside the settings panel
- **Bar click action** — click the bars to refresh (default) or to open the settings panel; in settings mode the gear icon is hidden
- Version number shown in the settings panel

## v1.1.0

- Rewrote rendering with Pillow: proper HiDPI (2×), rounded bar caps, correct text measurement
- **Standard style** — percentage, bar, and time-to-reset on one line: `65% ════ 2h`
- **Compact style** — bar on top, label below, side by side
- Removed the old Time Format (24h/12h) and Percent position (inside/outside) settings

## v1.0.0 — 2026-04-17

Initial release.

- Session and weekly usage as progress bars in the macOS menu bar
- Background daemon reads data from the Claude API via Chrome's local cookie database
- Settings: color theme, refresh interval
- Auto-update check against the latest GitHub release
- One-command install (`install.sh`) and uninstall (`uninstall.sh`)
