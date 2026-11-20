"""Giao diện chính nổi (Floating Panel) và hộp thoại Cài đặt cho QuickTranslate."""

from __future__ import annotations

import shutil
import time
import webbrowser
from typing import Optional

from PIL import Image
from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QFont, QKeyEvent
from PySide6.QtWidgets import (
    QApplication,
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
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .capture import capture_region, compute_diff_percent, image_to_jpeg_bytes
from .config import AppConfig, RectRegion, TargetPoint
from .hotkeys import GlobalHotkeyManager
from .injector import inject_text
from .ocr import extract_text_from_image, list_ocr_languages, normalize_ocr_text
from .overlay import PointPickerOverlay, RegionBorderOverlay, RegionSelectorOverlay, SubtitleOverlay
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
QPlainTextEdit, QLineEdit, QComboBox, QDoubleSpinBox, QSpinBox {
    background-color: #1e293b;
    color: #f8fafc;
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 5px 6px;
}
QPlainTextEdit:focus, QLineEdit:focus {
    border-color: #38bdf8;
}
QCheckBox {
    color: #cbd5e1;
    spacing: 6px;
}
"""


class TranslateRegionWorker(QThread):
    finished_ok = Signal(str, float, str, str)  # translated, elapsed, mode, ocr_text
    skipped_unchanged = Signal()
    failed = Signal(str)

    def __init__(
        self,
        translator: GeminiTranslator,
        img: Image.Image,
        use_local_ocr: bool,
        ocr_language: str,
        last_ocr_norm: str,
        force: bool,
        mode: str = "chat",
        history: Optional[list[str]] = None,
    ) -> None:
        super().__init__()
        self._translator = translator
        self._img = img
        self._use_local_ocr = use_local_ocr
        self._ocr_language = ocr_language
        self._last_ocr_norm = last_ocr_norm
        self._force = force
        self._mode = mode
        self._history = list(history or [])

    def run(self) -> None:
        t0 = time.perf_counter()
        try:
            if self._use_local_ocr or self._translator.config.backend == "google_free":
                raw_text = extract_text_from_image(self._img, lang_tag=self._ocr_language)
                norm = normalize_ocr_text(raw_text)
                if not self._force and norm == self._last_ocr_norm:
                    self.skipped_unchanged.emit()
                    return
                if not raw_text.strip():
                    empty_msg = (
                        "(Không có lời thoại)"
                        if self._mode == "game_movie"
                        else "(Không phát hiện nội dung văn bản)"
                    )
                    self.finished_ok.emit(empty_msg, time.perf_counter() - t0, self._mode, "")
                    return
                if self._mode == "game_movie":
                    translated = self._translator.translate_game_movie_text(
                        raw_text, history=self._history
                    )
                else:
                    translated = self._translator.translate_chat_text(raw_text)
                self.finished_ok.emit(
                    translated, time.perf_counter() - t0, self._mode, raw_text
                )
            else:
                img_bytes = image_to_jpeg_bytes(self._img)
                if self._mode == "game_movie":
                    translated = self._translator.translate_game_movie_image(
                        img_bytes, history=self._history
                    )
                else:
                    translated = self._translator.translate_chat_image(img_bytes)
                self.finished_ok.emit(
                    translated, time.perf_counter() - t0, self._mode, ""
                )
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
        self.setMinimumWidth(560)
        self._config = config

        layout = QVBoxLayout(self)
        form = QFormLayout()

        # 1. Chọn Backend AI
        self.backend_combo = QComboBox()
        self.backend_combo.addItem(
            "🌐 Dịch nhanh miễn phí (Google Translate — Không cần API Key)", "google_free"
        )
        self.backend_combo.addItem(
            "🏠 Local AI (Ollama / LM Studio — Offline, 0đ, siêu nhanh trên GPU)", "local_ollama"
        )
        self.backend_combo.addItem(
            "⚡ Cloud siêu nhanh (Groq / OpenRouter / DeepSeek / OpenAI)", "openai_compat"
        )
        self.backend_combo.addItem(
            "✨ Gemini API (API Key — có tự fallback khi 503)", "gemini_api"
        )
        self.backend_combo.addItem(
            "💻 Gemini CLI (Dùng quota Google AI Pro)", "gemini_cli"
        )
        idx = self.backend_combo.findData(config.backend)
        if idx >= 0:
            self.backend_combo.setCurrentIndex(idx)

        self.lbl_backend_hint = QLabel()
        self.lbl_backend_hint.setWordWrap(True)
        self.lbl_backend_hint.setStyleSheet("font-size: 11px;")

        # 2. Endpoint URL + nút preset nhanh (cho Local Ollama / LM Studio / Groq / OpenRouter)
        url_row = QHBoxLayout()
        self.url_edit = QLineEdit()
        self.btn_preset_1 = QPushButton("Ollama")
        self.btn_preset_2 = QPushButton("LM Studio")
        url_row.addWidget(self.url_edit, stretch=1)
        url_row.addWidget(self.btn_preset_1)
        url_row.addWidget(self.btn_preset_2)
        self.url_widget = QWidget()
        self.url_widget.setLayout(url_row)
        url_row.setContentsMargins(0, 0, 0, 0)

        # 3. API Key + nút lấy API Key miễn phí
        api_row = QHBoxLayout()
        api_row.setContentsMargins(0, 0, 0, 0)
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.btn_get_key = QPushButton("🔑 Lấy API Key")
        self.btn_get_key.clicked.connect(self._open_api_key_page)
        api_row.addWidget(self.api_key_edit, stretch=1)
        api_row.addWidget(self.btn_get_key)
        self.api_widget = QWidget()
        self.api_widget.setLayout(api_row)

        # 4. Model + nút Tải model
        model_row = QHBoxLayout()
        model_row.setContentsMargins(0, 0, 0, 0)
        self.model_combo = QComboBox()
        self.model_combo.setEditable(True)
        self.btn_refresh_models = QPushButton("🔄 Tải model")
        self.btn_refresh_models.clicked.connect(self._refresh_models)
        model_row.addWidget(self.model_combo, stretch=1)
        model_row.addWidget(self.btn_refresh_models)
        self.model_widget = QWidget()
        self.model_widget.setLayout(model_row)

        # 5. OCR cục bộ (Windows OCR)
        self.use_ocr_cb = QCheckBox(
            "Đọc chữ tại máy (Windows OCR — siêu nhanh ~0.1s, tiết kiệm token)"
        )
        self.use_ocr_cb.setChecked(config.use_local_ocr)

        self.ocr_lang_combo = QComboBox()
        self.ocr_lang_combo.addItem("Tự động (theo Windows)", "")
        for lang in list_ocr_languages():
            self.ocr_lang_combo.addItem(lang, lang)
        ocr_idx = self.ocr_lang_combo.findData(config.ocr_language)
        if ocr_idx >= 0:
            self.ocr_lang_combo.setCurrentIndex(ocr_idx)

        # 6. Ngôn ngữ & Tự động dịch
        self.read_lang_edit = QLineEdit(config.target_language_read)
        self.write_lang_edit = QLineEdit(config.target_language_write)

        self.interval_spin = QDoubleSpinBox()
        self.interval_spin.setRange(0.5, 30.0)
        self.interval_spin.setSingleStep(0.5)
        self.interval_spin.setSuffix(" giây")
        self.interval_spin.setValue(config.auto_interval_sec)

        # 7. Chế độ Game / Phim
        self.memory_spin = QSpinBox()
        self.memory_spin.setRange(0, 30)
        self.memory_spin.setSuffix(" câu gần nhất")
        self.memory_spin.setValue(config.context_memory_size)

        self.sub_font_spin = QSpinBox()
        self.sub_font_spin.setRange(10, 32)
        self.sub_font_spin.setSuffix(" pt")
        self.sub_font_spin.setValue(config.subtitle_font_size)

        self.glossary_edit = QLineEdit(config.story_glossary)
        self.glossary_edit.setPlaceholderText(
            "VD: Game kiếm hiệp, nhân vật chính tên Cloud, xưng hô tôi/cậu..."
        )

        self.show_border_cb = QCheckBox("Hiển thị viền xanh quanh khung đã khóa")
        self.show_border_cb.setChecked(config.show_border)

        self.restore_clip_cb = QCheckBox("Khôi phục clipboard cũ sau khi điền xong")
        self.restore_clip_cb.setChecked(config.restore_clipboard)

        form.addRow("Backend dịch:", self.backend_combo)
        form.addRow("", self.lbl_backend_hint)
        self.lbl_url_row = QLabel("Endpoint URL:")
        form.addRow(self.lbl_url_row, self.url_widget)
        self.lbl_api_row = QLabel("API Key:")
        form.addRow(self.lbl_api_row, self.api_widget)
        self.lbl_model_row = QLabel("Model:")
        form.addRow(self.lbl_model_row, self.model_widget)
        form.addRow("", self.use_ocr_cb)
        form.addRow("Ngôn ngữ OCR:", self.ocr_lang_combo)
        form.addRow("Dịch khung sang:", self.read_lang_edit)
        form.addRow("Dịch tin nhắn đi sang:", self.write_lang_edit)
        form.addRow("Chu kỳ kiểm tra tự động:", self.interval_spin)
        form.addRow("Nhớ ngữ cảnh Game/Phim:", self.memory_spin)
        form.addRow("Cỡ chữ phụ đề nổi:", self.sub_font_spin)
        form.addRow("Ghi chú Game/Phim:", self.glossary_edit)
        form.addRow("", self.show_border_cb)
        form.addRow("", self.restore_clip_cb)

        layout.addLayout(form)

        tip = QLabel(
            "Phím tắt:  Ctrl+Shift+S (Chọn khung)  •  Ctrl+Shift+T (Ghim ô chat)  •  "
            "Ctrl+Shift+D (Dịch ngay)  •  Ctrl+Shift+M (Game/Phim)  •  Ctrl+Shift+L (Khóa chuột)"
        )
        tip.setWordWrap(True)
        tip.setStyleSheet("color: #94a3b8; font-size: 11px; margin-top: 4px;")
        layout.addWidget(tip)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # Lưu tạm giá trị khi chuyển qua lại giữa các backend trong dialog
        self._draft_local_url = config.local_base_url
        self._draft_local_model = config.local_model
        self._draft_openai_url = config.openai_base_url
        self._draft_openai_key = config.openai_api_key
        self._draft_openai_model = config.openai_model
        self._draft_gemini_key = config.api_key
        self._draft_gemini_model = config.model
        self._active_backend = str(self.backend_combo.currentData())

        self.backend_combo.currentIndexChanged.connect(self._on_backend_changed)
        self.btn_preset_1.clicked.connect(self._on_preset_1)
        self.btn_preset_2.clicked.connect(self._on_preset_2)
        self._populate_backend_fields(self._active_backend)

    def _stash_current_backend_fields(self) -> None:
        b = self._active_backend
        if b == "local_ollama":
            self._draft_local_url = self.url_edit.text().strip()
            self._draft_local_model = self.model_combo.currentText().strip()
        elif b == "openai_compat":
            self._draft_openai_url = self.url_edit.text().strip()
            self._draft_openai_key = self.api_key_edit.text().strip()
            self._draft_openai_model = self.model_combo.currentText().strip()
        elif b in ("gemini_api", "gemini_cli"):
            self._draft_gemini_key = self.api_key_edit.text().strip()
            self._draft_gemini_model = self.model_combo.currentText().strip()

    def _on_backend_changed(self) -> None:
        self._stash_current_backend_fields()
        self._active_backend = str(self.backend_combo.currentData())
        self._populate_backend_fields(self._active_backend)

    def _populate_backend_fields(self, b: str) -> None:
        show_url = b in ("local_ollama", "openai_compat")
        show_key = b in ("openai_compat", "gemini_api")
        show_model = b != "google_free"

        self.lbl_url_row.setVisible(show_url)
        self.url_widget.setVisible(show_url)
        self.lbl_api_row.setVisible(show_key)
        self.api_widget.setVisible(show_key)
        self.lbl_model_row.setVisible(show_model)
        self.model_widget.setVisible(show_model)
        self.btn_refresh_models.setVisible(b in ("local_ollama", "openai_compat", "gemini_api"))

        self.model_combo.clear()

        if b == "google_free":
            self.lbl_backend_hint.setText(
                "✓ Dùng ngay không cần API Key, tốc độ ~0.2 giây (kết hợp Windows OCR). "
                "Phù hợp chat nhanh & thử nghiệm; để dịch Game/Phim có nhớ ngữ cảnh, hãy chọn Local AI hoặc Groq."
            )
            self.lbl_backend_hint.setStyleSheet("color: #34d399; font-size: 11px;")

        elif b == "local_ollama":
            self.url_edit.setText(self._draft_local_url or "http://127.0.0.1:11434/v1")
            self.btn_preset_1.setText("Ollama")
            self.btn_preset_2.setText("LM Studio")
            self.model_combo.addItems(
                ["qwen2.5:3b", "qwen2.5:7b", "qwen3:8b", "gemma3:4b", "gemma3:12b"]
            )
            self.model_combo.setCurrentText(self._draft_local_model or "qwen2.5:3b")
            self.lbl_backend_hint.setText(
                "🏠 Chạy 100% trên GPU máy bạn (~0.3–0.7s, 0đ, 0 lỗi 503, nhớ ngữ cảnh cực tốt). "
                "Cài Ollama tại ollama.com rồi chạy: ollama pull qwen2.5:3b (nhanh nhất) hoặc qwen2.5:7b."
            )
            self.lbl_backend_hint.setStyleSheet("color: #38bdf8; font-size: 11px;")

        elif b == "openai_compat":
            self.url_edit.setText(self._draft_openai_url or "https://api.groq.com/openai/v1")
            self.api_key_edit.setText(self._draft_openai_key)
            self.api_key_edit.setPlaceholderText("Dán Groq / OpenRouter / DeepSeek API Key...")
            self.btn_preset_1.setText("Groq (Miễn phí)")
            self.btn_preset_2.setText("OpenRouter")
            self.model_combo.addItems(
                [
                    "llama-3.3-70b-versatile",
                    "qwen/qwen3-32b",
                    "llama-3.1-8b-instant",
                ]
            )
            self.model_combo.setCurrentText(
                self._draft_openai_model or "llama-3.3-70b-versatile"
            )
            self.lbl_backend_hint.setText(
                "⚡ Groq có gói miễn phí cực nhanh (~0.2 giây/câu, nhớ ngữ cảnh tốt, rất ít lỗi 503). "
                "Bấm '🔑 Lấy API Key' để mở console.groq.com."
            )
            self.lbl_backend_hint.setStyleSheet("color: #a78bfa; font-size: 11px;")

        elif b == "gemini_api":
            self.api_key_edit.setText(self._draft_gemini_key)
            self.api_key_edit.setPlaceholderText("Dán API Key từ aistudio.google.com...")
            self.model_combo.addItems(
                [
                    "gemini-3.8-flash",
                    "gemini-3.8-flash-lite",
                    "gemini-3.8-pro",
                    "gemini-flash-latest",
                ]
            )
            self.model_combo.setCurrentText(self._draft_gemini_model or "gemini-3.8-flash")
            self.lbl_backend_hint.setText(
                "✨ Tự tắt Thinking để tăng tốc và tự chuyển model dự phòng nếu gặp lỗi 503."
            )
            self.lbl_backend_hint.setStyleSheet("color: #94a3b8; font-size: 11px;")

        elif b == "gemini_cli":
            self.model_combo.addItems(["gemini-3.8-flash", "gemini-3.8-pro"])
            self.model_combo.setCurrentText(self._draft_gemini_model or "gemini-3.8-flash")
            if shutil.which("gemini"):
                self.lbl_backend_hint.setText("✓ Đã cài Gemini CLI trên máy (sẵn sàng dùng).")
                self.lbl_backend_hint.setStyleSheet("color: #34d399; font-size: 11px;")
            else:
                self.lbl_backend_hint.setText(
                    "⚠ Chưa cài Gemini CLI (cài bằng: npm install -g @google/gemini-cli)."
                )
                self.lbl_backend_hint.setStyleSheet("color: #fbbf24; font-size: 11px;")

    def _on_preset_1(self) -> None:
        if self._active_backend == "local_ollama":
            self.url_edit.setText("http://127.0.0.1:11434/v1")
            self.model_combo.setCurrentText("qwen2.5:3b")
        elif self._active_backend == "openai_compat":
            self.url_edit.setText("https://api.groq.com/openai/v1")
            self.model_combo.setCurrentText("llama-3.3-70b-versatile")

    def _on_preset_2(self) -> None:
        if self._active_backend == "local_ollama":
            self.url_edit.setText("http://127.0.0.1:1234/v1")
        elif self._active_backend == "openai_compat":
            self.url_edit.setText("https://openrouter.ai/api/v1")
            self.model_combo.setCurrentText("google/gemini-2.5-flash")

    def _open_api_key_page(self) -> None:
        if self._active_backend == "openai_compat":
            if "openrouter" in self.url_edit.text().lower():
                webbrowser.open("https://openrouter.ai/keys")
            else:
                webbrowser.open("https://console.groq.com/keys")
        else:
            webbrowser.open("https://aistudio.google.com/apikey")

    def _refresh_models(self) -> None:
        b = self._active_backend
        self.btn_refresh_models.setEnabled(False)
        self.btn_refresh_models.setText("Đang tải...")
        try:
            translator = GeminiTranslator(self._config)
            models = translator.list_available_models(
                backend=b,
                api_key=self.api_key_edit.text().strip(),
                base_url=self.url_edit.text().strip(),
            )
            if models:
                current = self.model_combo.currentText().strip()
                self.model_combo.clear()
                self.model_combo.addItems(models)
                if current in models:
                    self.model_combo.setCurrentText(current)
                else:
                    self.model_combo.setCurrentIndex(0)
                QMessageBox.information(
                    self,
                    "Đã cập nhật model",
                    f"Đã tải {len(models)} model khả dụng.",
                )
            else:
                QMessageBox.information(self, "Thông báo", "Không tìm thấy model nào.")
        except Exception as exc:
            QMessageBox.warning(self, "Lỗi tải model", str(exc))
        finally:
            self.btn_refresh_models.setEnabled(True)
            self.btn_refresh_models.setText("🔄 Tải model")

    def apply_to_config(self) -> None:
        self._stash_current_backend_fields()
        self._config.backend = self._active_backend
        self._config.local_base_url = self._draft_local_url or "http://localhost:11434/v1"
        self._config.local_model = self._draft_local_model or "qwen2.5:7b"
        self._config.openai_base_url = self._draft_openai_url or "https://api.groq.com/openai/v1"
        self._config.openai_api_key = self._draft_openai_key
        self._config.openai_model = self._draft_openai_model or "llama-3.3-70b-versatile"
        self._config.api_key = self._draft_gemini_key
        self._config.model = self._draft_gemini_model or "gemini-3.8-flash"

        self._config.use_local_ocr = self.use_ocr_cb.isChecked()
        self._config.ocr_language = str(self.ocr_lang_combo.currentData() or "")
        self._config.target_language_read = self.read_lang_edit.text().strip() or "Tiếng Việt"
        self._config.target_language_write = self.write_lang_edit.text().strip() or "Tiếng Anh"
        self._config.auto_interval_sec = float(self.interval_spin.value())
        self._config.context_memory_size = int(self.memory_spin.value())
        self._config.subtitle_font_size = int(self.sub_font_spin.value())
        self._config.story_glossary = self.glossary_edit.text().strip()
        self._config.show_border = self.show_border_cb.isChecked()
        self._config.restore_clipboard = self.restore_clip_cb.isChecked()
        self._config.save()


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.config = AppConfig.load()
        self.translator = GeminiTranslator(self.config)

        self._last_captured_img: Optional[Image.Image] = None
        self._last_ocr_norm: str = ""
        self._last_translation: str = ""
        self._story_history: list[str] = []
        self._img_worker: Optional[TranslateRegionWorker] = None
        self._reply_worker: Optional[TranslateReplyWorker] = None
        self._selector_overlay: Optional[RegionSelectorOverlay] = None
        self._picker_overlay: Optional[PointPickerOverlay] = None

        self._border_overlay = RegionBorderOverlay()
        self._subtitle_overlay = SubtitleOverlay(font_size=self.config.subtitle_font_size)
        if len(self.config.subtitle_geometry) == 4:
            sx, sy, sw, sh = self.config.subtitle_geometry
            self._subtitle_overlay.setGeometry(sx, sy, max(360, sw), max(110, sh))

        self._hotkeys = GlobalHotkeyManager()

        self.setWindowTitle("QuickTranslate")
        self.resize(470, 580)
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

        top_row = QHBoxLayout()
        self.btn_select_region = QPushButton("📐 Chọn khung")
        self.btn_select_region.setToolTip("Chọn & khóa vùng khung chat / phụ đề (Ctrl+Shift+S)")

        self.btn_pick_input = QPushButton("🎯 Ghim ô chat")
        self.btn_pick_input.setToolTip("Click vào ô nhập tin nhắn để đặt con trỏ điền nhanh (Ctrl+Shift+T)")

        self.btn_translate = QPushButton("⚡ Dịch ngay")
        self.btn_translate.setObjectName("primaryBtn")
        self.btn_translate.setToolTip("Chụp khung đã khóa và dịch sang Tiếng Việt (Ctrl+Shift+D)")

        self.btn_game_mode = QPushButton("🎮 Game/Phim")
        self.btn_game_mode.setToolTip(
            "Chuyển sang khung phụ đề nổi (chỉ hiện phần dịch, nhớ ngữ cảnh) — Ctrl+Shift+M"
        )

        self.btn_settings = QPushButton("⚙")
        self.btn_settings.setFixedWidth(36)
        self.btn_settings.setToolTip("Cài đặt Backend (Local AI / Groq / Google Free / Gemini), OCR...")

        top_row.addWidget(self.btn_select_region)
        top_row.addWidget(self.btn_pick_input)
        top_row.addWidget(self.btn_translate)
        top_row.addWidget(self.btn_game_mode)
        top_row.addWidget(self.btn_settings)
        main_layout.addLayout(top_row)

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

        self.lbl_info = QLabel()
        self.lbl_info.setStyleSheet("color: #94a3b8; font-size: 11px;")
        main_layout.addWidget(self.lbl_info)

        read_header = QHBoxLayout()
        lbl_read = QLabel("Bản dịch khung (Tiếng Việt):")
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
            "1. Bấm 'Chọn khung' để khóa vùng chat hoặc vùng phụ đề game/phim.\n"
            "2. Bấm 'Ghim ô chat' để điền nhanh, hoặc bấm '🎮 Game/Phim' để chỉ hiện phụ đề nổi.\n"
            "3. Bấm '⚙' để chọn Local AI (Ollama), Groq siêu nhanh, Google Free (0 Key) hoặc Gemini."
        )
        self.translation_view.setFont(QFont("Segoe UI", 10))
        main_layout.addWidget(self.translation_view, stretch=3)

        write_header = QHBoxLayout()
        lbl_write = QLabel("Trả lời nhanh (Tiếng Việt → Tiếng Anh):")
        lbl_write.setStyleSheet("font-weight: 600; color: #34d399;")
        self.cb_auto_enter = QCheckBox("Tự gửi (Enter)")
        self.cb_auto_enter.setChecked(self.config.auto_press_enter)
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
        self.btn_game_mode.clicked.connect(lambda: self.set_game_movie_mode(True))
        self.btn_settings.clicked.connect(self.open_settings)
        self.btn_send.clicked.connect(self.trigger_translate_and_fill)
        self.reply_input.submit_requested.connect(self.trigger_translate_and_fill)

        self.cb_auto.toggled.connect(self._on_auto_toggled)
        self.cb_on_top.toggled.connect(self._on_top_toggled)
        self.cb_border.toggled.connect(self._on_border_toggled)
        self.cb_auto_enter.toggled.connect(self._on_auto_enter_toggled)

        self._subtitle_overlay.select_region_clicked.connect(self.start_region_selection)
        self._subtitle_overlay.translate_now_clicked.connect(
            lambda: self.trigger_translate_region(force=True)
        )
        self._subtitle_overlay.toggle_auto_clicked.connect(
            lambda: self.cb_auto.setChecked(not self.cb_auto.isChecked())
        )
        self._subtitle_overlay.clear_context_clicked.connect(self.clear_story_context)
        self._subtitle_overlay.toggle_lock_clicked.connect(self.toggle_subtitle_lock)
        self._subtitle_overlay.exit_subtitle_mode_clicked.connect(
            lambda: self.set_game_movie_mode(False)
        )
        self._subtitle_overlay.quit_app_clicked.connect(self.close)

        self._hotkeys.select_region_triggered.connect(self.start_region_selection)
        self._hotkeys.pick_input_triggered.connect(self.start_point_picking)
        self._hotkeys.translate_now_triggered.connect(
            lambda: self.trigger_translate_region(force=True)
        )
        self._hotkeys.toggle_subtitle_mode_triggered.connect(self.toggle_game_movie_mode)
        self._hotkeys.toggle_subtitle_lock_triggered.connect(self.toggle_subtitle_lock)

    def set_game_movie_mode(self, enabled: bool) -> None:
        self.config.mode = "game_movie" if enabled else "chat"
        self.config.save()

        if enabled:
            self.hide()
            self._subtitle_overlay.set_font_size(self.config.subtitle_font_size)
            if self._last_translation:
                self._subtitle_overlay.set_subtitle_text(self._last_translation)
            self._subtitle_overlay.set_status(
                "Sẵn sàng", len(self._story_history), self.config.auto_translate
            )
            self._subtitle_overlay.show()
            self._subtitle_overlay.raise_()
        else:
            if self._subtitle_overlay.is_click_through():
                self._subtitle_overlay.set_click_through(False)
            g = self._subtitle_overlay.geometry()
            self.config.subtitle_geometry = [g.x(), g.y(), g.width(), g.height()]
            self.config.save()
            self._subtitle_overlay.hide()
            self.show()
            self.raise_()
            self.activateWindow()

    def toggle_game_movie_mode(self) -> None:
        self.set_game_movie_mode(self.config.mode != "game_movie")

    def toggle_subtitle_lock(self) -> None:
        if self.config.mode != "game_movie":
            return
        self._subtitle_overlay.set_click_through(not self._subtitle_overlay.is_click_through())

    def clear_story_context(self) -> None:
        self._story_history.clear()
        self._subtitle_overlay.set_status("Đã xóa ngữ cảnh", 0, self.config.auto_translate)
        self.lbl_status.setText("Đã xóa bộ nhớ ngữ cảnh Game/Phim")

    def _update_status_badges(self) -> None:
        r = self.config.chat_region
        p = self.config.input_point
        region_txt = f"Khung: {r.width}×{r.height}" if r else "Khung: Chưa chọn"
        point_txt = f"Ô chat: ({p.x},{p.y})" if p else "Ô chat: Chưa ghim"
        ocr_txt = "OCR" if self.config.use_local_ocr else "Vision"
        self.lbl_info.setText(
            f"{region_txt}  |  {point_txt}  |  {self.config.active_model_label()} ({ocr_txt})"
        )

    def _sync_watch_timer(self) -> None:
        if self.config.auto_translate and self.config.chat_region is not None:
            ms = max(500, int(self.config.auto_interval_sec * 1000))
            self._watch_timer.start(ms)
        else:
            self._watch_timer.stop()

    def _on_auto_toggled(self, checked: bool) -> None:
        self.config.auto_translate = checked
        self.config.save()
        self._sync_watch_timer()
        status = "Đang theo dõi..." if checked else "Đã tắt tự động"
        self.lbl_status.setText(status)
        self._subtitle_overlay.set_status(status, len(self._story_history), checked)
        if checked:
            self.trigger_translate_region(force=False)

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
        self._last_ocr_norm = ""
        self._border_overlay.set_region(region, self.config.show_border)
        self._update_status_badges()
        self._sync_watch_timer()
        self.lbl_status.setText("Đã khóa khung — đang dịch...")
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
            self._subtitle_overlay.set_font_size(self.config.subtitle_font_size)
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
                if self.config.mode == "game_movie":
                    self._subtitle_overlay.set_subtitle_text(
                        "Chưa chọn vùng phụ đề! Nhấn Ctrl+Shift+S hoặc nút 📐 Khung để chọn."
                    )
                else:
                    QMessageBox.information(
                        self,
                        "Chưa chọn khung",
                        "Hãy bấm 'Chọn khung' (hoặc Ctrl+Shift+S) để khóa vùng cần dịch trên màn hình trước.",
                    )
            return

        if self._img_worker is not None and self._img_worker.isRunning():
            return

        try:
            img = capture_region(region)
        except Exception as exc:
            self.lbl_status.setText(f"Lỗi chụp màn hình: {exc}")
            return

        use_ocr = self.config.use_local_ocr or self.config.backend == "google_free"
        if not force and not use_ocr:
            diff = compute_diff_percent(self._last_captured_img, img)
            if diff < self.config.diff_threshold:
                return

        self._last_captured_img = img
        if force:
            self.lbl_status.setText("Đang dịch...")
            self._subtitle_overlay.set_status(
                "Đang dịch...", len(self._story_history), self.config.auto_translate
            )
            self.btn_translate.setEnabled(False)
            self._border_overlay.set_active_translating(True)

        self._img_worker = TranslateRegionWorker(
            self.translator,
            img=img,
            use_local_ocr=use_ocr,
            ocr_language=self.config.ocr_language,
            last_ocr_norm=self._last_ocr_norm,
            force=force,
            mode=self.config.mode,
            history=self._story_history,
        )
        self._img_worker.finished_ok.connect(self._on_image_translated)
        self._img_worker.skipped_unchanged.connect(self._on_region_unchanged)
        self._img_worker.failed.connect(self._on_image_translate_failed)
        self._img_worker.start()

    def _on_region_unchanged(self) -> None:
        self.btn_translate.setEnabled(True)
        self._border_overlay.set_active_translating(False)

    def _on_image_translated(
        self, text: str, elapsed: float, mode: str, raw_ocr: str
    ) -> None:
        if raw_ocr:
            self._last_ocr_norm = normalize_ocr_text(raw_ocr)
        self._last_translation = text
        self.translation_view.setPlainText(text)
        self.lbl_status.setText(f"Đã dịch ({elapsed:.2f}s)")
        self.btn_translate.setEnabled(True)
        self._border_overlay.set_active_translating(False)

        if mode == "game_movie":
            cleaned = text.strip()
            ignore_markers = ("(Không có lời thoại)", "(Không phát hiện nội dung văn bản)")
            if (
                cleaned
                and cleaned not in ignore_markers
                and (not self._story_history or self._story_history[-1] != cleaned)
            ):
                self._story_history.append(cleaned)
                max_keep = max(1, int(self.config.context_memory_size))
                if len(self._story_history) > max_keep:
                    self._story_history = self._story_history[-max_keep:]

            self._subtitle_overlay.set_subtitle_text(text)
            self._subtitle_overlay.set_status(
                f"Đã dịch ({elapsed:.2f}s)",
                len(self._story_history),
                self.config.auto_translate,
            )

    def _on_image_translate_failed(self, err: str) -> None:
        self.lbl_status.setText("Lỗi dịch khung")
        self.translation_view.setPlainText(f"[Lỗi] {err}")
        self._subtitle_overlay.set_subtitle_text(f"[Lỗi] {err}")
        self._subtitle_overlay.set_status(
            "Lỗi dịch", len(self._story_history), self.config.auto_translate
        )
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
                self.lbl_last_sent.setText(f"Đã điền ({elapsed:.2f}s): {translated}")
            else:
                self.lbl_last_sent.setText(
                    f"Đã dán (chưa ghim ô chat, {elapsed:.2f}s): {translated}"
                )
        except Exception as exc:
            self.lbl_last_sent.setText(f"Đã dịch nhưng lỗi điền: {exc}")

    def _on_reply_failed(self, err: str) -> None:
        self.btn_send.setEnabled(True)
        self.reply_input.setEnabled(True)
        self.lbl_last_sent.setText(f"Lỗi: {err}")

    def closeEvent(self, event) -> None:  # noqa: N802
        try:
            g = self.geometry()
            self.config.window_geometry = [g.x(), g.y(), g.width(), g.height()]
            sg = self._subtitle_overlay.geometry()
            self.config.subtitle_geometry = [sg.x(), sg.y(), sg.width(), sg.height()]
            self.config.save()
        except Exception:
            pass

        self._watch_timer.stop()
        try:
            self.translator._http.close()
        except Exception:
            pass

        for ov in (
            self._border_overlay,
            self._subtitle_overlay,
            self._selector_overlay,
            self._picker_overlay,
        ):
            if ov is not None:
                try:
                    ov.hide()
                    ov.close()
                except Exception:
                    pass

        try:
            self._hotkeys.stop()
        except Exception:
            pass

        event.accept()
        super().closeEvent(event)
        app = QApplication.instance()
        if app is not None:
            app.quit()
