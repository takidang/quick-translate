"""Các lớp phủ màn hình (overlay): chọn khung chat, ghim ô nhập, và viền khung đã khóa."""

from __future__ import annotations

import ctypes
from typing import Optional

from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QKeyEvent, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSizeGrip, QVBoxLayout, QWidget

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


class SubtitleOverlay(QWidget):
    """Khung phụ đề nổi (Always-on-top) chỉ hiển thị phần dịch cho Game / Phim."""

    select_region_clicked = Signal()
    translate_now_clicked = Signal()
    toggle_auto_clicked = Signal()
    clear_context_clicked = Signal()
    toggle_lock_clicked = Signal()
    exit_subtitle_mode_clicked = Signal()
    quit_app_clicked = Signal()

    def __init__(self, font_size: int = 15) -> None:
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMinimumSize(360, 110)
        self.resize(760, 140)

        self._drag_offset: Optional[QPoint] = None
        self._click_through = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 8, 14, 10)
        layout.setSpacing(6)

        # Thanh công cụ mini (ẩn khi khóa xuyên chuột để không vướng màn hình game/phim)
        self._toolbar = QWidget(self)
        tb_layout = QHBoxLayout(self._toolbar)
        tb_layout.setContentsMargins(0, 0, 0, 0)
        tb_layout.setSpacing(4)

        self._status_label = QLabel("🎮 Chế độ Game / Phim  •  Ngữ cảnh: 0 câu")
        self._status_label.setStyleSheet(
            "color: #94a3b8; font-size: 11px; font-weight: 600; background: transparent;"
        )
        tb_layout.addWidget(self._status_label)
        tb_layout.addStretch()

        btn_style = (
            "QPushButton { background: rgba(30, 41, 59, 190); color: #e2e8f0; "
            "border: 1px solid rgba(100, 116, 139, 140); border-radius: 5px; "
            "padding: 2px 7px; font-size: 11px; font-weight: 600; }"
            "QPushButton:hover { background: rgba(51, 65, 85, 230); }"
        )

        self._btn_region = QPushButton("📐 Khung")
        self._btn_region.setToolTip("Chọn vùng phụ đề/thoại trên màn hình (Ctrl+Shift+S)")
        self._btn_region.setStyleSheet(btn_style)
        self._btn_region.clicked.connect(self.select_region_clicked.emit)

        self._btn_translate = QPushButton("⚡ Dịch")
        self._btn_translate.setToolTip("Dịch ngay (Ctrl+Shift+D)")
        self._btn_translate.setStyleSheet(btn_style)
        self._btn_translate.clicked.connect(self.translate_now_clicked.emit)

        self._btn_auto = QPushButton("▶ Tự động")
        self._btn_auto.setToolTip("Bật/Tắt tự động dịch khi có thoại mới")
        self._btn_auto.setStyleSheet(btn_style)
        self._btn_auto.clicked.connect(self.toggle_auto_clicked.emit)

        self._btn_clear = QPushButton("🧹")
        self._btn_clear.setToolTip("Xóa bộ nhớ ngữ cảnh (khi đổi game/phim khác)")
        self._btn_clear.setStyleSheet(btn_style)
        self._btn_clear.clicked.connect(self.clear_context_clicked.emit)

        self._btn_lock = QPushButton("📌 Khóa chuột")
        self._btn_lock.setToolTip("Khóa xuyên chuột khi chơi game (nhấn Ctrl+Shift+L để mở khóa)")
        self._btn_lock.setStyleSheet(btn_style)
        self._btn_lock.clicked.connect(self.toggle_lock_clicked.emit)

        self._btn_back = QPushButton("💬 Chat")
        self._btn_back.setToolTip("Quay lại giao diện đầy đủ (Ctrl+Shift+M)")
        self._btn_back.setStyleSheet(btn_style)
        self._btn_back.clicked.connect(self.exit_subtitle_mode_clicked.emit)

        self._btn_quit = QPushButton("✕")
        self._btn_quit.setToolTip("Thoát hoàn toàn QuickTranslate")
        self._btn_quit.setStyleSheet(
            "QPushButton { background: rgba(185, 28, 28, 200); color: #ffffff; "
            "border: 1px solid rgba(248, 113, 113, 160); border-radius: 5px; "
            "padding: 2px 7px; font-size: 11px; font-weight: 700; }"
            "QPushButton:hover { background: rgba(220, 38, 38, 240); }"
        )
        self._btn_quit.clicked.connect(self.quit_app_clicked.emit)

        for b in (
            self._btn_region,
            self._btn_translate,
            self._btn_auto,
            self._btn_clear,
            self._btn_lock,
            self._btn_back,
            self._btn_quit,
        ):
            tb_layout.addWidget(b)

        layout.addWidget(self._toolbar)

        # Nội dung phụ đề đã dịch
        self._subtitle_label = QLabel(
            "Chọn khung phụ đề (Ctrl+Shift+S) rồi bật Tự động hoặc bấm Ctrl+Shift+D để dịch..."
        )
        self._subtitle_label.setWordWrap(True)
        self._subtitle_label.setAlignment(
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter
        )
        self.set_font_size(font_size)
        layout.addWidget(self._subtitle_label, stretch=1)

        # Tay nắm đổi kích thước ở góc phải dưới
        grip_row = QHBoxLayout()
        grip_row.setContentsMargins(0, 0, 0, 0)
        grip_row.addStretch()
        self._size_grip = QSizeGrip(self)
        self._size_grip.setFixedSize(14, 14)
        grip_row.addWidget(self._size_grip)
        layout.addLayout(grip_row)

    def set_font_size(self, size: int) -> None:
        clamped = max(10, min(32, int(size)))
        self._subtitle_label.setFont(QFont("Segoe UI", clamped, QFont.Weight.DemiBold))
        self._subtitle_label.setStyleSheet(
            "color: #f8fafc; background: transparent; padding: 2px 6px;"
        )

    def set_subtitle_text(self, text: str) -> None:
        self._subtitle_label.setText(text.strip() or "(Không có lời thoại)")

    def set_status(self, text: str, context_count: int, auto_on: bool) -> None:
        self._status_label.setText(f"🎮 {text}  •  Ngữ cảnh: {context_count} câu")
        self._btn_auto.setText("⏸ Đang tự động" if auto_on else "▶ Tự động")

    def set_click_through(self, locked: bool) -> None:
        self._click_through = locked
        self._toolbar.setVisible(not locked)
        self._size_grip.setVisible(not locked)
        flags = (
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        if locked:
            flags |= Qt.WindowType.WindowTransparentForInput
        was_visible = self.isVisible()
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, locked)
        if was_visible:
            self.show()
        self.update()

    def is_click_through(self) -> bool:
        return self._click_through

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        bg_alpha = 185 if self._click_through else 215
        painter.setBrush(QColor(10, 14, 24, bg_alpha))
        border_color = QColor(56, 189, 248, 70) if self._click_through else QColor(148, 163, 184, 110)
        painter.setPen(QPen(border_color, 1.5))
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 12, 12)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if not self._click_through and event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._drag_offset is not None and not self._click_through:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self._drag_offset = None

