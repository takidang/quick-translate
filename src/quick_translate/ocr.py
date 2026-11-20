"""Đọc chữ cục bộ bằng Windows OCR tích hợp sẵn (WinRT) — ~0.1s, 100% offline."""

from __future__ import annotations

import asyncio
from typing import Optional

from PIL import Image


def list_ocr_languages() -> list[str]:
    """Liệt kê các gói ngôn ngữ OCR đang có sẵn trên Windows."""
    try:
        from winrt.windows.media.ocr import OcrEngine

        return [lang.language_tag for lang in OcrEngine.available_recognizer_languages]
    except Exception:
        return []


def _create_engine(lang_tag: str = ""):
    from winrt.windows.globalization import Language
    from winrt.windows.media.ocr import OcrEngine

    if lang_tag.strip():
        try:
            eng = OcrEngine.try_create_from_language(Language(lang_tag.strip()))
            if eng is not None:
                return eng
        except Exception:
            pass

    eng = OcrEngine.try_create_from_user_profile_languages()
    if eng is not None:
        return eng

    avail = list(OcrEngine.available_recognizer_languages)
    if avail:
        return OcrEngine.try_create_from_language(avail[0])
    return None


def extract_text_from_image(img: Image.Image, lang_tag: str = "") -> str:
    """
    Nhận diện chữ từ ảnh PIL bằng Windows OCR.
    Tự phóng to 2x với vùng chữ nhỏ để đọc phụ đề game/chat sắc nét hơn.
    """
    from winrt.windows.graphics.imaging import (
        BitmapAlphaMode,
        BitmapPixelFormat,
        SoftwareBitmap,
    )
    from winrt.windows.storage.streams import DataWriter

    engine = _create_engine(lang_tag)
    if engine is None:
        raise RuntimeError(
            "Không khởi tạo được Windows OCR. Hãy kiểm tra gói ngôn ngữ trong Windows Settings."
        )

    work_img = img.convert("RGBA")
    # Phóng to vùng nhỏ để chữ phụ đề/chat sắc nét hơn với Windows OCR
    if work_img.width < 600 or work_img.height < 180:
        work_img = work_img.resize(
            (work_img.width * 2, work_img.height * 2),
            Image.Resampling.LANCZOS,
        )

    bgra_bytes = work_img.tobytes("raw", "BGRA")
    writer = DataWriter()
    writer.write_bytes(bgra_bytes)
    ibuffer = writer.detach_buffer()

    bitmap = SoftwareBitmap.create_copy_from_buffer(
        ibuffer,
        BitmapPixelFormat.BGRA8,
        work_img.width,
        work_img.height,
        BitmapAlphaMode.PREMULTIPLIED,
    )

    result = asyncio.run(engine.recognize_async(bitmap))
    lines = [line.text.strip() for line in result.lines if line.text and line.text.strip()]
    return "\n".join(lines).strip()


def normalize_ocr_text(text: Optional[str]) -> str:
    """Chuẩn hóa text OCR để so sánh trùng lặp ổn định."""
    if not text:
        return ""
    return " ".join(text.lower().split())
