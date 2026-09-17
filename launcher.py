from __future__ import annotations

from usage_widget import UsageWidget


class AutoSizedUsageWidget(UsageWidget):
    """Keep the widget content-sized while preserving the saved screen position."""

    def _restore_position(self):
        x = self.config_data.get("window_x")
        y = self.config_data.get("window_y")
        if isinstance(x, int) and isinstance(y, int):
            self.geometry(f"+{x}+{y}")
            return

        self.update_idletasks()
        width = max(360, self.winfo_reqwidth())
        screen_w = self.winfo_screenwidth()
        self.geometry(f"+{max(20, screen_w - width - 28)}+80")


def main() -> int:
    app = AutoSizedUsageWidget()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
