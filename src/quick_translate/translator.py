"""Backend dịch thuật dùng Gemini API (google-genai) hoặc Gemini CLI."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from google import genai
from google.genai import types

from .config import AppConfig


class TranslationError(RuntimeError):
    """Lỗi khi gọi dịch thuật Gemini."""


class GeminiTranslator:
    """Hỗ trợ dịch ảnh khung chat (→ Tiếng Việt) và dịch câu trả lời (→ Tiếng Anh)."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self._client: Optional[genai.Client] = None
        self._client_key: str = ""
        # Cache chế độ tắt thinking tối ưu cho từng model ("minimal" | "budget0" | "none")
        self._thinking_mode_cache: dict[str, str] = {}

    def _get_api_client(self) -> genai.Client:
        api_key = self.config.api_key.strip()
        if not api_key:
            raise TranslationError(
                "Chưa có Gemini API Key. Mở Cài đặt (⚙) để nhập API key từ aistudio.google.com "
                "hoặc chuyển sang backend Gemini CLI."
            )
        if self._client is None or self._client_key != api_key:
            self._client = genai.Client(
                api_key=api_key,
                http_options=types.HttpOptions(timeout=20_000),
            )
            self._client_key = api_key
        return self._client

    def translate_chat_image(self, png_bytes: bytes) -> str:
        """Dịch toàn bộ nội dung đoạn chat trong ảnh sang ngôn ngữ đọc (mặc định Tiếng Việt)."""
        target_lang = self.config.target_language_read or "Tiếng Việt"
        prompt = (
            f"Bạn là trợ lý dịch hội thoại cực kỳ chính xác và tự nhiên.\n"
            f"Hãy đọc toàn bộ tin nhắn / văn bản hiển thị trong ảnh chụp khung chat này "
            f"và dịch sang {target_lang}.\n"
            f"Quy tắc:\n"
            f"- Giữ nguyên tên người gửi (nếu thấy) và thứ tự tin nhắn từ trên xuống dưới.\n"
            f"- Dịch tự nhiên theo ngữ cảnh chat đời thường/công việc, không giải thích dài dòng.\n"
            f"- Bỏ qua các nút giao diện thừa (như biểu tượng, thanh cuộn, khung nhập trống).\n"
            f"- Nếu trong ảnh không có chữ nào để dịch, trả về đúng dòng: (Không phát hiện nội dung văn bản)"
        )

        if self.config.backend == "gemini_cli":
            return self._call_gemini_cli(prompt, png_bytes=png_bytes)
        return self._call_gemini_api(prompt, image_bytes=png_bytes, mime_type="image/jpeg")

    def translate_game_movie_image(
        self,
        png_bytes: bytes,
        history: Optional[list[str]] = None,
    ) -> str:
        """Dịch phụ đề/hội thoại game hoặc phim sang ngôn ngữ đọc, giữ ngữ cảnh xuyên suốt."""
        target_lang = self.config.target_language_read or "Tiếng Việt"

        parts: list[str] = [
            f"Bạn là biên dịch viên phụ đề game & phim chuyên nghiệp, dịch tự nhiên sang {target_lang}."
        ]

        glossary = (self.config.story_glossary or "").strip()
        if glossary:
            parts.append(f"Ghi chú ngữ cảnh / nhân vật / xưng hô:\n{glossary}")

        if history:
            recent = history[-max(1, int(self.config.context_memory_size)) :]
            joined = "\n".join(f"- {line}" for line in recent)
            parts.append(
                "Các câu thoại đã dịch ngay trước đó (hãy giữ đồng nhất xưng hô, tên riêng và mạch truyện):\n"
                f"{joined}"
            )

        parts.append(
            "Yêu cầu:\n"
            f"- Đọc toàn bộ lời thoại / phụ đề trong ảnh và dịch mượt mà sang {target_lang}.\n"
            "- Nếu có tên nhân vật nói, giữ gọn dạng `Tên: lời thoại`.\n"
            "- Chỉ trả về DUY NHẤT nội dung phụ đề đã dịch, không giải thích, không thêm ghi chú thừa.\n"
            "- Bỏ qua HUD/nút bấm/UI không phải lời thoại.\n"
            "- Nếu ảnh không có chữ/phụ đề nào, trả về đúng: (Không có lời thoại)"
        )

        prompt = "\n\n".join(parts)
        if self.config.backend == "gemini_cli":
            return self._call_gemini_cli(prompt, png_bytes=png_bytes)
        return self._call_gemini_api(prompt, image_bytes=png_bytes, mime_type="image/jpeg")

    def translate_reply(self, user_text: str, chat_context: str = "") -> str:
        """Dịch câu người dùng nhập sang ngôn ngữ gửi (mặc định Tiếng Anh) kèm ngữ cảnh chat."""
        target_lang = self.config.target_language_write or "Tiếng Anh"
        context_block = ""
        if chat_context.strip():
            trimmed = chat_context.strip()[-1500:]
            context_block = (
                f"Ngữ cảnh cuộc hội thoại gần đây (chỉ để tham khảo giọng điệu/ngữ cảnh):\n"
                f"---\n{trimmed}\n---\n\n"
            )

        prompt = (
            f"{context_block}"
            f"Hãy dịch câu trả lời sau sang {target_lang} sao cho tự nhiên, đúng ngữ cảnh chat.\n"
            f"QUAN TRỌNG: Chỉ trả về DUY NHẤT câu đã dịch, không thêm dấu ngoặc kép, không giải thích, không lời dẫn.\n\n"
            f"Nội dung cần dịch:\n{user_text.strip()}"
        )

        if self.config.backend == "gemini_cli":
            return self._call_gemini_cli(prompt)
        return self._call_gemini_api(prompt)

    def _build_fast_config(self, mode: str) -> types.GenerateContentConfig:
        if mode == "minimal":
            return types.GenerateContentConfig(
                temperature=0.2,
                thinking_config=types.ThinkingConfig(
                    thinking_level=types.ThinkingLevel.MINIMAL
                ),
            )
        if mode == "budget0":
            return types.GenerateContentConfig(
                temperature=0.2,
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            )
        return types.GenerateContentConfig(temperature=0.2)

    def _call_gemini_api(
        self,
        prompt: str,
        image_bytes: Optional[bytes] = None,
        mime_type: str = "image/jpeg",
    ) -> str:
        client = self._get_api_client()
        model_name = self.config.model or "gemini-3.8-flash"
        contents: list[object] = [prompt]
        if image_bytes is not None:
            contents.append(
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
            )

        cached = self._thinking_mode_cache.get(model_name)
        if cached is not None:
            modes_to_try = [cached]
        elif "gemini-3" in model_name.lower():
            modes_to_try = ["minimal", "budget0", "none"]
        else:
            modes_to_try = ["budget0", "minimal", "none"]

        response = None
        last_exc: Optional[Exception] = None
        for mode in modes_to_try:
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config=self._build_fast_config(mode),
                )
                self._thinking_mode_cache[model_name] = mode
                break
            except Exception as exc:
                last_exc = exc
                err_str = str(exc).lower()
                # Chỉ thử chế độ thinking khác nếu lỗi do tham số thinking không hợp lệ
                if "thinking" in err_str or "invalid_argument" in err_str or "400" in err_str:
                    continue
                raise TranslationError(f"Lỗi Gemini API: {exc}") from exc

        if response is None:
            raise TranslationError(f"Lỗi Gemini API: {last_exc}") from last_exc

        text = (response.text or "").strip()
        if not text:
            raise TranslationError("Gemini API không trả về nội dung.")
        return text

    def list_available_models(self, api_key: Optional[str] = None) -> list[str]:
        """Lấy danh sách model Gemini khả dụng trực tiếp từ tài khoản API Key."""
        key = (api_key if api_key is not None else self.config.api_key).strip()
        if not key:
            raise TranslationError("Hãy nhập Gemini API Key trước khi tải danh sách model.")
        client = genai.Client(api_key=key)
        models: list[str] = []
        try:
            for m in client.models.list():
                name = getattr(m, "name", "") or ""
                if name.startswith("models/"):
                    name = name[len("models/") :]
                if "gemini" in name.lower() and "embedding" not in name.lower():
                    models.append(name)
        except Exception as exc:
            raise TranslationError(f"Không tải được danh sách model: {exc}") from exc
        return sorted(set(models), reverse=True)

    def _call_gemini_cli(self, prompt: str, png_bytes: Optional[bytes] = None) -> str:
        gemini_exe = shutil.which("gemini")
        if not gemini_exe:
            raise TranslationError(
                "Không tìm thấy lệnh `gemini` trên máy. Hãy cài Gemini CLI "
                "(`npm install -g @google/gemini-cli`) rồi đăng nhập bằng tài khoản Google AI Pro, "
                "hoặc chuyển sang dùng Gemini API Key."
            )

        tmp_path: Optional[Path] = None
        try:
            full_prompt = prompt
            if png_bytes is not None:
                with tempfile.NamedTemporaryFile(
                    suffix=".jpg", delete=False
                ) as tmp:
                    tmp.write(png_bytes)
                    tmp_path = Path(tmp.name)
                full_prompt = f"@{tmp_path}\n{prompt}"

            cmd = [gemini_exe, "-p", full_prompt]
            if self.config.model:
                cmd.extend(["-m", self.config.model])

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if result.returncode != 0:
                err = (result.stderr or result.stdout or "").strip()
                raise TranslationError(f"Gemini CLI lỗi (mã {result.returncode}): {err}")
            output = result.stdout.strip()
            if not output:
                raise TranslationError("Gemini CLI không trả về kết quả.")
            return output
        except subprocess.TimeoutExpired as exc:
            raise TranslationError("Gemini CLI phản hồi quá lâu (timeout 60s).") from exc
        finally:
            if tmp_path is not None and tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass
