# QuickTranslate — Dịch khung chat, Game & Phim siêu tốc trên Windows

Ứng dụng desktop nhỏ gọn (1 file `.exe` độc lập) giúp bạn đọc hiểu và trả lời chat ngoại ngữ hoặc dịch phụ đề game/phim theo thời gian thực:

- **Windows OCR cục bộ (~0.1 giây, 100% offline):** Đọc chữ ngay trên máy, tự bỏ qua khi lời thoại chưa đổi (kể cả khi nền game/phim đang chuyển động).
- **5 Backend dịch để chọn linh hoạt trong Cài đặt (⚙):**
  1. **🌐 Dịch nhanh miễn phí (Google Translate — mặc định):** Không cần API Key, mở lên dùng được ngay (~0.2 giây).
  2. **🏠 Local AI (Ollama / LM Studio):** Chạy 100% offline trên GPU/CPU máy bạn — **0 đồng, 0 lỗi 503, nhớ ngữ cảnh Game/Phim cực mượt** (`qwen2.5:7b`, `qwen3:8b`, `gemma3:4b`, `gemma3:12b`).
  3. **⚡ Cloud siêu nhanh (Groq / OpenRouter / DeepSeek / OpenAI):** Groq có gói miễn phí tốc độ ~0.2 giây/câu, nhớ ngữ cảnh tốt.
  4. **✨ Gemini API:** Tự tắt Thinking để tăng tốc & tự chuyển model dự phòng khi gặp lỗi 503.
  5. **💻 Gemini CLI:** Dùng quota gói Google AI Pro nếu đã cài `gemini`.
- **Chế độ Chat:** Khóa khung chat → dịch Tiếng Việt; gõ Tiếng Việt nhấn `Enter` → dịch sang Tiếng Anh theo ngữ cảnh và tự điền vào đúng con trỏ ô chat đã ghim.
- **Chế độ 🎮 Dịch Game / Phim:** Thu gọn chỉ hiện **khung phụ đề nổi Always-on-top** (có khóa xuyên chuột `Ctrl + Shift + L` để chơi game không click nhầm) + **bộ nhớ ngữ cảnh xuyên suốt** giữ đồng nhất xưng hô & tên nhân vật.

---

## Cách dùng nhanh (không cần cài Python)

1. Vào mục **Releases** ở cột phải → tải file **`QuickTranslate.exe`**.
2. Nhấp đúp mở **`QuickTranslate.exe`** (mặc định dùng sẵn **Google Free — không cần API Key** để test ngay).
3. Nếu muốn dịch mượt + nhớ ngữ cảnh Game/Phim **offline trên máy mạnh (như RTX 40/50 / Legion 5)**:
   - Cài [Ollama](https://ollama.com/download) → mở PowerShell chạy `ollama pull qwen2.5:7b` (hoặc `ollama pull gemma3:4b`).
   - Vào **⚙ Cài đặt** trong QuickTranslate → chọn **🏠 Local AI (Ollama / LM Studio)** → bấm **Save**!

---

## Phím tắt toàn cục

| Phím tắt | Chức năng |
|---|---|
| `Ctrl + Shift + S` | Kéo chọn & khóa khung chat / khung phụ đề trên màn hình |
| `Ctrl + Shift + T` | Click để ghim vị trí ô nhập văn bản trong khung chat |
| `Ctrl + Shift + D` | Dịch khung ngay lập tức |
| `Ctrl + Shift + M` | Chuyển nhanh giữa chế độ **Chat** ↔ **Phụ đề Game / Phim** (chỉ hiện phần dịch, luôn nổi) |
| `Ctrl + Shift + L` | Khóa / mở khóa xuyên chuột (click-through) cho khung phụ đề khi chơi game |
| `Enter` (trong ô trả lời) | Dịch sang Tiếng Anh & điền vào ô chat đã ghim |
| `Shift + Enter` | Xuống dòng trong ô trả lời |

---

## Tự build từ mã nguồn

```powershell
git clone https://github.com/takidang/quick-translate.git
cd quick-translate
uv sync
.\build_exe.bat
```
