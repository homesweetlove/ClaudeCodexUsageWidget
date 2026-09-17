from __future__ import annotations

import time
import tkinter as tk

from usage_widget import LocalUsageScanner, ProviderSnapshot, load_config, save_config


class CompactUsageWidget(tk.Tk):
    """Thin horizontal desktop widget for Claude + Codex remaining usage."""

    WIDTH = 380
    HEIGHT = 126

    BG = "#0d0d0f"
    CARD = "#151517"
    TEXT = "#f3f3f4"
    MUTED = "#8f8f96"
    BORDER = "#2a2a2e"
    TRACK = "#303035"
    FILL = "#d7d7db"
    FILL_LOW = "#8f8f96"

    def __init__(self):
        super().__init__()
        self.config_data = load_config()
        self.scanner = LocalUsageScanner()
        self.refresh_job = None
        self.drag_origin = None
        self.rows: dict[str, dict[str, object]] = {}

        self.title("ClaudeCodexUsageWidget")
        self.configure(bg=self.BG)
        self.overrideredirect(True)
        self.resizable(False, False)
        self.attributes("-topmost", bool(self.config_data.get("always_on_top", True)))

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
        shell = tk.Frame(
            self,
            bg=self.CARD,
            width=self.WIDTH,
            height=self.HEIGHT,
            highlightbackground=self.BORDER,
            highlightthickness=1,
        )
        shell.pack(fill="both", expand=True)
        shell.pack_propagate(False)

        header = tk.Frame(shell, bg=self.CARD, height=34)
        header.pack(fill="x", padx=12, pady=(8, 2))
        header.pack_propagate(False)

        title_wrap = tk.Frame(header, bg=self.CARD)
        title_wrap.pack(side="left", fill="y")
        tk.Label(
            title_wrap,
            text="AI USAGE",
            bg=self.CARD,
            fg=self.TEXT,
            font=("Segoe UI Semibold", 9),
        ).pack(side="left", pady=(2, 0))
        self.status_dot = tk.Label(
            title_wrap,
            text="  local",
            bg=self.CARD,
            fg=self.MUTED,
            font=("Segoe UI", 8),
        )
        self.status_dot.pack(side="left", pady=(3, 0))

        self.close_btn = self._tiny_button(header, "×", self.destroy)
        self.close_btn.pack(side="right", padx=(3, 0))
        self.pin_btn = self._tiny_button(
            header,
            "●" if self.config_data.get("always_on_top", True) else "○",
            self.toggle_topmost,
        )
        self.pin_btn.pack(side="right", padx=(3, 0))
        self.refresh_btn = self._tiny_button(header, "↻", self.refresh)
        self.refresh_btn.pack(side="right")

        body = tk.Frame(shell, bg=self.CARD)
        body.pack(fill="both", expand=True, padx=12, pady=(0, 8))

        self._build_provider_row(body, "Claude")
        self._build_provider_row(body, "Codex")

    def _tiny_button(self, parent, text, command):
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=self.CARD,
            fg=self.MUTED,
            activebackground=self.CARD,
            activeforeground=self.TEXT,
            relief="flat",
            bd=0,
            width=2,
            height=1,
            cursor="hand2",
            font=("Segoe UI", 9),
            padx=0,
            pady=0,
        )

    def _build_provider_row(self, parent, provider: str):
        row = tk.Frame(parent, bg=self.CARD, height=36)
        row.pack(fill="x", pady=1)
        row.pack_propagate(False)

        left = tk.Frame(row, bg=self.CARD, width=62)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)
        tk.Label(
            left,
            text=provider,
            bg=self.CARD,
            fg=self.TEXT,
            font=("Segoe UI Semibold", 9),
        ).pack(anchor="w", pady=(1, 0))
        reset_label = tk.Label(
            left,
            text="reading…",
            bg=self.CARD,
            fg=self.MUTED,
            font=("Segoe UI", 7),
        )
        reset_label.pack(anchor="w")

        percent_label = tk.Label(
            row,
            text="--%",
            bg=self.CARD,
            fg=self.TEXT,
            font=("Segoe UI Semibold", 12),
            width=4,
            anchor="e",
        )
        percent_label.pack(side="right", fill="y", padx=(7, 0), pady=(6, 0))

        bar_wrap = tk.Frame(row, bg=self.CARD)
        bar_wrap.pack(side="left", fill="both", expand=True, padx=(5, 0))
        canvas = tk.Canvas(
            bar_wrap,
            height=8,
            bg=self.CARD,
            highlightthickness=0,
            bd=0,
        )
        canvas.pack(fill="x", pady=(13, 0))

        self.rows[provider] = {
            "canvas": canvas,
            "percent": percent_label,
            "reset": reset_label,
            "value": None,
        }

        canvas.bind("<Configure>", lambda _e, p=provider: self._draw_bar(p))

    def _pick_window(self, snapshot: ProviderSnapshot):
        if not snapshot.windows:
            return None
        for window in snapshot.windows:
            label = window.label.lower()
            if "5" in label or "primary" in label or "hour" in label:
                return window
        return snapshot.windows[0]

    @staticmethod
    def _short_reset(timestamp: float | None) -> str:
        if timestamp is None:
            return "reset --"
        seconds = max(0, int(timestamp - time.time()))
        if seconds <= 0:
            return "reset now"
        if seconds >= 86400:
            return f"reset {seconds // 86400}d"
        if seconds >= 3600:
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60
            return f"reset {hours}h {minutes}m"
        return f"reset {max(1, seconds // 60)}m"

    def _render_snapshot(self, snapshot: ProviderSnapshot):
        controls = self.rows[snapshot.provider]
        window = self._pick_window(snapshot)

        if window is None or window.remaining_percent is None:
            controls["value"] = None
            controls["percent"].config(text="--%", fg=self.MUTED)
            controls["reset"].config(text="unavailable")
            self._draw_bar(snapshot.provider)
            return

        remaining = max(0.0, min(100.0, float(window.remaining_percent)))
        controls["value"] = remaining
        controls["percent"].config(text=f"{remaining:.0f}%", fg=self.TEXT)
        controls["reset"].config(text=self._short_reset(window.resets_at))
        self._draw_bar(snapshot.provider)

    def _draw_bar(self, provider: str):
        controls = self.rows.get(provider)
        if not controls:
            return
        canvas: tk.Canvas = controls["canvas"]
        value = controls.get("value")
        canvas.delete("all")
        width = max(1, canvas.winfo_width())
        height = 8
        radius = 4

        canvas.create_rectangle(radius, 0, width - radius, height, fill=self.TRACK, outline="")
        canvas.create_oval(0, 0, height, height, fill=self.TRACK, outline="")
        canvas.create_oval(width - height, 0, width, height, fill=self.TRACK, outline="")

        if value is None:
            return

        fill_width = max(0, min(width, width * float(value) / 100.0))
        if fill_width <= 1:
            return
        fill_color = self.FILL if float(value) >= 15 else self.FILL_LOW
        if fill_width <= height:
            canvas.create_oval(0, 0, fill_width, height, fill=fill_color, outline="")
        else:
            canvas.create_rectangle(radius, 0, fill_width - radius, height, fill=fill_color, outline="")
            canvas.create_oval(0, 0, height, height, fill=fill_color, outline="")
            canvas.create_oval(fill_width - height, 0, fill_width, height, fill=fill_color, outline="")

    def refresh(self):
        if self.refresh_job is not None:
            try:
                self.after_cancel(self.refresh_job)
            except tk.TclError:
                pass
            self.refresh_job = None

        self.status_dot.config(text="  scanning…")
        self.update_idletasks()

        claude = self.scanner.scan_claude()
        codex = self.scanner.scan_codex()
        self._render_snapshot(claude)
        self._render_snapshot(codex)
        self.status_dot.config(text="  local only")

        seconds = int(self.config_data.get("refresh_seconds", 30))
        self.refresh_job = self.after(max(10, seconds) * 1000, self.refresh)

    def toggle_topmost(self):
        enabled = not bool(self.config_data.get("always_on_top", True))
        self.config_data["always_on_top"] = enabled
        self.attributes("-topmost", enabled)
        self.pin_btn.config(text="●" if enabled else "○")
        save_config(self.config_data)

    def _restore_position(self):
        x = self.config_data.get("compact_window_x")
        y = self.config_data.get("compact_window_y")
        if isinstance(x, int) and isinstance(y, int):
            self.geometry(f"{self.WIDTH}x{self.HEIGHT}+{x}+{y}")
            return

        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        x = max(16, screen_w - self.WIDTH - 28)
        y = max(60, min(screen_h - self.HEIGHT - 60, int(screen_h * 0.52)))
        self.geometry(f"{self.WIDTH}x{self.HEIGHT}+{x}+{y}")

    def _begin_drag(self, event):
        if isinstance(event.widget, tk.Button):
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
            self.config_data["compact_window_x"] = self.winfo_x()
            self.config_data["compact_window_y"] = self.winfo_y()
            save_config(self.config_data)
        self.drag_origin = None

    def destroy(self):
        try:
            self.config_data["compact_window_x"] = self.winfo_x()
            self.config_data["compact_window_y"] = self.winfo_y()
            save_config(self.config_data)
        except tk.TclError:
            pass
        super().destroy()


def main() -> int:
    app = CompactUsageWidget()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
