"""Giao diện chính nổi (Floating Panel) và hộp thoại Cài đặt cho QuickTranslate."""

from __future__ import annotations

import time
from typing import Optional

from PIL import Image
from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QFont, QKeyEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .capture import capture_region, compute_diff_percent, image_to_png_bytes
from .config import AppConfig, RectRegion, TargetPoint
from .hotkeys import GlobalHotkeyManager
from .injector import inject_text
from .overlay import PointPickerOverlay, RegionBorderOverlay, RegionSelectorOverlay
from .translator import GeminiTranslator

DARK_STYLESHEET = """
QMainWindow, QDialog {
    background-color: #0f172a;
    color: #e2e8f0;
    font-family: "Segoe UI", sans-serif;
    font-size: 13px;
}
QLabel {
    color: #cbd5e1;
}
QPushButton {
    background-color: #1e293b;
    color: #f1f5f9;
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 6px 10px;
    font-weight: 600;
}
QPushButton:hover {
    background-color: #334155;
    border-color: #475569;
}
QPushButton:pressed {
    background-color: #0f172a;
}
QPushButton#primaryBtn {
    background-color: #2563eb;
    border-color: #3b82f6;
    color: #ffffff;
}
QPushButton#primaryBtn:hover {
    background-color: #1d4ed8;
}
QPushButton#accentBtn {
    background-color: #059669;
    border-color: #10b981;
    color: #ffffff;
}
QPushButton#accentBtn:hover {
    background-color: #047857;
}
QPlainTextEdit, QLineEdit, QComboBox, QDoubleSpinBox {
    background-color: #1e293b;
    color: #f8fafc;
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 6px;
}
QPlainTextEdit:focus, QLineEdit:focus {
    border-color: #38bdf8;
}
QCheckBox {
    color: #cbd5e1;
    spacing: 6px;
}
"""


class TranslateImageWorker(QThread):
    finished_ok = Signal(str, float)
    failed = Signal(str)

    def __init__(self, translator: GeminiTranslator, png_bytes: bytes) -> None:
        super().__init__()
        self._translator = translator
        self._png_bytes = png_bytes

    def run(self) -> None:
        t0 = time.perf_counter()
        try:
            text = self._translator.translate_chat_image(self._png_bytes)
            elapsed = time.perf_counter() - t0
            self.finished_ok.emit(text, elapsed)
        except Exception as exc:
            self.failed.emit(str(exc))


class TranslateReplyWorker(QThread):
    finished_ok = Signal(str, float)
    failed = Signal(str)

    def __init__(
        self,
        translator: GeminiTranslator,
        user_text: str,
        chat_context: str,
    ) -> None:
        super().__init__()
        self._translator = translator
        self._user_text = user_text
        self._chat_context = chat_context

    def run(self) -> None:
        t0 = time.perf_counter()
        try:
            translated = self._translator.translate_reply(
                self._user_text, self._chat_context
            )
            elapsed = time.perf_counter() - t0
            self.finished_ok.emit(translated, elapsed)
        except Exception as exc:
            self.failed.emit(str(exc))


class ReplyInputEdit(QPlainTextEdit):
    """Ô nhập tiếng Việt: Enter để dịch & điền nhanh, Shift+Enter để xuống dòng."""

    submit_requested = Signal()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                super().keyPressEvent(event)
            else:
                event.accept()
                self.submit_requested.emit()
            return
        super().keyPressEvent(event)


class SettingsDialog(QDialog):
    def __init__(self, config: AppConfig, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Cài đặt QuickTranslate")
        self.setMinimumWidth(460)
        self._config = config

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.backend_combo = QComboBox()
        self.backend_combo.addItem("Gemini API (Nhanh nhất — Free Tier / API Key)", "gemini_api")
        self.backend_combo.addItem("Gemini CLI (Dùng quota Google AI Pro)", "gemini_cli")
        idx = self.backend_combo.findData(config.backend)
        if idx >= 0:
            self.backend_combo.setCurrentIndex(idx)

        self.api_key_edit = QLineEdit(config.api_key)
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_edit.setPlaceholderText("Dán API Key từ aistudio.google.com...")

        self.model_combo = QComboBox()
        self.model_combo.setEditable(True)
        self.model_combo.addItems(
            [
                "gemini-2.5-flash",
                "gemini-2.5-flash-lite",
                "gemini-2.5-pro",
            ]
        )
        self.model_combo.setCurrentText(config.model)

        self.read_lang_edit = QLineEdit(config.target_language_read)
        self.write_lang_edit = QLineEdit(config.target_language_write)

        self.interval_spin = QDoubleSpinBox()
        self.interval_spin.setRange(0.8, 30.0)
        self.interval_spin.setSingleStep(0.5)
        self.interval_spin.setSuffix(" giây")
        self.interval_spin.setValue(config.auto_interval_sec)

        self.diff_spin = QDoubleSpinBox()
        self.diff_spin.setRange(0.5, 30.0)
        self.diff_spin.setSingleStep(0.5)
        self.diff_spin.setSuffix(" %")
        self.diff_spin.setValue(config.diff_threshold)

        self.show_border_cb = QCheckBox("Hiển thị viền xanh quanh khung chat đã khóa")
        self.show_border_cb.setChecked(config.show_border)

        self.restore_clip_cb = QCheckBox("Khôi phục clipboard cũ sau khi điền xong")
        self.restore_clip_cb.setChecked(config.restore_clipboard)

        form.addRow("Backend AI:", self.backend_combo)
        form.addRow("Gemini API Key:", self.api_key_edit)
        form.addRow("Model:", self.model_combo)
        form.addRow("Dịch khung chat sang:", self.read_lang_edit)
        form.addRow("Dịch tin nhắn đi sang:", self.write_lang_edit)
        form.addRow("Chu kỳ kiểm tra tự động:", self.interval_spin)
        form.addRow("Ngưỡng thay đổi ảnh:", self.diff_spin)
        form.addRow("", self.show_border_cb)
        form.addRow("", self.restore_clip_cb)

        layout.addLayout(form)

        tip = QLabel(
            "Phím tắt toàn cục:  Ctrl+Shift+S (Chọn khung)  •  "
            "Ctrl+Shift+T (Ghim ô chat)  •  Ctrl+Shift+D (Dịch ngay)"
        )
        tip.setWordWrap(True)
        tip.setStyleSheet("color: #94a3b8; font-size: 11px; margin-top: 6px;")
        layout.addWidget(tip)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def apply_to_config(self) -> None:
        self._config.backend = str(self.backend_combo.currentData())
        self._config.api_key = self.api_key_edit.text().strip()
        self._config.model = self.model_combo.currentText().strip() or "gemini-2.5-flash"
        self._config.target_language_read = self.read_lang_edit.text().strip() or "Tiếng Việt"
        self._config.target_language_write = self.write_lang_edit.text().strip() or "Tiếng Anh"
        self._config.auto_interval_sec = float(self.interval_spin.value())
        self._config.diff_threshold = float(self.diff_spin.value())
        self._config.show_border = self.show_border_cb.isChecked()
        self._config.restore_clipboard = self.restore_clip_cb.isChecked()
        self._config.save()


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.config = AppConfig.load()
        self.translator = GeminiTranslator(self.config)

        self._last_captured_img: Optional[Image.Image] = None
        self._last_translation: str = ""
        self._img_worker: Optional[TranslateImageWorker] = None
        self._reply_worker: Optional[TranslateReplyWorker] = None
        self._selector_overlay: Optional[RegionSelectorOverlay] = None
        self._picker_overlay: Optional[PointPickerOverlay] = None

        self._border_overlay = RegionBorderOverlay()
        self._hotkeys = GlobalHotkeyManager()

        self.setWindowTitle("QuickTranslate — Gemini")
        self.resize(450, 560)
        self._apply_always_on_top(self.config.always_on_top)
        self._build_ui()
        self._connect_signals()

        self._watch_timer = QTimer(self)
        self._watch_timer.timeout.connect(self._on_auto_watch_tick)
        self._sync_watch_timer()

        self._border_overlay.set_region(self.config.chat_region, self.config.show_border)
        self._update_status_badges()
        self._hotkeys.start()

        if len(self.config.window_geometry) == 4:
            x, y, w, h = self.config.window_geometry
            self.setGeometry(x, y, max(360, w), max(420, h))

    def _apply_always_on_top(self, on_top: bool) -> None:
        flags = self.windowFlags()
        if on_top:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        else:
            flags &= ~Qt.WindowType.WindowStaysOnTopHint
        was_visible = self.isVisible()
        self.setWindowFlags(flags)
        if was_visible:
            self.show()

    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        main_layout = QVBoxLayout(root)
        main_layout.setContentsMargins(12, 10, 12, 12)
        main_layout.setSpacing(8)

        # Hàng nút điều khiển chính
        top_row = QHBoxLayout()
        self.btn_select_region = QPushButton("📐 Chọn khung")
        self.btn_select_region.setToolTip("Chọn & khóa vùng khung chat trên màn hình (Ctrl+Shift+S)")

        self.btn_pick_input = QPushButton("🎯 Ghim ô chat")
        self.btn_pick_input.setToolTip("Click vào ô nhập tin nhắn để đặt con trỏ điền nhanh (Ctrl+Shift+T)")

        self.btn_translate = QPushButton("⚡ Dịch ngay")
        self.btn_translate.setObjectName("primaryBtn")
        self.btn_translate.setToolTip("Chụp khung đã khóa và dịch sang Tiếng Việt (Ctrl+Shift+D)")

        self.btn_settings = QPushButton("⚙")
        self.btn_settings.setFixedWidth(36)
        self.btn_settings.setToolTip("Cài đặt API Key, Model, Chu kỳ tự động...")

        top_row.addWidget(self.btn_select_region)
        top_row.addWidget(self.btn_pick_input)
        top_row.addWidget(self.btn_translate)
        top_row.addWidget(self.btn_settings)
        main_layout.addLayout(top_row)

        # Hàng tùy chọn nhanh
        opt_row = QHBoxLayout()
        self.cb_auto = QCheckBox("Tự động dịch khi có tin mới")
        self.cb_auto.setChecked(self.config.auto_translate)

        self.cb_on_top = QCheckBox("Luôn nổi")
        self.cb_on_top.setChecked(self.config.always_on_top)

        self.cb_border = QCheckBox("Viền khung")
        self.cb_border.setChecked(self.config.show_border)

        opt_row.addWidget(self.cb_auto)
        opt_row.addStretch()
        opt_row.addWidget(self.cb_border)
        opt_row.addWidget(self.cb_on_top)
        main_layout.addLayout(opt_row)

        # Nhãn trạng thái vùng chọn & ô chat
        self.lbl_info = QLabel()
        self.lbl_info.setStyleSheet("color: #94a3b8; font-size: 11px;")
        main_layout.addWidget(self.lbl_info)

        # Khu vực hiển thị bản dịch khung chat (Tiếng Việt)
        read_header = QHBoxLayout()
        lbl_read = QLabel("Bản dịch khung chat (Tiếng Việt):")
        lbl_read.setStyleSheet("font-weight: 600; color: #38bdf8;")
        self.lbl_status = QLabel("Sẵn sàng")
        self.lbl_status.setStyleSheet("color: #94a3b8; font-size: 11px;")
        read_header.addWidget(lbl_read)
        read_header.addStretch()
        read_header.addWidget(self.lbl_status)
        main_layout.addLayout(read_header)

        self.translation_view = QPlainTextEdit()
        self.translation_view.setReadOnly(True)
        self.translation_view.setPlaceholderText(
            "1. Bấm 'Chọn khung' để khóa vùng chat trên màn hình.\n"
            "2. Bấm 'Ghim ô chat' rồi click vào ô nhập tin nhắn của ứng dụng chat.\n"
            "3. Bấm 'Dịch ngay' (Ctrl+Shift+D) hoặc bật 'Tự động dịch'."
        )
        self.translation_view.setFont(QFont("Segoe UI", 10))
        main_layout.addWidget(self.translation_view, stretch=3)

        # Khu vực nhập tiếng Việt → dịch sang tiếng Anh & điền nhanh
        write_header = QHBoxLayout()
        lbl_write = QLabel("Trả lời nhanh (Tiếng Việt → Tiếng Anh):")
        lbl_write.setStyleSheet("font-weight: 600; color: #34d399;")
        self.cb_auto_enter = QCheckBox("Tự gửi (Enter)")
        self.cb_auto_enter.setChecked(self.config.auto_press_enter)
        self.cb_auto_enter.setToolTip(
            "Nếu bật, app sẽ tự nhấn Enter sau khi dán vào khung chat."
        )
        write_header.addWidget(lbl_write)
        write_header.addStretch()
        write_header.addWidget(self.cb_auto_enter)
        main_layout.addLayout(write_header)

        self.reply_input = ReplyInputEdit()
        self.reply_input.setPlaceholderText(
            "Gõ tiếng Việt ở đây rồi nhấn Enter để dịch sang Tiếng Anh & điền vào ô chat..."
        )
        self.reply_input.setFixedHeight(78)
        self.reply_input.setFont(QFont("Segoe UI", 10))
        main_layout.addWidget(self.reply_input)

        send_row = QHBoxLayout()
        self.lbl_last_sent = QLabel("")
        self.lbl_last_sent.setStyleSheet("color: #94a3b8; font-size: 11px;")
        self.lbl_last_sent.setWordWrap(True)

        self.btn_send = QPushButton("🚀 Dịch & Điền (Enter)")
        self.btn_send.setObjectName("accentBtn")
        send_row.addWidget(self.lbl_last_sent, stretch=1)
        send_row.addWidget(self.btn_send)
        main_layout.addLayout(send_row)

    def _connect_signals(self) -> None:
        self.btn_select_region.clicked.connect(self.start_region_selection)
        self.btn_pick_input.clicked.connect(self.start_point_picking)
        self.btn_translate.clicked.connect(lambda: self.trigger_translate_region(force=True))
        self.btn_settings.clicked.connect(self.open_settings)
        self.btn_send.clicked.connect(self.trigger_translate_and_fill)
        self.reply_input.submit_requested.connect(self.trigger_translate_and_fill)

        self.cb_auto.toggled.connect(self._on_auto_toggled)
        self.cb_on_top.toggled.connect(self._on_top_toggled)
        self.cb_border.toggled.connect(self._on_border_toggled)
        self.cb_auto_enter.toggled.connect(self._on_auto_enter_toggled)

        self._hotkeys.select_region_triggered.connect(self.start_region_selection)
        self._hotkeys.pick_input_triggered.connect(self.start_point_picking)
        self._hotkeys.translate_now_triggered.connect(
            lambda: self.trigger_translate_region(force=True)
        )

    def _update_status_badges(self) -> None:
        r = self.config.chat_region
        p = self.config.input_point
        region_txt = f"Khung: {r.width}×{r.height} @ ({r.x},{r.y})" if r else "Khung: Chưa chọn"
        point_txt = f"Ô chat: ({p.x},{p.y})" if p else "Ô chat: Chưa ghim"
        backend_txt = "API" if self.config.backend == "gemini_api" else "CLI"
        self.lbl_info.setText(f"{region_txt}   |   {point_txt}   |   {backend_txt}: {self.config.model}")

    def _sync_watch_timer(self) -> None:
        if self.config.auto_translate and self.config.chat_region is not None:
            ms = max(800, int(self.config.auto_interval_sec * 1000))
            self._watch_timer.start(ms)
        else:
            self._watch_timer.stop()

    def _on_auto_toggled(self, checked: bool) -> None:
        self.config.auto_translate = checked
        self.config.save()
        self._sync_watch_timer()
        if checked:
            self.lbl_status.setText("Đang theo dõi khung chat...")
            self.trigger_translate_region(force=False)
        else:
            self.lbl_status.setText("Đã tắt tự động dịch")

    def _on_top_toggled(self, checked: bool) -> None:
        self.config.always_on_top = checked
        self.config.save()
        self._apply_always_on_top(checked)

    def _on_border_toggled(self, checked: bool) -> None:
        self.config.show_border = checked
        self.config.save()
        self._border_overlay.set_region(self.config.chat_region, checked)

    def _on_auto_enter_toggled(self, checked: bool) -> None:
        self.config.auto_press_enter = checked
        self.config.save()

    def start_region_selection(self) -> None:
        self._border_overlay.hide()
        self._selector_overlay = RegionSelectorOverlay()
        self._selector_overlay.region_selected.connect(self._on_region_selected)
        self._selector_overlay.cancelled.connect(
            lambda: self._border_overlay.set_region(
                self.config.chat_region, self.config.show_border
            )
        )
        self._selector_overlay.show()
        self._selector_overlay.activateWindow()

    def _on_region_selected(self, region: RectRegion) -> None:
        self.config.chat_region = region
        self.config.save()
        self._last_captured_img = None
        self._border_overlay.set_region(region, self.config.show_border)
        self._update_status_badges()
        self._sync_watch_timer()
        self.lbl_status.setText("Đã khóa khung chat — đang dịch...")
        self.trigger_translate_region(force=True)

    def start_point_picking(self) -> None:
        self._picker_overlay = PointPickerOverlay()
        self._picker_overlay.point_selected.connect(self._on_point_selected)
        self._picker_overlay.show()
        self._picker_overlay.activateWindow()

    def _on_point_selected(self, point: TargetPoint) -> None:
        self.config.input_point = point
        self.config.save()
        self._update_status_badges()
        self.lbl_status.setText(f"Đã ghim ô nhập chat tại ({point.x}, {point.y})")

    def open_settings(self) -> None:
        dlg = SettingsDialog(self.config, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            dlg.apply_to_config()
            self._border_overlay.set_region(self.config.chat_region, self.config.show_border)
            self.cb_border.setChecked(self.config.show_border)
            self._sync_watch_timer()
            self._update_status_badges()
            self.lbl_status.setText("Đã lưu cài đặt")

    def _on_auto_watch_tick(self) -> None:
        if self._img_worker is not None and self._img_worker.isRunning():
            return
        self.trigger_translate_region(force=False)

    def trigger_translate_region(self, force: bool = True) -> None:
        region = self.config.chat_region
        if region is None or not region.is_valid():
            if force:
                QMessageBox.information(
                    self,
                    "Chưa chọn khung chat",
                    "Hãy bấm 'Chọn khung' (hoặc Ctrl+Shift+S) để khóa vùng chat trên màn hình trước.",
                )
            return

        if self._img_worker is not None and self._img_worker.isRunning():
            return

        try:
            img = capture_region(region)
        except Exception as exc:
            self.lbl_status.setText(f"Lỗi chụp màn hình: {exc}")
            return

        if not force:
            diff = compute_diff_percent(self._last_captured_img, img)
            if diff < self.config.diff_threshold:
                return

        self._last_captured_img = img
        png_bytes = image_to_png_bytes(img)

        self.lbl_status.setText("Đang dịch khung chat...")
        self.btn_translate.setEnabled(False)
        self._border_overlay.set_active_translating(True)

        self._img_worker = TranslateImageWorker(self.translator, png_bytes)
        self._img_worker.finished_ok.connect(self._on_image_translated)
        self._img_worker.failed.connect(self._on_image_translate_failed)
        self._img_worker.start()

    def _on_image_translated(self, text: str, elapsed: float) -> None:
        self._last_translation = text
        self.translation_view.setPlainText(text)
        self.lbl_status.setText(f"Đã dịch xong ({elapsed:.1f}s)")
        self.btn_translate.setEnabled(True)
        self._border_overlay.set_active_translating(False)

    def _on_image_translate_failed(self, err: str) -> None:
        self.lbl_status.setText("Lỗi dịch khung chat")
        self.translation_view.setPlainText(f"[Lỗi] {err}")
        self.btn_translate.setEnabled(True)
        self._border_overlay.set_active_translating(False)

    def trigger_translate_and_fill(self) -> None:
        user_text = self.reply_input.toPlainText().strip()
        if not user_text:
            return
        if self._reply_worker is not None and self._reply_worker.isRunning():
            return

        self.btn_send.setEnabled(False)
        self.reply_input.setEnabled(False)
        self.lbl_last_sent.setText("Đang dịch sang Tiếng Anh...")

        self._reply_worker = TranslateReplyWorker(
            self.translator, user_text, self._last_translation
        )
        self._reply_worker.finished_ok.connect(self._on_reply_translated)
        self._reply_worker.failed.connect(self._on_reply_failed)
        self._reply_worker.start()

    def _on_reply_translated(self, translated: str, elapsed: float) -> None:
        self.btn_send.setEnabled(True)
        self.reply_input.setEnabled(True)
        self.reply_input.clear()

        try:
            inject_text(
                translated,
                target_point=self.config.input_point,
                auto_press_enter=self.config.auto_press_enter,
                restore_clipboard=self.config.restore_clipboard,
            )
            if self.config.input_point is not None:
                self.lbl_last_sent.setText(f"Đã điền ({elapsed:.1f}s): {translated}")
            else:
                self.lbl_last_sent.setText(
                    f"Đã dán (chưa ghim ô chat, {elapsed:.1f}s): {translated}"
                )
        except Exception as exc:
            self.lbl_last_sent.setText(f"Đã dịch nhưng lỗi điền: {exc}")

    def _on_reply_failed(self, err: str) -> None:
        self.btn_send.setEnabled(True)
        self.reply_input.setEnabled(True)
        self.lbl_last_sent.setText(f"Lỗi: {err}")

    def closeEvent(self, event) -> None:  # noqa: N802
        g = self.geometry()
        self.config.window_geometry = [g.x(), g.y(), g.width(), g.height()]
        self.config.save()
        self._watch_timer.stop()
        self._hotkeys.stop()
        self._border_overlay.close()
        super().closeEvent(event)
