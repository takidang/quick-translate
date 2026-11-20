"""Chụp vùng màn hình và phát hiện thay đổi nội dung để tiết kiệm token."""

from __future__ import annotations

import io
from typing import Optional

import mss
from PIL import Image, ImageChops, ImageStat

from .config import RectRegion


def capture_region(region: RectRegion) -> Image.Image:
    """Chụp vùng màn hình theo tọa độ vật lý (physical pixels)."""
    monitor = {
        "left": int(region.x),
        "top": int(region.y),
        "width": int(region.width),
        "height": int(region.height),
    }
    with mss.mss() as sct:
        shot = sct.grab(monitor)
        return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")


def image_to_png_bytes(img: Image.Image, max_width: int = 1280) -> bytes:
    """Nén ảnh hợp lý trước khi gửi Gemini để tối ưu tốc độ và token."""
    out_img = img
    if img.width > max_width:
        ratio = max_width / float(img.width)
        new_size = (max_width, max(1, int(img.height * ratio)))
        out_img = img.resize(new_size, Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    out_img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def compute_diff_percent(img_a: Optional[Image.Image], img_b: Image.Image) -> float:
    """Tính % khác biệt trung bình (0..100) giữa 2 ảnh ở kích thước thu nhỏ."""
    if img_a is None:
        return 100.0
    thumb_size = (160, 160)
    a = img_a.convert("L").resize(thumb_size, Image.Resampling.BILINEAR)
    b = img_b.convert("L").resize(thumb_size, Image.Resampling.BILINEAR)
    diff = ImageChops.difference(a, b)
    stat = ImageStat.Stat(diff)
    mean_diff = stat.mean[0]  # 0..255
    return (mean_diff / 255.0) * 100.0
