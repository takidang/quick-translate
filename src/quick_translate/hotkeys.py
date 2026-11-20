"""Phím tắt toàn cục (Global Hotkeys) dùng pynput phát tín hiệu an toàn về Qt."""

from __future__ import annotations

from typing import Optional

from pynput import keyboard
from PySide6.QtCore import QObject, Signal


class GlobalHotkeyManager(QObject):
    select_region_triggered = Signal()
    pick_input_triggered = Signal()
    translate_now_triggered = Signal()
    toggle_subtitle_mode_triggered = Signal()
    toggle_subtitle_lock_triggered = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._listener: Optional[keyboard.GlobalHotKeys] = None

    def start(self) -> None:
        if self._listener is not None:
            return
        mapping = {
            "<ctrl>+<shift>+s": self.select_region_triggered.emit,
            "<ctrl>+<shift>+t": self.pick_input_triggered.emit,
            "<ctrl>+<shift>+d": self.translate_now_triggered.emit,
            "<ctrl>+<shift>+m": self.toggle_subtitle_mode_triggered.emit,
            "<ctrl>+<shift>+l": self.toggle_subtitle_lock_triggered.emit,
        }
        try:
            self._listener = keyboard.GlobalHotKeys(mapping)
            self._listener.daemon = True
            self._listener.start()
        except Exception:
            self._listener = None

    def stop(self) -> None:
        if self._listener is not None:
            try:
                self._listener.stop()
            except Exception:
                pass
            self._listener = None
