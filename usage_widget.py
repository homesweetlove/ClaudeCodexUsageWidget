from __future__ import annotations

import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import tkinter as tk
from tkinter import messagebox

APP_NAME = "ClaudeCodexUsageWidget"
APP_VERSION = "0.1.0"
CONFIG_DIR = Path(os.getenv("LOCALAPPDATA", Path.home())) / APP_NAME
CONFIG_PATH = CONFIG_DIR / "config.json"
DEFAULT_CONFIG = {
    "refresh_seconds": 30,
    "always_on_top": True,
    "window_x": None,
    "window_y": None,
}


@dataclass
class LimitWindow:
    label: str
    used_percent: float | None = None
    remaining_percent: float | None = None
    resets_at: float | None = None
    window_minutes: float | None = None

    def finalize(self) -> "LimitWindow":
        if self.remaining_percent is None and self.used_percent is not None:
            self.remaining_percent = 100.0 - self.used_percent
        if self.used_percent is None and self.remaining_percent is not None:
            self.used_percent = 100.0 - self.remaining_percent
        if self.used_percent is not None:
            self.used_percent = max(0.0, min(100.0, self.used_percent))
        if self.remaining_percent is not None:
            self.remaining_percent = max(0.0, min(100.0, self.remaining_percent))
        return self


@dataclass
class ProviderSnapshot:
    provider: str
    windows: list[LimitWindow] = field(default_factory=list)
    source: str | None = None
    source_mtime: float | None = None
    status: str = "Unavailable"
    detail: str = "No local rate-limit metadata found"


class LocalUsageScanner:
    """Read-only scanner. It never starts claude/codex and never performs network requests."""

    USED_KEYS = (
        "used_percent",
        "usage_percent",
        "percent_used",
        "percentage_used",
        "used_percentage",
        "utilization",
    )
    REMAINING_KEYS = (
        "remaining_percent",
        "percent_remaining",
        "remaining_percentage",
    )
    RESET_KEYS = (
        "resets_at",
        "reset_at",
        "reset_time",
        "resetAt",
        "next_reset_at",
        "next_reset",
    )
    WINDOW_KEYS = (
        "window_minutes",
        "window_mins",
        "windowMinutes",
        "duration_minutes",
    )
    BUCKET_KEYS = {
        "primary": "5h / Primary",
        "secondary": "Weekly / Secondary",
        "five_hour": "5 hour",
        "fiveHour": "5 hour",
        "5h": "5 hour",
        "seven_day": "7 day",
        "sevenDay": "7 day",
        "7d": "7 day",
        "weekly": "Weekly",
        "seven_day_opus": "7 day Opus",
        "seven_day_sonnet": "7 day Sonnet",
    }

    def scan_codex(self) -> ProviderSnapshot:
        roots = [Path.home() / ".codex"]
        return self._scan_provider("Codex", roots, provider_hint="codex")

    def scan_claude(self) -> ProviderSnapshot:
        roots = [Path.home() / ".claude"]
        return self._scan_provider("Claude", roots, provider_hint="claude")

    def _scan_provider(self, provider: str, roots: list[Path], provider_hint: str) -> ProviderSnapshot:
        files: list[Path] = []
        for root in roots:
            if not root.exists():
                continue
            try:
                for pattern in ("**/*.jsonl", "**/*.json"):
                    files.extend(root.glob(pattern))
            except OSError:
                continue

        if not files:
            return ProviderSnapshot(
                provider=provider,
                status="Unavailable",
                detail=f"{roots[0]} not found or has no JSON state",
            )

        candidates: list[tuple[float, Path]] = []
        for path in files:
            try:
                st = path.stat()
                if st.st_size <= 0:
                    continue
                candidates.append((st.st_mtime, path))
            except OSError:
                pass
        candidates.sort(reverse=True, key=lambda item: item[0])

        # Newest local state normally contains the freshest limit event.
        # Bound work so refreshes stay cheap even with years of sessions.
        for mtime, path in candidates[:60]:
            for obj in self._read_json_objects(path):
                windows = self._extract_windows(obj, provider_hint)
                if windows:
                    windows = self._dedupe_and_sort(windows)
                    return ProviderSnapshot(
                        provider=provider,
                        windows=windows[:3],
                        source=str(path),
                        source_mtime=mtime,
                        status="Local data",
                        detail="Read from local CLI state; no model request sent",
                    )

        return ProviderSnapshot(
            provider=provider,
            status="Unavailable",
            detail="CLI state exists, but no trustworthy rate-limit fields were found",
        )

    def _read_json_objects(self, path: Path):
        try:
            size = path.stat().st_size
            # Reading just the tail makes large session JSONL files cheap to scan.
            max_bytes = 2_000_000
            with path.open("rb") as f:
                if size > max_bytes:
                    f.seek(size - max_bytes)
                    f.readline()  # discard partial first line
                data = f.read().decode("utf-8", errors="ignore")
        except OSError:
            return

        suffix = path.suffix.lower()
        if suffix == ".jsonl":
            lines = data.splitlines()
            for line in reversed(lines[-3000:]):
                line = line.strip()
                if not line:
                    continue
                try:
                    value = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(value, (dict, list)):
                    yield value
        else:
            try:
                value = json.loads(data)
            except json.JSONDecodeError:
                return
            if isinstance(value, (dict, list)):
                yield value

    def _extract_windows(self, root, provider_hint: str) -> list[LimitWindow]:
        found: list[LimitWindow] = []

        def visit(node, path: tuple[str, ...] = ()):
            if isinstance(node, dict):
                # A direct bucket (for example primary/secondary or five_hour/seven_day).
                for key, label in self.BUCKET_KEYS.items():
                    bucket = node.get(key)
                    if isinstance(bucket, dict):
                        parsed = self._parse_bucket(bucket, label)
                        if parsed:
                            found.append(parsed)

                # Generic rate-limit object with nested named windows.
                for key, value in node.items():
                    low = str(key).lower()
                    if isinstance(value, dict) and (
                        "rate_limit" in low
                        or low in {"limits", "usage_limits", "current_usage", "usage"}
                    ):
                        parsed = self._parse_bucket(value, self._label_from_path(path + (str(key),), value))
                        if parsed:
                            found.append(parsed)

                # Parse the current dictionary itself when it clearly looks like a limit bucket.
                keys_lower = {str(k).lower() for k in node.keys()}
                has_percent = any(k.lower() in keys_lower for k in self.USED_KEYS + self.REMAINING_KEYS)
                has_limit_context = any(
                    token in "/".join(path).lower()
                    for token in ("rate", "limit", "usage", "primary", "secondary", "five_hour", "seven_day")
                )
                if has_percent and has_limit_context:
                    parsed = self._parse_bucket(node, self._label_from_path(path, node))
                    if parsed:
                        found.append(parsed)

                for key, value in node.items():
                    if isinstance(value, (dict, list)):
                        visit(value, path + (str(key),))

            elif isinstance(node, list):
                for idx, value in enumerate(node[-200:]):
                    if isinstance(value, (dict, list)):
                        visit(value, path + (str(idx),))

        visit(root)
        return found

    def _parse_bucket(self, bucket: dict, label: str) -> LimitWindow | None:
        used = self._first_number(bucket, self.USED_KEYS)
        remaining = self._first_number(bucket, self.REMAINING_KEYS)
        if used is None and remaining is None:
            return None

        reset_raw = self._first_value(bucket, self.RESET_KEYS)
        window = self._first_number(bucket, self.WINDOW_KEYS)
        reset = self._parse_timestamp(reset_raw)

        if window is not None:
            if window <= 360:
                label = "5 hour"
            elif window >= 6 * 24 * 60:
                label = "Weekly"

        return LimitWindow(
            label=label,
            used_percent=used,
            remaining_percent=remaining,
            resets_at=reset,
            window_minutes=window,
        ).finalize()

    @staticmethod
    def _first_value(mapping: dict, keys: tuple[str, ...]):
        for wanted in keys:
            for key, value in mapping.items():
                if str(key).lower() == wanted.lower():
                    return value
        return None

    def _first_number(self, mapping: dict, keys: tuple[str, ...]) -> float | None:
        value = self._first_value(mapping, keys)
        if value is None or isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            match = re.search(r"-?\d+(?:\.\d+)?", value.replace(",", ""))
            if match:
                try:
                    return float(match.group(0))
                except ValueError:
                    return None
        return None

    @staticmethod
    def _parse_timestamp(value) -> float | None:
        if value is None or isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            stamp = float(value)
            if stamp > 10_000_000_000:  # milliseconds
                stamp /= 1000.0
            return stamp if stamp > 1_000_000_000 else None
        if isinstance(value, str):
            text = value.strip()
            if text.isdigit():
                stamp = float(text)
                if stamp > 10_000_000_000:
                    stamp /= 1000.0
                return stamp
            try:
                normalized = text.replace("Z", "+00:00")
                return datetime.fromisoformat(normalized).timestamp()
            except ValueError:
                return None
        return None

    @staticmethod
    def _label_from_path(path: tuple[str, ...], bucket: dict) -> str:
        joined = "/".join(path).lower()
        if "five_hour" in joined or "5h" in joined:
            return "5 hour"
        if "seven_day" in joined or "weekly" in joined or "7d" in joined:
            return "Weekly"
        if "primary" in joined:
            return "Primary"
        if "secondary" in joined:
            return "Secondary"
        minutes = bucket.get("window_minutes")
        if isinstance(minutes, (int, float)):
            if minutes <= 360:
                return "5 hour"
            if minutes >= 6 * 24 * 60:
                return "Weekly"
        return "Usage limit"

    @staticmethod
    def _dedupe_and_sort(windows: list[LimitWindow]) -> list[LimitWindow]:
        unique: dict[tuple, LimitWindow] = {}
        for win in windows:
            key = (
                win.label.lower(),
                round(win.remaining_percent or -1, 2),
                int(win.resets_at or 0),
            )
            unique[key] = win

        priority = {
            "5 hour": 0,
            "5h / primary": 0,
            "primary": 0,
            "weekly": 1,
            "weekly / secondary": 1,
            "secondary": 1,
            "7 day": 1,
        }
        return sorted(unique.values(), key=lambda w: priority.get(w.label.lower(), 5))


def load_config() -> dict:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    config = dict(DEFAULT_CONFIG)
    if CONFIG_PATH.exists():
        try:
            saved = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(saved, dict):
                config.update(saved)
        except (OSError, json.JSONDecodeError):
            pass
    try:
        config["refresh_seconds"] = max(10, min(3600, int(config["refresh_seconds"])))
    except (TypeError, ValueError):
        config["refresh_seconds"] = 30
    return config


def save_config(config: dict) -> None:
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(json.dumps(config, indent=2), encoding="utf-8")
    except OSError:
        pass


def human_reset(timestamp: float | None) -> str:
    if timestamp is None:
        return "reset time unavailable"
    seconds = int(timestamp - time.time())
    if seconds <= 0:
        return "reset due"
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes = seconds // 60
    if days:
        return f"resets in {days}d {hours}h"
    if hours:
        return f"resets in {hours}h {minutes}m"
    return f"resets in {max(1, minutes)}m"


def age_text(mtime: float | None) -> str:
    if not mtime:
        return ""
    seconds = max(0, int(time.time() - mtime))
    if seconds < 60:
        return "updated <1m ago"
    if seconds < 3600:
        return f"updated {seconds // 60}m ago"
    if seconds < 86400:
        return f"updated {seconds // 3600}h ago"
    return f"updated {seconds // 86400}d ago"


class UsageWidget(tk.Tk):
    BG = "#0b0b0d"
    CARD = "#151518"
    CARD_2 = "#1b1b1f"
    TEXT = "#f4f4f5"
    MUTED = "#8d8d96"
    BORDER = "#27272c"
    TRACK = "#29292e"
    GOOD = "#d9d9df"
    WARN = "#b7b7bf"
    DANGER = "#85858f"

    def __init__(self):
        super().__init__()
        self.config_data = load_config()
        self.scanner = LocalUsageScanner()
        self.drag_origin: tuple[int, int, int, int] | None = None
        self.refresh_job = None
        self.provider_frames: dict[str, tk.Frame] = {}

        self.title(APP_NAME)
        self.configure(bg=self.BG)
        self.overrideredirect(True)
        self.attributes("-topmost", bool(self.config_data.get("always_on_top", True)))
        self.resizable(False, False)

        self._build_ui()
        self.update_idletasks()
        self._restore_position()
        self.bind("<ButtonPress-1>", self._begin_drag, add="+")
        self.bind("<B1-Motion>", self._drag, add="+")
        self.bind("<ButtonRelease-1>", self._end_drag, add="+")
        self.bind("<Escape>", lambda _e: self.destroy())
        self.protocol("WM_DELETE_WINDOW", self.destroy)

        self.after(80, self.refresh)

    def _build_ui(self):
        outer = tk.Frame(self, bg=self.BG, highlightbackground=self.BORDER, highlightthickness=1)
        outer.pack(fill="both", expand=True)

        header = tk.Frame(outer, bg=self.BG, padx=14, pady=11)
        header.pack(fill="x")

        left = tk.Frame(header, bg=self.BG)
        left.pack(side="left")
        tk.Label(left, text="USAGE", bg=self.BG, fg=self.TEXT, font=("Segoe UI Semibold", 10)).pack(anchor="w")
        self.subtitle = tk.Label(
            left,
            text="local state only",
            bg=self.BG,
            fg=self.MUTED,
            font=("Segoe UI", 8),
        )
        self.subtitle.pack(anchor="w")

        close_btn = self._header_button(header, "×", self.destroy)
        close_btn.pack(side="right", padx=(4, 0))
        pin_char = "●" if self.config_data.get("always_on_top", True) else "○"
        self.pin_btn = self._header_button(header, pin_char, self.toggle_topmost)
        self.pin_btn.pack(side="right", padx=(4, 0))
        refresh_btn = self._header_button(header, "↻", self.refresh)
        refresh_btn.pack(side="right")

        body = tk.Frame(outer, bg=self.BG, padx=10, pady=0)
        body.pack(fill="both")
        for provider in ("Claude", "Codex"):
            frame = tk.Frame(body, bg=self.CARD, padx=12, pady=11)
            frame.pack(fill="x", pady=(0, 8))
            self.provider_frames[provider] = frame
            self._render_placeholder(frame, provider)

        footer = tk.Frame(outer, bg=self.BG, padx=14, pady=8)
        footer.pack(fill="x")
        self.footer_status = tk.Label(
            footer,
            text=f"auto refresh · {self.config_data['refresh_seconds']}s",
            bg=self.BG,
            fg=self.MUTED,
            font=("Segoe UI", 8),
        )
        self.footer_status.pack(side="left")
        tk.Label(
            footer,
            text=f"v{APP_VERSION}",
            bg=self.BG,
            fg=self.MUTED,
            font=("Segoe UI", 8),
        ).pack(side="right")

    def _header_button(self, parent, text, command):
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=self.CARD,
            fg=self.TEXT,
            activebackground=self.CARD_2,
            activeforeground=self.TEXT,
            relief="flat",
            bd=0,
            width=3,
            height=1,
            cursor="hand2",
            font=("Segoe UI", 10),
        )

    def _render_placeholder(self, frame: tk.Frame, provider: str):
        for child in frame.winfo_children():
            child.destroy()
        tk.Label(
            frame,
            text=provider.upper(),
            bg=self.CARD,
            fg=self.TEXT,
            font=("Segoe UI Semibold", 9),
        ).pack(anchor="w")
        tk.Label(
            frame,
            text="Reading local state…",
            bg=self.CARD,
            fg=self.MUTED,
            font=("Segoe UI", 9),
        ).pack(anchor="w", pady=(7, 2))

    def _render_snapshot(self, snapshot: ProviderSnapshot):
        frame = self.provider_frames[snapshot.provider]
        for child in frame.winfo_children():
            child.destroy()

        top = tk.Frame(frame, bg=self.CARD)
        top.pack(fill="x")
        tk.Label(
            top,
            text=snapshot.provider.upper(),
            bg=self.CARD,
            fg=self.TEXT,
            font=("Segoe UI Semibold", 9),
        ).pack(side="left")
        tk.Label(
            top,
            text=age_text(snapshot.source_mtime),
            bg=self.CARD,
            fg=self.MUTED,
            font=("Segoe UI", 8),
        ).pack(side="right")

        if not snapshot.windows:
            tk.Label(
                frame,
                text="Unavailable",
                bg=self.CARD,
                fg=self.TEXT,
                font=("Segoe UI Semibold", 16),
            ).pack(anchor="w", pady=(8, 1))
            tk.Label(
                frame,
                text=snapshot.detail,
                bg=self.CARD,
                fg=self.MUTED,
                font=("Segoe UI", 8),
                wraplength=330,
                justify="left",
            ).pack(anchor="w")
            return

        for i, window in enumerate(snapshot.windows[:2]):
            row = tk.Frame(frame, bg=self.CARD)
            row.pack(fill="x", pady=(9 if i == 0 else 8, 0))

            label = tk.Label(
                row,
                text=window.label,
                bg=self.CARD,
                fg=self.MUTED,
                font=("Segoe UI", 8),
            )
            label.pack(anchor="w")

            metric = tk.Frame(row, bg=self.CARD)
            metric.pack(fill="x", pady=(1, 3))
            remaining = window.remaining_percent if window.remaining_percent is not None else 0.0
            tk.Label(
                metric,
                text=f"{remaining:.0f}%",
                bg=self.CARD,
                fg=self.TEXT,
                font=("Segoe UI Semibold", 17),
            ).pack(side="left")
            tk.Label(
                metric,
                text=" remaining",
                bg=self.CARD,
                fg=self.MUTED,
                font=("Segoe UI", 8),
            ).pack(side="left", pady=(7, 0))
            tk.Label(
                metric,
                text=human_reset(window.resets_at),
                bg=self.CARD,
                fg=self.MUTED,
                font=("Segoe UI", 8),
            ).pack(side="right", pady=(7, 0))

            self._progress_bar(row, remaining)

    def _progress_bar(self, parent: tk.Widget, percent: float):
        canvas = tk.Canvas(parent, width=330, height=5, bg=self.CARD, highlightthickness=0, bd=0)
        canvas.pack(fill="x", pady=(1, 0))

        def draw(_event=None):
            canvas.delete("all")
            width = max(1, canvas.winfo_width())
            canvas.create_rectangle(0, 0, width, 5, fill=self.TRACK, outline="")
            fill = max(0, min(width, width * percent / 100.0))
            shade = self.GOOD if percent >= 35 else self.WARN if percent >= 15 else self.DANGER
            if fill > 0:
                canvas.create_rectangle(0, 0, fill, 5, fill=shade, outline="")

        canvas.bind("<Configure>", draw)
        self.after_idle(draw)

    def refresh(self):
        if self.refresh_job is not None:
            try:
                self.after_cancel(self.refresh_job)
            except tk.TclError:
                pass
            self.refresh_job = None

        self.subtitle.config(text="scanning local state…")
        self.update_idletasks()

        # The scan is local file I/O only and intentionally performs no subprocess/network call.
        claude = self.scanner.scan_claude()
        codex = self.scanner.scan_codex()
        self._render_snapshot(claude)
        self._render_snapshot(codex)
        self.subtitle.config(text="no model requests")
        self.footer_status.config(text=f"auto refresh · {self.config_data['refresh_seconds']}s")

        self.refresh_job = self.after(int(self.config_data["refresh_seconds"]) * 1000, self.refresh)

    def toggle_topmost(self):
        enabled = not bool(self.config_data.get("always_on_top", True))
        self.config_data["always_on_top"] = enabled
        self.attributes("-topmost", enabled)
        self.pin_btn.config(text="●" if enabled else "○")
        save_config(self.config_data)

    def _restore_position(self):
        x = self.config_data.get("window_x")
        y = self.config_data.get("window_y")
        width = max(360, self.winfo_reqwidth())
        height = max(300, self.winfo_reqheight())
        if isinstance(x, int) and isinstance(y, int):
            self.geometry(f"{width}x{height}+{x}+{y}")
            return
        screen_w = self.winfo_screenwidth()
        self.geometry(f"{width}x{height}+{max(20, screen_w - width - 28)}+80")

    def _begin_drag(self, event):
        widget = event.widget
        if isinstance(widget, tk.Button):
            self.drag_origin = None
            return
        self.drag_origin = (event.x_root, event.y_root, self.winfo_x(), self.winfo_y())

    def _drag(self, event):
        if not self.drag_origin:
            return
        sx, sy, wx, wy = self.drag_origin
        self.geometry(f"+{wx + event.x_root - sx}+{wy + event.y_root - sy}")

    def _end_drag(self, _event):
        if self.drag_origin:
            self.config_data["window_x"] = self.winfo_x()
            self.config_data["window_y"] = self.winfo_y()
            save_config(self.config_data)
        self.drag_origin = None

    def destroy(self):
        self.config_data["window_x"] = self.winfo_x()
        self.config_data["window_y"] = self.winfo_y()
        save_config(self.config_data)
        super().destroy()


def main() -> int:
    if sys.platform != "win32":
        print("This widget is designed for Windows, but the local scanner itself is cross-platform.")
    try:
        app = UsageWidget()
        app.mainloop()
        return 0
    except tk.TclError as exc:
        messagebox.showerror(APP_NAME, f"Tkinter failed to start:\n{exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
