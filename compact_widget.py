from __future__ import annotations

import ctypes
import sys
import time
import tkinter as tk

from usage_widget import LocalUsageScanner, ProviderSnapshot, load_config, save_config


class CompactUsageWidget(tk.Tk):
    """macOS/iOS-inspired horizontal usage widget for Claude + Codex."""

    WIDTH = 392
    HEIGHT = 136

    BG = "#141416"
    SURFACE = "#1c1c1e"
    SURFACE_2 = "#242426"
    TEXT = "#f5f5f7"
    MUTED = "#98989f"
    DIM = "#68686f"
    TRACK = "#343438"
    FILL = "#f2f2f7"
    FILL_LOW = "#8e8e93"
    DIVIDER = "#2c2c2e"

    FONT = "Segoe UI Variable Text"
    FONT_DISPLAY = "Segoe UI Variable Display"

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
        try:
            self.attributes("-alpha", 0.975)
        except tk.TclError:
            pass

        self._build_ui()
        self.update_idletasks()
        self._apply_windows_rounding()
        self._restore_position()

        self.bind("<ButtonPress-1>", self._begin_drag, add="+")
        self.bind("<B1-Motion>", self._drag, add="+")
        self.bind("<ButtonRelease-1>", self._end_drag, add="+")
        self.bind("<Escape>", lambda _e: self.destroy())
        self.protocol("WM_DELETE_WINDOW", self.destroy)

        self.after(80, self.refresh)

    def _apply_windows_rounding(self):
        if sys.platform != "win32":
            return
        try:
            hwnd = self.winfo_id()
            DWMWA_WINDOW_CORNER_PREFERENCE = 33
            DWMWCP_ROUND = ctypes.c_int(2)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd,
                DWMWA_WINDOW_CORNER_PREFERENCE,
                ctypes.byref(DWMWCP_ROUND),
                ctypes.sizeof(DWMWCP_ROUND),
            )
        except Exception:
            pass

    def _build_ui(self):
        shell = tk.Frame(
            self,
            bg=self.SURFACE,
            width=self.WIDTH,
            height=self.HEIGHT,
            highlightbackground=self.DIVIDER,
            highlightthickness=1,
        )
        shell.pack(fill="both", expand=True)
        shell.pack_propagate(False)

        header = tk.Frame(shell, bg=self.SURFACE, height=38)
        header.pack(fill="x", padx=16, pady=(9, 0))
        header.pack_propagate(False)

        title_area = tk.Frame(header, bg=self.SURFACE)
        title_area.pack(side="left", fill="y")
        tk.Label(
            title_area,
            text="AI Usage",
            bg=self.SURFACE,
            fg=self.TEXT,
            font=(self.FONT_DISPLAY, 11, "bold"),
        ).pack(side="left", pady=(2, 0))

        self.status_label = tk.Label(
            title_area,
            text="  Local",
            bg=self.SURFACE,
            fg=self.DIM,
            font=(self.FONT, 8),
        )
        self.status_label.pack(side="left", pady=(4, 0))

        controls = tk.Frame(header, bg=self.SURFACE)
        controls.pack(side="right")
        self.refresh_btn = self._circle_button(controls, "↻", self.refresh)
        self.refresh_btn.pack(side="left", padx=(0, 5))
        self.pin_btn = self._circle_button(
            controls,
            "●" if self.config_data.get("always_on_top", True) else "○",
            self.toggle_topmost,
        )
        self.pin_btn.pack(side="left", padx=(0, 5))
        self.close_btn = self._circle_button(controls, "×", self.destroy)
        self.close_btn.pack(side="left")

        divider = tk.Frame(shell, bg=self.DIVIDER, height=1)
        divider.pack(fill="x", padx=16)

        body = tk.Frame(shell, bg=self.SURFACE)
        body.pack(fill="both", expand=True, padx=16, pady=(5, 10))

        self._build_provider_row(body, "Claude")
        self._build_provider_row(body, "Codex")

    def _circle_button(self, parent, text, command):
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=self.SURFACE_2,
            fg=self.MUTED,
            activebackground="#303033",
            activeforeground=self.TEXT,
            relief="flat",
            bd=0,
            width=2,
            height=1,
            padx=1,
            pady=0,
            cursor="hand2",
            font=(self.FONT, 9),
            highlightthickness=0,
        )

    def _build_provider_row(self, parent, provider: str):
        row = tk.Frame(parent, bg=self.SURFACE, height=39)
        row.pack(fill="x", pady=2)
        row.pack_propagate(False)

        left = tk.Frame(row, bg=self.SURFACE, width=78)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)

        tk.Label(
            left,
            text=provider,
            bg=self.SURFACE,
            fg=self.TEXT,
            font=(self.FONT, 9, "bold"),
        ).pack(anchor="w", pady=(2, 0))

        reset_label = tk.Label(
            left,
            text="Reading…",
            bg=self.SURFACE,
            fg=self.DIM,
            font=(self.FONT, 7),
        )
        reset_label.pack(anchor="w", pady=(0, 0))

        percent_label = tk.Label(
            row,
            text="--%",
            bg=self.SURFACE,
            fg=self.TEXT,
            font=(self.FONT_DISPLAY, 16, "bold"),
            width=4,
            anchor="e",
        )
        percent_label.pack(side="right", fill="y", padx=(10, 0), pady=(3, 0))

        bar_wrap = tk.Frame(row, bg=self.SURFACE)
        bar_wrap.pack(side="left", fill="both", expand=True, padx=(8, 0))

        canvas = tk.Canvas(
            bar_wrap,
            height=10,
            bg=self.SURFACE,
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
            return "Reset --"
        seconds = max(0, int(timestamp - time.time()))
        if seconds <= 0:
            return "Reset now"
        if seconds >= 86400:
            return f"Reset {seconds // 86400}d"
        if seconds >= 3600:
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60
            return f"Reset {hours}h {minutes}m"
        return f"Reset {max(1, seconds // 60)}m"

    def _render_snapshot(self, snapshot: ProviderSnapshot):
        controls = self.rows[snapshot.provider]
        window = self._pick_window(snapshot)

        if window is None or window.remaining_percent is None:
            controls["value"] = None
            controls["percent"].config(text="--%", fg=self.MUTED)
            controls["reset"].config(text="Unavailable")
            self._draw_bar(snapshot.provider)
            return

        remaining = max(0.0, min(100.0, float(window.remaining_percent)))
        controls["value"] = remaining
        controls["percent"].config(text=f"{remaining:.0f}%", fg=self.TEXT)
        controls["reset"].config(text=self._short_reset(window.resets_at))
        self._draw_bar(snapshot.provider)

    @staticmethod
    def _pill(canvas: tk.Canvas, x1: float, y1: float, x2: float, y2: float, fill: str):
        height = y2 - y1
        radius = height / 2
        if x2 - x1 <= height:
            canvas.create_oval(x1, y1, x2, y2, fill=fill, outline="")
            return
        canvas.create_rectangle(x1 + radius, y1, x2 - radius, y2, fill=fill, outline="")
        canvas.create_oval(x1, y1, x1 + height, y2, fill=fill, outline="")
        canvas.create_oval(x2 - height, y1, x2, y2, fill=fill, outline="")

    def _draw_bar(self, provider: str):
        controls = self.rows.get(provider)
        if not controls:
            return

        canvas: tk.Canvas = controls["canvas"]
        value = controls.get("value")
        canvas.delete("all")

        width = max(1, canvas.winfo_width())
        top = 1
        height = 8
        self._pill(canvas, 0, top, width, top + height, self.TRACK)

        if value is None:
            return

        fill_width = max(0.0, min(float(width), width * float(value) / 100.0))
        if fill_width <= 1:
            return
        fill = self.FILL if float(value) >= 15 else self.FILL_LOW
        self._pill(canvas, 0, top, fill_width, top + height, fill)

    def refresh(self):
        if self.refresh_job is not None:
            try:
                self.after_cancel(self.refresh_job)
            except tk.TclError:
                pass
            self.refresh_job = None

        self.status_label.config(text="  Updating…")
        self.update_idletasks()

        claude = self.scanner.scan_claude()
        codex = self.scanner.scan_codex()
        self._render_snapshot(claude)
        self._render_snapshot(codex)
        self.status_label.config(text="  Local only")

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
