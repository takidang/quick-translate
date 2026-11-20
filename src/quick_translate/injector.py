"""Điền nhanh văn bản đã dịch vào đúng vị trí con trỏ của khung chat trên Windows."""

from __future__ import annotations

import ctypes
import time
from typing import Optional

import pyperclip
from pynput.keyboard import Controller as KeyboardController
from pynput.keyboard import Key

from .config import TargetPoint

# Win32 constants for mouse click at exact physical coordinates
_MOUSEEVENTF_LEFTDOWN = 0x0002
_MOUSEEVENTF_LEFTUP = 0x0004


def _win32_click_physical(x: int, y: int) -> None:
    """Di chuyển chuột tới tọa độ vật lý (x, y) và click trái để đặt con trỏ."""
    user32 = ctypes.windll.user32
    user32.SetCursorPos(int(x), int(y))
    time.sleep(0.04)
    user32.mouse_event(_MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.02)
    user32.mouse_event(_MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)


def inject_text(
    text: str,
    target_point: Optional[TargetPoint],
    auto_press_enter: bool = False,
    restore_clipboard: bool = True,
) -> None:
    """
    Điền `text` vào ô chat đã ghim:
    1. Lưu clipboard cũ (nếu bật restore_clipboard).
    2. Copy `text` vào clipboard.
    3. Click vào `target_point` (nếu có) để đưa con trỏ văn bản vào đúng ô chat.
    4. Nhấn Ctrl+V (và Enter nếu bật auto_press_enter).
    5. Khôi phục clipboard cũ.
    """
    if not text:
        return

    old_clipboard: Optional[str] = None
    if restore_clipboard:
        try:
            old_clipboard = pyperclip.paste()
        except Exception:
            old_clipboard = None

    pyperclip.copy(text)

    if target_point is not None:
        _win32_click_physical(target_point.x, target_point.y)
        time.sleep(0.12)

    kb = KeyboardController()
    with kb.pressed(Key.ctrl):
        kb.press("v")
        kb.release("v")

    if auto_press_enter:
        time.sleep(0.06)
        kb.press(Key.enter)
        kb.release(Key.enter)

    if restore_clipboard and old_clipboard is not None:
        time.sleep(0.18)
        try:
            pyperclip.copy(old_clipboard)
        except Exception:
            pass
