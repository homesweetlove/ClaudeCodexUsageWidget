from __future__ import annotations

from compact_widget import CompactUsageWidget


def main() -> int:
    app = CompactUsageWidget()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
