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
    # "google_free" | "local_ollama" | "openai_compat" | "gemini_api" | "gemini_cli"
    backend: str = "google_free"

    # OCR cục bộ trên Windows (siêu nhanh, miễn phí, tránh dịch lại khi nền game/phim động)
    use_local_ocr: bool = True
    ocr_language: str = ""  # Trống = tự động theo Windows

    # Backend: Local AI (Ollama / LM Studio)
    local_base_url: str = "http://127.0.0.1:11434/v1"
    local_model: str = "qwen2.5:3b"

    # Backend: OpenAI-compatible (Groq / OpenRouter / DeepSeek / OpenAI)
    openai_base_url: str = "https://api.groq.com/openai/v1"
    openai_api_key: str = ""
    openai_model: str = "llama-3.3-70b-versatile"

    # Backend: Gemini API / CLI
    api_key: str = ""
    model: str = "gemini-3.8-flash"

    auto_translate: bool = False
    auto_interval_sec: float = 1.5
    diff_threshold: float = 2.5  # % thay đổi điểm ảnh tối thiểu (khi tắt OCR)
    show_border: bool = True
    always_on_top: bool = True
    auto_press_enter: bool = False
    restore_clipboard: bool = True
    target_language_read: str = "Tiếng Việt"
    target_language_write: str = "Tiếng Anh"
    mode: str = "chat"  # "chat" | "game_movie"
    context_memory_size: int = 10
    story_glossary: str = ""
    subtitle_font_size: int = 15
    subtitle_geometry: list[int] = field(default_factory=list)
    chat_region: Optional[RectRegion] = None
    input_point: Optional[TargetPoint] = None
    window_geometry: list[int] = field(default_factory=list)

    def active_model_label(self) -> str:
        if self.backend == "google_free":
            return "Google Free (0 Key)"
        if self.backend == "local_ollama":
            return f"Local: {self.local_model}"
        if self.backend == "openai_compat":
            return f"Cloud: {self.openai_model}"
        if self.backend == "gemini_cli":
            return f"Gemini CLI: {self.model}"
        return f"Gemini API: {self.model}"

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

        if cfg.model == "gemini-2.5-flash":
            cfg.model = "gemini-3.8-flash"
        return cfg

    def save(self, path: Optional[Path] = None) -> None:
        cfg_path = path or _default_config_path()
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        data = asdict(self)
        cfg_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
