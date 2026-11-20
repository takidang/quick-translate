"""Điểm khởi chạy ứng dụng QuickTranslate."""

from __future__ import annotations

import os
import sys

from PySide6.QtWidgets import QApplication

from .ui import DARK_STYLESHEET, MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("QuickTranslate")
    app.setQuitOnLastWindowClosed(True)
    app.setStyleSheet(DARK_STYLESHEET)

    window = MainWindow()
    window.show()
    code = app.exec()
    # Thoát tiến trình ngay lập tức để thread nền (pynput / HTTP) không giữ .exe treo ngầm
    os._exit(code)


if __name__ == "__main__":
    raise SystemExit(main())
