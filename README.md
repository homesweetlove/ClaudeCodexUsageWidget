# ClaudeCodexUsageWidget

A lightweight Windows desktop widget that shows locally cached usage / rate-limit information for **Claude Code** and **OpenAI Codex** without sending prompts or consuming model tokens.

## What it does

- Dark, compact always-on-top desktop widget
- Shows Claude Code and Codex usage when locally observable
- Reads local cache / session metadata only
- **Does not invoke `claude`, `codex`, or any model API**
- Manual refresh + configurable auto refresh
- Draggable frameless window
- Optional Windows startup launcher
- Zero third-party Python packages

## Data sources

### Codex
The widget scans recent JSON/JSONL state under `%USERPROFILE%\.codex` and looks for rate-limit structures such as `rate_limits`, `primary`, `secondary`, `used_percent`, and reset timestamps. Newer Codex CLI sessions commonly persist this information in session/event metadata.

### Claude Code
The widget scans recent JSON/JSONL state under `%USERPROFILE%\.claude` for locally cached rate-limit/usage metadata. Claude Code versions differ in what they persist locally, so the widget may show **Unavailable** when no non-token-consuming local usage record exists.

This project intentionally does **not** scrape browser cookies, steal session tokens, or send a hidden prompt just to discover limits.

## Run on Windows

Requirements: Python 3.10+ with Tkinter (included in the normal Windows Python installer).

```bat
run.bat
```

Or:

```powershell
pythonw usage_widget.py
```

## Start with Windows

Run:

```powershell
powershell -ExecutionPolicy Bypass -File .\install_startup.ps1
```

To remove startup:

```powershell
powershell -ExecutionPolicy Bypass -File .\uninstall_startup.ps1
```

## Configuration

On first launch the app creates:

`%LOCALAPPDATA%\ClaudeCodexUsageWidget\config.json`

Default settings:

```json
{
  "refresh_seconds": 30,
  "always_on_top": true,
  "window_x": null,
  "window_y": null
}
```

## Notes

- A percentage shown by the widget is based on the newest matching local state record it can find.
- If a CLI changes its local file format, the parser is deliberately tolerant and searches nested JSON recursively.
- `Unavailable` means the widget did not find trustworthy local usage metadata; it does **not** mean the account has no quota.

## License

MIT
