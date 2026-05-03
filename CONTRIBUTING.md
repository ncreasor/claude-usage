# Contributing

## Bug reports

Open an issue with:
- macOS version
- Browser you use with claude.ai
- What happened vs. what you expected
- Relevant log lines (`tail -50 ~/Library/Logs/claude-usage-systray.log`)

## Pull requests

1. Fork the repo and create a branch from `main`
2. Test your change manually — run `install.sh` and verify the app works
3. Keep the PR focused: one fix or feature per PR
4. Update `UPDATES.md` with a short entry under a new version heading

## Project structure

| Path | What it does |
|---|---|
| `server/server.py` | HTTP daemon — fetches usage data from the Claude API |
| `server/sources/subscription.py` | Subscription mode: cookie auth + API calls |
| `server/browsers/` | Per-browser cookie extraction |
| `displays/systray/claude-usage.py` | Native macOS status bar app |
| `claude_shared.py` | Shared rendering and config helpers |
| `install.sh` / `uninstall.sh` | Setup and teardown |
