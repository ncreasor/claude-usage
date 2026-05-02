# Claude Usage Monitor

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Platform: macOS](https://img.shields.io/badge/Platform-macOS-blue.svg)](#)

Your Claude session and weekly limits as progress bars in the macOS menu bar, so you stop opening a browser tab just to check.

![menu bar preview](docs/preview.png)
![compact style + settings preview](docs/settings.png)

## Why

I kept a Claude tab pinned just to see how close I was to the weekly limit, and I got tired of it. Now it's in the menu bar.

## How it works

A small daemon grabs your Claude session cookie from the browser, hits the Claude API, and writes the result to a file. A native macOS status bar app reads that file and draws the bars.

You don't paste tokens anywhere, and there's no browser extension. If you're signed into [claude.ai](https://claude.ai) in a browser, it works.

## Requirements

- macOS
- [Homebrew](https://brew.sh)
- Browser (Chrome, Brave, Arc), signed into claude.ai

## Install

```bash
git clone https://github.com/ncreasor/claude-usage.git
cd claude-usage
./install.sh
```

The installer grabs Python 3.13 via Homebrew if you don't have it, starts the background daemon, and launches the status bar app.

## Settings

Click the progress bars in the menu bar to open the dropdown, then go to **Settings**.

| Setting | Options |
|---|---|
| Style | Standard (`65% ──── 2h`) or Compact (two thin bars, no text) |
| Color theme | Orange, Blue, Green, Purple, Red, Teal, Pink, Yellow |
| Refresh interval | 1, 2, 5, 10, 15, or 30 minutes |
| Time format | Rounded (`5m`, `2h`) or Exact (`4m`, `1h 23m`, `2d 6h`) |
| Weekly bar | Show in menu bar or hide (still visible in the dropdown when hidden) |
| History charts | Show or hide the 24h session and 7d weekly usage charts |
| Extra Features | Optionally show Claude Design and Extra Usage bars in the dropdown |

Saved to `~/.claude-usage/config.json`.

## Uninstall

```bash
./uninstall.sh
```

Stops the daemon and the status bar app, and asks whether to clear cached data.

## Privacy

All network requests go to Anthropic only — no third-party server, no telemetry, nothing else phones home. Endpoints used:

- `GET /api/organizations/{id}/usage` — session and weekly usage
- `GET /api/organizations/{id}/prepaid/credits` — account balance (Extra Usage bar)
- `GET/PUT /api/organizations/{id}/overage_spend_limit` — extra usage toggle

To read your usage, the daemon opens browser's local cookie database — the same cookies browser itself sends to claude.ai on every page load.

If you want to check, the entry points are [server.py](server/server.py), [claude-usage.py](displays/systray/claude-usage.py), and [claude_shared.py](claude_shared.py). You can read it end to end in a few minutes.

## Logs

```bash
tail -f ~/Library/Logs/claude-usage.log          # daemon
tail -f ~/Library/Logs/claude-usage-systray.log  # status bar app
```

## Roadmap
Settings
- [x] Styles & Colors
- [x] Refresh interval
- [x] Time format
- [x] Getting updates
- [ ] Languages
- [ ] Health

AI
- [x] Claude
- [ ] ChatGPT
- [ ] Grok

Browsers
- [x] Chrome
- [x] Arc
- [ ] Safari
- [ ] Firefox
- [x] Brave

Modes
- [x] Subscription
- [ ] Api

OS
- [x] MacOS
- [ ] Windows

## Contributing

Issues and PRs welcome. If it's useful to you, a ⭐ genuinely helps other people find it.
