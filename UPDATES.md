# Changelog

## v1.8.1

- **Claude Design bar width** — `d` bar no longer stretches to full width; progress bar now stops at the same column as session and weekly bars

## v1.8.0

- **Bar labels** — each dropdown bar now has a small grey letter on the left (`s` session, `w` weekly, `d` design, `e` extra); letters are centered in a fixed column so percentage values stay left-aligned regardless of letter width

## v1.7.10

- **Extra Usage bar** — optional bar showing extra usage (% and account balance); toggle extra usage on/off directly from the dropdown without opening a browser; clicking the toggle triggers an immediate data refresh
- **Account balance** — fetches real prepaid credit balance from the Claude billing API; shows `$0.00` when the account is empty, actual balance when positive; shows `Off` when extra usage is disabled

## v1.7.9

- **Claude Design bar** — optional bar showing Claude Design weekly usage; enabled under Settings → Extra Features
- **GitHub button** — added a GitHub link at the bottom of the dropdown menu

- **Aligned dropdown bars** — percentage values are left-aligned, progress bars start at the same column, and time-to-reset is right-aligned; bars no longer shift based on text width
- **Fixed dropdown bar width** — `DROPDOWN_BAR_WIDTH` now controls the total image width; the progress bar shrinks to fill the remaining space so the layout never overflows
- **Charts follow dropdown width** — in compact mode charts match `DROPDOWN_BAR_WIDTH`; in standard mode they stretch to fill the full menu width (driven by the status bar icon)

## v1.7.1 – v1.7.7

Internal testing of the auto-update mechanism — no user-facing changes.

## v1.7.0

- **Native systray app** — replaced the SwiftBar plugin with a native macOS status bar app (rumps + AppKit); SwiftBar is no longer required
- **Streamlined layout** — removed the separate settings panel and bar-click action; charts and controls are now directly in the dropdown

## v1.6.1

- **Arc and Brave support fix** — each Chromium-based browser now looks up its own keychain entry (`Arc Safe Storage`, `Brave Safe Storage`) instead of always using `Chrome Safe Storage`; cookie decryption now works correctly for Arc and Brave users

## v1.6.0

- **Usage history charts** — the settings panel now shows two mini-charts: session usage over the last 24 hours and weekly usage over the last 7 days. Each fetch is recorded to `~/.claude-usage/history.jsonl`; the charts auto-prune entries older than 7 days. Toggle visibility with **Hide history / Show history**.
- **Grouped settings** — settings options are now organized under a collapsible **Settings** submenu with labeled sections (Style, Color, Refresh Interval, Time Format, Weekly Bar, Bar Click Action).
- **Performance** — Chrome cookie decryption key and the data source object are now cached; both SwiftBar plugins refresh after each fetch.

## v1.5.4

- **Settings access fix** — when "Open settings" click mode is active and data hasn't loaded yet, the bar now shows a fallback icon and still opens the settings panel on click instead of doing nothing

## v1.5.3

- **Time format spacing** — exact format now uses spaces between units: `1h 23m`, `2d 6h`

## v1.5.2

Internal refactoring — no user-facing changes.

- Browser cookie logic moved to `server/browsers/` (Chrome, Arc, Brave share one implementation; Firefox and Safari stubbed for future support)
- Fetch logic moved to `server/sources/` (subscription and API modes as separate modules)
- SwiftBar plugins moved to `displays/swiftbar/` to make room for other OS display layers

## v1.5.0

- **Compact style redesign** — now shows two thin stacked bars (session on top, weekly below), no text; same bar width as standard
- **Unified settings panel** — gear icon and bar-click settings are now identical: same layout, same options, both include a **Refresh now** button
- **Standard preview in settings** — when compact mode is active, the settings panel always shows both bars in standard style so you can read the actual values

## v1.3.4

- **Exact time format fix** — removed seconds (was `4m32s`, now `4m`); durations over 24 hours now show days+hours (`2d6h`) instead of raw hours (`54h`)

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
