# Claude Usage Monitor

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Platform: macOS](https://img.shields.io/badge/Platform-macOS-blue.svg)](#)
[![Requires: SwiftBar](https://img.shields.io/badge/Requires-SwiftBar-orange.svg)](https://swiftbar.app)

Your Claude session and weekly limits as progress bars in the macOS menu bar, so you stop opening a browser tab just to check.

![menu bar preview](docs/preview.png)
![compact style + settings preview](docs/settings.png)

## Why

I kept a Claude tab pinned just to see how close I was to the weekly limit, and I got tired of it. Now it's in the menu bar.

## How it works

A small daemon grabs your Claude session cookie from Chrome, hits the Claude API, and writes the result to a file. A SwiftBar plugin reads that file and draws the bars.

You don't paste tokens anywhere, and there's no browser extension. If you're signed into [claude.ai](https://claude.ai) in Chrome, it works.

## Requirements

- macOS
- [Homebrew](https://brew.sh)
- Google Chrome, signed into claude.ai

## Install

```bash
git clone https://github.com/ncreasor/claude-usage.git
cd claude-usage
./install.sh
```

The installer grabs Python 3.13 and SwiftBar via Homebrew if you don't have them, starts the background daemon, and adds the bars to your menu.

## Settings

Click ⚙ in the menu bar to change settings. Alternatively, enable **Open settings** mode to open the settings panel directly by clicking the progress bars (the gear icon is hidden in this mode).

| Setting | Options |
|---|---|
| Style | Standard (`65% ──── 2h`) or Compact (bar on top, label below) |
| Color theme | Orange, Blue, Green, Purple, Red, Teal, Pink, Yellow |
| Refresh interval | 1, 2, 5, 10, 15, or 30 minutes |
| Time format | Rounded (`5m`, `2h`) or Exact (`4m32s`, `1h23m`) |
| Weekly bar | Show in menu bar or hide (still visible inside settings) |
| Bar click action | Refresh data or Open settings (hides the gear icon) |

Saved to `~/.claude-usage/config.json`.

## Uninstall

```bash
./uninstall.sh
```

Stops the daemon, removes the plugins, and asks whether to clear cached data.

## Privacy

The only network request goes to Anthropic: `GET https://claude.ai/api/organizations/{id}/usage`. No third-party server, no telemetry, nothing else phones home.

To read your usage, the daemon opens Chrome's local cookie database — the same cookies Chrome itself sends to claude.ai on every page load.

If you want to check, the whole project is about 600 lines of Python across four files: [server.py](server/server.py), [claude-usage.py](swiftbar/claude-usage.py), [claude-settings.py](swiftbar/claude-settings.py), and [claude_shared.py](claude_shared.py). You can read it end to end in a few minutes.

## Logs

```bash
tail -f ~/Library/Logs/claude-usage.log
```

## Roadmap

- [ ] Arc
- [ ] Safari
- [ ] Firefox
- [ ] Windows

## Contributing

Issues and PRs welcome. If it's useful to you, a ⭐ genuinely helps other people find it.
