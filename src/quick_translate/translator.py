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

    def _get_api_client(self) -> genai.Client:
        api_key = self.config.api_key.strip()
        if not api_key:
            raise TranslationError(
                "Chưa có Gemini API Key. Mở Cài đặt (⚙) để nhập API key từ aistudio.google.com "
                "hoặc chuyển sang backend Gemini CLI."
            )
        if self._client is None or self._client_key != api_key:
            self._client = genai.Client(api_key=api_key)
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
        return self._call_gemini_api(prompt, png_bytes=png_bytes)

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

    def _call_gemini_api(self, prompt: str, png_bytes: Optional[bytes] = None) -> str:
        client = self._get_api_client()
        contents: list[object] = [prompt]
        if png_bytes is not None:
            contents.append(
                types.Part.from_bytes(data=png_bytes, mime_type="image/png")
            )

        try:
            response = client.models.generate_content(
                model=self.config.model or "gemini-2.5-flash",
                contents=contents,
            )
        except Exception as exc:
            raise TranslationError(f"Lỗi Gemini API: {exc}") from exc

        text = (response.text or "").strip()
        if not text:
            raise TranslationError("Gemini API không trả về nội dung.")
        return text

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
                    suffix=".png", delete=False
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
