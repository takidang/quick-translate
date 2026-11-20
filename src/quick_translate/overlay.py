"""Các lớp phủ màn hình (overlay): chọn khung chat, ghim ô nhập, và viền khung đã khóa."""

from __future__ import annotations

import ctypes
from typing import Optional

from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QKeyEvent, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import QWidget

from .config import RectRegion, TargetPoint


class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


def _get_physical_cursor_pos() -> tuple[int, int]:
    """Lấy tọa độ chuột theo physical pixels (khớp tuyệt đối với mss & Win32)."""
    pt = _POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
    return int(pt.x), int(pt.y)


def _virtual_desktop_rect() -> QRect:
    rect = QRect()
    for screen in QGuiApplication.screens():
        rect = rect.united(screen.geometry())
    return rect


def _physical_to_logical_rect(region: RectRegion) -> QRect:
    """Chuyển RectRegion (physical pixels) sang tọa độ logical của Qt để vẽ viền khớp DPI."""
    for screen in QGuiApplication.screens():
        dpr = screen.devicePixelRatio() or 1.0
        geo = screen.geometry()
        phys_left = int(round(geo.left() * dpr))
        phys_top = int(round(geo.top() * dpr))
        phys_right = phys_left + int(round(geo.width() * dpr))
        phys_bottom = phys_top + int(round(geo.height() * dpr))
        cx = region.x + region.width // 2
        cy = region.y + region.height // 2
        if phys_left <= cx <= phys_right and phys_top <= cy <= phys_bottom:
            return QRect(
                int(round(region.x / dpr)),
                int(round(region.y / dpr)),
                int(round(region.width / dpr)),
                int(round(region.height / dpr)),
            )
    dpr = QGuiApplication.primaryScreen().devicePixelRatio() or 1.0
    return QRect(
        int(round(region.x / dpr)),
        int(round(region.y / dpr)),
        int(round(region.width / dpr)),
        int(round(region.height / dpr)),
    )


class RegionSelectorOverlay(QWidget):
    """Lớp phủ toàn màn hình cho phép kéo chuột chọn khung chat cần khóa."""

    region_selected = Signal(object)  # RectRegion
    cancelled = Signal()

    def __init__(self) -> None:
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setCursor(Qt.CursorShape.CrossCursor)

        self._dragging = False
        self._start_local = QPoint()
        self._end_local = QPoint()
        self._start_phys = (0, 0)
        self._end_phys = (0, 0)

        self.setGeometry(_virtual_desktop_rect())

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Nền tối mờ
        painter.fillRect(self.rect(), QColor(10, 14, 24, 115))

        # Thanh hướng dẫn trên cùng
        banner = QRect(self.width() // 2 - 260, 24, 520, 42)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(18, 24, 38, 230))
        painter.drawRoundedRect(banner, 10, 10)
        painter.setPen(QColor("#e2e8f0"))
        painter.setFont(QFont("Segoe UI", 10, QFont.Weight.DemiBold))
        painter.drawText(
            banner,
            Qt.AlignmentFlag.AlignCenter,
            "Kéo chuột chọn khung chat cần khóa  •  Nhấn ESC để hủy",
        )

        if self._dragging:
            sel = QRect(self._start_local, self._end_local).normalized()
            # Làm sáng vùng đang chọn
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            painter.fillRect(sel, Qt.GlobalColor.transparent)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

            painter.fillRect(sel, QColor(56, 189, 248, 22))
            pen = QPen(QColor("#38bdf8"), 2.5)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(sel)

            size_text = f"{sel.width()} × {sel.height()}"
            painter.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            painter.setPen(QColor("#38bdf8"))
            painter.drawText(sel.left() + 6, max(18, sel.top() - 6), size_text)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._start_local = event.position().toPoint()
            self._end_local = self._start_local
            self._start_phys = _get_physical_cursor_pos()
            self._end_phys = self._start_phys
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._dragging:
            self._end_local = event.position().toPoint()
            self._end_phys = _get_physical_cursor_pos()
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self._dragging:
            self._dragging = False
            self._end_phys = _get_physical_cursor_pos()
            x1, y1 = self._start_phys
            x2, y2 = self._end_phys
            left, right = min(x1, x2), max(x1, x2)
            top, bottom = min(y1, y2), max(y1, y2)
            region = RectRegion(x=left, y=top, width=right - left, height=bottom - top)
            self.close()
            if region.is_valid():
                self.region_selected.emit(region)
            else:
                self.cancelled.emit()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            self.cancelled.emit()


class PointPickerOverlay(QWidget):
    """Lớp phủ cho phép click 1 điểm để ghim vị trí ô nhập tin nhắn trong khung chat."""

    point_selected = Signal(object)  # TargetPoint
    cancelled = Signal()

    def __init__(self) -> None:
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self._mouse_pos: Optional[QPoint] = None
        self.setMouseTracking(True)
        self.setGeometry(_virtual_desktop_rect())

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(10, 14, 24, 95))

        banner = QRect(self.width() // 2 - 280, 24, 560, 42)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(18, 24, 38, 235))
        painter.drawRoundedRect(banner, 10, 10)
        painter.setPen(QColor("#fde68a"))
        painter.setFont(QFont("Segoe UI", 10, QFont.Weight.DemiBold))
        painter.drawText(
            banner,
            Qt.AlignmentFlag.AlignCenter,
            "Click vào ô nhập tin nhắn của khung chat muốn điền  •  ESC để hủy",
        )

        if self._mouse_pos is not None:
            pen = QPen(QColor("#fbbf24"), 1.5, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.drawLine(0, self._mouse_pos.y(), self.width(), self._mouse_pos.y())
            painter.drawLine(self._mouse_pos.x(), 0, self._mouse_pos.x(), self.height())
            painter.setBrush(QColor(251, 191, 36, 90))
            painter.drawEllipse(self._mouse_pos, 10, 10)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self._mouse_pos = event.position().toPoint()
        self.update()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            px, py = _get_physical_cursor_pos()
            self.close()
            self.point_selected.emit(TargetPoint(x=px, y=py))

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            self.cancelled.emit()


class RegionBorderOverlay(QWidget):
    """Viền khung nổi luôn ở trên cùng, click-through hoàn toàn để đánh dấu vùng chat đã khóa."""

    def __init__(self) -> None:
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._border_color = QColor("#22c55e")
        self._pad = 4

    def set_region(self, region: Optional[RectRegion], visible: bool = True) -> None:
        if region is None or not region.is_valid() or not visible:
            self.hide()
            return
        logical = _physical_to_logical_rect(region)
        padded = logical.adjusted(-self._pad, -self._pad, self._pad, self._pad)
        self.setGeometry(padded)
        self.show()
        self.update()

    def set_active_translating(self, busy: bool) -> None:
        self._border_color = QColor("#38bdf8") if busy else QColor("#22c55e")
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(self._border_color, 2.5)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        r = self.rect().adjusted(2, 2, -2, -2)
        painter.drawRoundedRect(r, 4, 4)
