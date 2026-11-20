"""Kiểm thử nhanh các module lõi của QuickTranslate."""

from __future__ import annotations

import os
from pathlib import Path

from PIL import Image

from quick_translate.capture import compute_diff_percent, image_to_png_bytes
from quick_translate.config import AppConfig, RectRegion, TargetPoint


def test_config_roundtrip(tmp_path: Path) -> None:
    cfg_file = tmp_path / "config.json"
    cfg = AppConfig(
        backend="gemini_api",
        api_key="test-key-123",
        model="gemini-2.5-flash-lite",
        auto_translate=True,
        mode="game_movie",
        context_memory_size=12,
        story_glossary="Nhân vật chính tên Cloud",
        subtitle_font_size=18,
        chat_region=RectRegion(100, 200, 500, 400),
        input_point=TargetPoint(350, 620),
    )
    cfg.save(cfg_file)

    loaded = AppConfig.load(cfg_file)
    assert loaded.backend == "gemini_api"
    assert loaded.api_key == "test-key-123"
    assert loaded.model == "gemini-2.5-flash-lite"
    assert loaded.auto_translate is True
    assert loaded.mode == "game_movie"
    assert loaded.context_memory_size == 12
    assert loaded.story_glossary == "Nhân vật chính tên Cloud"
    assert loaded.subtitle_font_size == 18
    assert loaded.chat_region == RectRegion(100, 200, 500, 400)
    assert loaded.input_point == TargetPoint(350, 620)


def test_image_diff_and_png_encoding() -> None:
    img1 = Image.new("RGB", (400, 300), color=(20, 20, 20))
    img2 = Image.new("RGB", (400, 300), color=(20, 20, 20))
    img3 = Image.new("RGB", (400, 300), color=(220, 220, 220))

    assert compute_diff_percent(img1, img2) == 0.0
    assert compute_diff_percent(img1, img3) > 50.0
    assert compute_diff_percent(None, img1) == 100.0

    large = Image.new("RGB", (2560, 1440), color=(10, 30, 50))
    png = image_to_png_bytes(large, max_width=1280)
    assert png.startswith(b"\x89PNG\r\n\x1a\n")


def test_qt_mainwindow_smoke(tmp_path: Path) -> None:
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    os.environ["QUICK_TRANSLATE_CONFIG"] = str(tmp_path / "qt_config.json")
    from PySide6.QtWidgets import QApplication

    from quick_translate.ui import MainWindow

    app = QApplication.instance() or QApplication([])
    win = MainWindow()
    assert "QuickTranslate" in win.windowTitle()
    win.set_game_movie_mode(True)
    assert win.config.mode == "game_movie"
    win.set_game_movie_mode(False)
    assert win.config.mode == "chat"
    win.close()
    app.processEvents()
