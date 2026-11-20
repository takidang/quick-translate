"""Điểm khởi chạy ứng dụng QuickTranslate."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from .ui import DARK_STYLESHEET, MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("QuickTranslate")
    app.setStyleSheet(DARK_STYLESHEET)

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
