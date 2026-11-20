"""Đa backend dịch thuật: Local AI (Ollama/LM Studio), Groq/OpenAI-compat, Google Free, Gemini API/CLI."""

from __future__ import annotations

import base64
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

import requests
from google import genai
from google.genai import types

from .config import AppConfig


class TranslationError(RuntimeError):
    """Lỗi khi gọi dịch thuật."""


_LANG_CODE_MAP: dict[str, str] = {
    "tiếng việt": "vi",
    "vietnamese": "vi",
    "vi": "vi",
    "tiếng anh": "en",
    "english": "en",
    "en": "en",
    "tiếng nhật": "ja",
    "japanese": "ja",
    "ja": "ja",
    "tiếng trung": "zh-CN",
    "chinese": "zh-CN",
    "zh": "zh-CN",
    "tiếng hàn": "ko",
    "korean": "ko",
    "ko": "ko",
    "tiếng pháp": "fr",
    "french": "fr",
    "tiếng đức": "de",
    "german": "de",
    "tiếng tây ban nha": "es",
    "spanish": "es",
    "tiếng nga": "ru",
    "russian": "ru",
    "tiếng thái": "th",
    "thai": "th",
}


def _to_lang_code(lang_name: str, default: str = "vi") -> str:
    key = (lang_name or "").strip().lower()
    if key in _LANG_CODE_MAP:
        return _LANG_CODE_MAP[key]
    if 2 <= len(key) <= 5 and key.replace("-", "").isalpha():
        return key
    return default


class GeminiTranslator:
    """Bộ điều phối dịch thuật hỗ trợ 5 backend (Local Ollama, Groq/OpenAI, Google Free, Gemini API, Gemini CLI)."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self._client: Optional[genai.Client] = None
        self._client_key: str = ""
        self._thinking_mode_cache: dict[str, str] = {}

    # ------------------------------------------------------------------
    # Public translation methods (TEXT — dùng cùng Windows OCR cục bộ)
    # ------------------------------------------------------------------

    def translate_chat_text(self, raw_text: str) -> str:
        text = raw_text.strip()
        if not text:
            return "(Không phát hiện nội dung văn bản)"

        target_lang = self.config.target_language_read or "Tiếng Việt"
        if self.config.backend == "google_free":
            return self._call_google_free(text, target_lang, default_code="vi")

        prompt = (
            f"Dịch đoạn hội thoại chat sau sang {target_lang} sao cho tự nhiên, đúng ngữ cảnh chat.\n"
            f"Quy tắc: giữ nguyên tên người gửi và thứ tự dòng; chỉ trả về bản dịch, không giải thích.\n\n"
            f"{text}"
        )
        return self._dispatch_llm(prompt)

    def translate_game_movie_text(
        self,
        raw_text: str,
        history: Optional[list[str]] = None,
    ) -> str:
        text = raw_text.strip()
        if not text:
            return "(Không có lời thoại)"

        target_lang = self.config.target_language_read or "Tiếng Việt"
        if self.config.backend == "google_free":
            return self._call_google_free(text, target_lang, default_code="vi")

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
                "Các câu thoại đã dịch ngay trước đó (giữ đồng nhất xưng hô, tên riêng và mạch truyện):\n"
                f"{joined}"
            )

        parts.append(
            f"Chỉ trả về DUY NHẤT bản dịch phụ đề sang {target_lang}, gọn gàng, không giải thích.\n\n"
            f"Lời thoại cần dịch:\n{text}"
        )
        return self._dispatch_llm("\n\n".join(parts))

    def translate_reply(self, user_text: str, chat_context: str = "") -> str:
        target_lang = self.config.target_language_write or "Tiếng Anh"
        if self.config.backend == "google_free":
            return self._call_google_free(user_text.strip(), target_lang, default_code="en")

        context_block = ""
        if chat_context.strip():
            trimmed = chat_context.strip()[-1500:]
            context_block = (
                f"Ngữ cảnh cuộc hội thoại gần đây (chỉ để tham khảo giọng điệu):\n"
                f"---\n{trimmed}\n---\n\n"
            )

        prompt = (
            f"{context_block}"
            f"Dịch câu trả lời sau sang {target_lang} tự nhiên, đúng ngữ cảnh chat.\n"
            f"QUAN TRỌNG: Chỉ trả về DUY NHẤT câu đã dịch, không ngoặc kép, không giải thích.\n\n"
            f"{user_text.strip()}"
        )
        return self._dispatch_llm(prompt)

    # ------------------------------------------------------------------
    # Public translation methods (VISION — dùng khi tắt OCR cục bộ)
    # ------------------------------------------------------------------

    def translate_chat_image(self, image_bytes: bytes) -> str:
        target_lang = self.config.target_language_read or "Tiếng Việt"
        prompt = (
            f"Đọc toàn bộ tin nhắn trong ảnh chụp khung chat này và dịch tự nhiên sang {target_lang}.\n"
            f"Giữ nguyên tên người gửi và thứ tự tin nhắn, bỏ qua nút giao diện thừa, không giải thích.\n"
            f"Nếu ảnh không có chữ, trả về đúng: (Không phát hiện nội dung văn bản)"
        )
        return self._dispatch_llm(prompt, image_bytes=image_bytes)

    def translate_game_movie_image(
        self,
        image_bytes: bytes,
        history: Optional[list[str]] = None,
    ) -> str:
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
                "Các câu thoại đã dịch ngay trước đó (giữ đồng nhất xưng hô & tên riêng):\n"
                f"{joined}"
            )
        parts.append(
            f"Đọc phụ đề/lời thoại trong ảnh và chỉ trả về DUY NHẤT bản dịch {target_lang}, không giải thích.\n"
            "Nếu không có lời thoại, trả về đúng: (Không có lời thoại)"
        )
        return self._dispatch_llm("\n\n".join(parts), image_bytes=image_bytes)

    # ------------------------------------------------------------------
    # Dispatch & Backends
    # ------------------------------------------------------------------

    def _dispatch_llm(self, prompt: str, image_bytes: Optional[bytes] = None) -> str:
        b = self.config.backend
        if b == "local_ollama":
            return self._call_openai_compat(
                base_url=self.config.local_base_url or "http://localhost:11434/v1",
                api_key="ollama",
                model=self.config.local_model or "qwen2.5:7b",
                prompt=prompt,
                image_bytes=image_bytes,
                is_local=True,
            )
        if b == "openai_compat":
            return self._call_openai_compat(
                base_url=self.config.openai_base_url or "https://api.groq.com/openai/v1",
                api_key=self.config.openai_api_key.strip(),
                model=self.config.openai_model or "llama-3.3-70b-versatile",
                prompt=prompt,
                image_bytes=image_bytes,
                is_local=False,
            )
        if b == "gemini_cli":
            return self._call_gemini_cli(prompt, image_bytes=image_bytes)
        if b == "gemini_api":
            return self._call_gemini_api(prompt, image_bytes=image_bytes)
        raise TranslationError(
            "Backend hiện tại cần bật 'Đọc chữ tại máy (Windows OCR)' để dịch vùng màn hình."
        )

    def _call_google_free(
        self, text: str, target_lang_name: str, default_code: str = "vi"
    ) -> str:
        tl = _to_lang_code(target_lang_name, default=default_code)
        try:
            resp = requests.get(
                "https://translate.googleapis.com/translate_a/single",
                params={
                    "client": "gtx",
                    "sl": "auto",
                    "tl": tl,
                    "dt": "t",
                    "q": text,
                },
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            translated = "".join(
                seg[0] for seg in data[0] if isinstance(seg, list) and seg and seg[0]
            ).strip()
            if not translated:
                raise TranslationError("Google Translate không trả về nội dung.")
            return translated
        except TranslationError:
            raise
        except Exception as exc:
            raise TranslationError(f"Lỗi Google Translate miễn phí: {exc}") from exc

    def _call_openai_compat(
        self,
        base_url: str,
        api_key: str,
        model: str,
        prompt: str,
        image_bytes: Optional[bytes] = None,
        is_local: bool = False,
    ) -> str:
        if not is_local and not api_key:
            raise TranslationError(
                "Chưa có API Key cho Cloud API (Groq/OpenRouter/OpenAI). "
                "Mở Cài đặt (⚙) để nhập API Key."
            )

        url = base_url.rstrip("/") + "/chat/completions"
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        if image_bytes is not None:
            b64 = base64.b64encode(image_bytes).decode("ascii")
            user_content: object = [
                {"type": "text", "text": prompt},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                },
            ]
        else:
            user_content = prompt

        payload = {
            "model": model,
            "temperature": 0.2,
            "messages": [
                {"role": "user", "content": user_content},
            ],
        }

        try:
            resp = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=35 if is_local else 20,
            )
        except requests.ConnectionError as exc:
            if is_local:
                raise TranslationError(
                    f"Không kết nối được Local AI tại {base_url}. "
                    f"Hãy mở Ollama (hoặc LM Studio) và đảm bảo đã tải model `{model}` "
                    f"(chạy: ollama pull {model})."
                ) from exc
            raise TranslationError(f"Không kết nối được tới {base_url}: {exc}") from exc
        except requests.Timeout as exc:
            raise TranslationError("Model phản hồi quá lâu (timeout).") from exc
        except Exception as exc:
            raise TranslationError(f"Lỗi gọi API: {exc}") from exc

        if resp.status_code >= 400:
            detail = resp.text[:300].strip()
            if is_local and resp.status_code == 404:
                raise TranslationError(
                    f"Không tìm thấy model `{model}` trên Local AI. "
                    f"Hãy chạy `ollama pull {model}` hoặc bấm '🔄 Tải model' trong Cài đặt."
                )
            raise TranslationError(f"Lỗi API ({resp.status_code}): {detail}")

        try:
            data = resp.json()
            text = (data["choices"][0]["message"]["content"] or "").strip()
        except Exception as exc:
            raise TranslationError(f"Phản hồi API không hợp lệ: {exc}") from exc

        if not text:
            raise TranslationError("Model không trả về nội dung.")
        return text

    # ------------------------------------------------------------------
    # Gemini API (có tự tắt thinking + tự fallback khi 503/429)
    # ------------------------------------------------------------------

    def _get_api_client(self) -> genai.Client:
        api_key = self.config.api_key.strip()
        if not api_key:
            raise TranslationError(
                "Chưa có Gemini API Key. Mở Cài đặt (⚙) để nhập API key từ aistudio.google.com "
                "hoặc chuyển sang Local AI / Google Free."
            )
        if self._client is None or self._client_key != api_key:
            self._client = genai.Client(
                api_key=api_key,
                http_options=types.HttpOptions(timeout=20_000),
            )
            self._client_key = api_key
        return self._client

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
        primary = self.config.model or "gemini-3.8-flash"
        candidate_models = [primary]
        for fb in ("gemini-3.8-flash-lite", "gemini-flash-latest"):
            if fb not in candidate_models:
                candidate_models.append(fb)

        contents: list[object] = [prompt]
        if image_bytes is not None:
            contents.append(
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
            )

        last_exc: Optional[Exception] = None
        for model_name in candidate_models:
            cached = self._thinking_mode_cache.get(model_name)
            if cached is not None:
                modes_to_try = [cached]
            elif "gemini-3" in model_name.lower():
                modes_to_try = ["minimal", "budget0", "none"]
            else:
                modes_to_try = ["budget0", "minimal", "none"]

            overloaded = False
            for mode in modes_to_try:
                try:
                    response = client.models.generate_content(
                        model=model_name,
                        contents=contents,
                        config=self._build_fast_config(mode),
                    )
                    self._thinking_mode_cache[model_name] = mode
                    text = (response.text or "").strip()
                    if not text:
                        raise TranslationError("Gemini API không trả về nội dung.")
                    return text
                except TranslationError:
                    raise
                except Exception as exc:
                    last_exc = exc
                    err_str = str(exc).lower()
                    if "thinking" in err_str or "invalid_argument" in err_str:
                        continue
                    if "503" in err_str or "unavailable" in err_str or "429" in err_str or "404" in err_str:
                        overloaded = True
                        break
                    raise TranslationError(f"Lỗi Gemini API: {exc}") from exc

            if not overloaded:
                break

        raise TranslationError(f"Lỗi Gemini API: {last_exc}") from last_exc

    # ------------------------------------------------------------------
    # Gemini CLI
    # ------------------------------------------------------------------

    def _call_gemini_cli(self, prompt: str, image_bytes: Optional[bytes] = None) -> str:
        gemini_exe = shutil.which("gemini")
        if not gemini_exe:
            raise TranslationError(
                "Không tìm thấy lệnh `gemini` trên máy. Hãy cài Gemini CLI "
                "(`npm install -g @google/gemini-cli`) hoặc chuyển sang Local AI / Google Free."
            )

        tmp_path: Optional[Path] = None
        try:
            full_prompt = prompt
            if image_bytes is not None:
                with tempfile.NamedTemporaryFile(
                    suffix=".jpg", delete=False
                ) as tmp:
                    tmp.write(image_bytes)
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

    # ------------------------------------------------------------------
    # Model discovery helpers (Ollama / OpenAI-compat / Gemini)
    # ------------------------------------------------------------------

    def list_available_models(
        self,
        backend: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> list[str]:
        b = backend or self.config.backend
        if b == "local_ollama":
            url = (base_url or self.config.local_base_url or "http://localhost:11434/v1").rstrip("/")
            # Thử /models chuẩn OpenAI (chạy cho cả Ollama & LM Studio)
            try:
                resp = requests.get(f"{url}/models", timeout=5)
                if resp.ok:
                    data = resp.json().get("data", [])
                    names = [item["id"] for item in data if isinstance(item, dict) and item.get("id")]
                    if names:
                        return sorted(set(names))
            except Exception:
                pass
            # Thử /api/tags của Ollama
            root = url[:-3] if url.endswith("/v1") else url
            try:
                resp = requests.get(f"{root}/api/tags", timeout=5)
                resp.raise_for_status()
                models = [m["name"] for m in resp.json().get("models", []) if m.get("name")]
                return sorted(set(models))
            except Exception as exc:
                raise TranslationError(
                    f"Không kết nối được Local AI tại {url}. Hãy bật Ollama hoặc LM Studio trước."
                ) from exc

        if b == "openai_compat":
            url = (base_url or self.config.openai_base_url or "https://api.groq.com/openai/v1").rstrip("/")
            key = (api_key if api_key is not None else self.config.openai_api_key).strip()
            if not key:
                raise TranslationError("Hãy nhập API Key trước khi tải danh sách model.")
            try:
                resp = requests.get(
                    f"{url}/models",
                    headers={"Authorization": f"Bearer {key}"},
                    timeout=10,
                )
                resp.raise_for_status()
                data = resp.json().get("data", [])
                names = [item["id"] for item in data if isinstance(item, dict) and item.get("id")]
                return sorted(set(names))
            except Exception as exc:
                raise TranslationError(f"Không tải được danh sách model: {exc}") from exc

        # Gemini API
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
