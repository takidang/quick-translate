"""Quản lý cấu hình cục bộ cho QuickTranslate."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional


def _default_config_path() -> Path:
    env_path = os.environ.get("QUICK_TRANSLATE_CONFIG", "").strip()
    if env_path:
        p = Path(env_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        return p
    appdata = os.environ.get("APPDATA")
    candidates = [
        (Path(appdata) / "QuickTranslate") if appdata else (Path.home() / ".quick_translate"),
        Path.cwd() / ".quick_translate",
    ]
    for base in candidates:
        try:
            base.mkdir(parents=True, exist_ok=True)
            return base / "config.json"
        except OSError:
            continue
    return Path("config.json")


@dataclass
class RectRegion:
    """Tọa độ vật lý (physical pixels) của vùng khung chat trên màn hình."""

    x: int
    y: int
    width: int
    height: int

    def is_valid(self) -> bool:
        return self.width >= 20 and self.height >= 20


@dataclass
class TargetPoint:
    """Tọa độ vật lý (physical pixels) của ô nhập văn bản trong khung chat."""

    x: int
    y: int


@dataclass
class AppConfig:
    backend: str = "gemini_api"  # "gemini_api" | "gemini_cli"
    api_key: str = ""
    model: str = "gemini-2.5-flash"
    auto_translate: bool = False
    auto_interval_sec: float = 2.0
    diff_threshold: float = 2.5  # % thay đổi điểm ảnh tối thiểu để kích hoạt dịch
    show_border: bool = True
    always_on_top: bool = True
    auto_press_enter: bool = False
    restore_clipboard: bool = True
    target_language_read: str = "Tiếng Việt"
    target_language_write: str = "Tiếng Anh"
    chat_region: Optional[RectRegion] = None
    input_point: Optional[TargetPoint] = None
    window_geometry: list[int] = field(default_factory=list)

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "AppConfig":
        cfg_path = path or _default_config_path()
        if not cfg_path.exists():
            cfg = cls()
            env_key = os.environ.get("GEMINI_API_KEY", "").strip()
            if env_key:
                cfg.api_key = env_key
            return cfg
        try:
            raw = json.loads(cfg_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return cls()

        region_data = raw.pop("chat_region", None)
        point_data = raw.pop("input_point", None)

        valid_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in raw.items() if k in valid_fields}
        cfg = cls(**filtered)

        if isinstance(region_data, dict):
            try:
                cfg.chat_region = RectRegion(
                    x=int(region_data["x"]),
                    y=int(region_data["y"]),
                    width=int(region_data["width"]),
                    height=int(region_data["height"]),
                )
            except (KeyError, TypeError, ValueError):
                cfg.chat_region = None

        if isinstance(point_data, dict):
            try:
                cfg.input_point = TargetPoint(
                    x=int(point_data["x"]),
                    y=int(point_data["y"]),
                )
            except (KeyError, TypeError, ValueError):
                cfg.input_point = None

        if not cfg.api_key:
            env_key = os.environ.get("GEMINI_API_KEY", "").strip()
            if env_key:
                cfg.api_key = env_key
        return cfg

    def save(self, path: Optional[Path] = None) -> None:
        cfg_path = path or _default_config_path()
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        data = asdict(self)
        cfg_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
