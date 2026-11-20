# QuickTranslate — Dịch khung chat & điền nhanh với Gemini

Ứng dụng desktop nhỏ gọn cho Windows giúp bạn đọc hiểu và trả lời chat ngoại ngữ ngay trên màn hình:

- **Chọn & khóa (block) 1 khung chat / khung phụ đề trên màn hình** với viền xanh luôn nổi, xuyên chuột (click-through).
- **Chế độ Chat:** Dịch toàn bộ khung chat sang Tiếng Việt + gõ Tiếng Việt nhấn `Enter` để dịch sang Tiếng Anh theo ngữ cảnh và tự điền vào đúng con trỏ khung chat đã ghim.
- **Chế độ Dịch Game / Phim (Khung phụ đề nổi — Always-on-top):**
  - Thu gọn chỉ còn **khung phụ đề trong suốt luôn nổi trên cùng** (chỉ hiện phần dịch, kéo thả di chuyển & đổi cỡ tự do, có nút **Khóa xuyên chuột** bằng `Ctrl + Shift + L` để chơi game không click nhầm).
  - **Nhớ ngữ cảnh xuyên suốt** các câu thoại trước đó (đồng nhất xưng hô, tên nhân vật, thuật ngữ game/phim), kèm ô ghi chú tên nhân vật/bối cảnh trong Cài đặt.
- **Tự động dịch khi có tin/thoại mới** (chỉ gọi API khi ảnh trong khung thật sự thay đổi để tiết kiệm token).
- **Tự nhập API Key của riêng bạn** (lưu cục bộ trên máy, có nút mở thẳng trang lấy API Key miễn phí). Hỗ trợ thêm backend **Gemini CLI** nếu bạn dùng gói Google AI Pro.

---

## Cách dùng nhanh (không cần cài Python)

1. Vào mục **Releases** ở cột phải → tải file **`QuickTranslate.exe`**.
2. Nhấp đúp mở **`QuickTranslate.exe`**.
3. Bấm nút **⚙ (Cài đặt)** → dán **Gemini API Key** của bạn (lấy miễn phí tại [Google AI Studio](https://aistudio.google.com/apikey)) → bấm **Save**.
4. Bấm **📐 Chọn khung** (`Ctrl + Shift + S`) để kéo khóa vùng chat cần dịch.
5. Bấm **🎯 Ghim ô chat** (`Ctrl + Shift + T`) rồi click vào ô nhập tin nhắn của ứng dụng chat bạn muốn điền.
6. Bấm **⚡ Dịch ngay** (`Ctrl + Shift + D`) hoặc tích **Tự động dịch khi có tin mới**. Gõ Tiếng Việt ở ô dưới rồi nhấn **`Enter`** để dịch & điền nhanh!

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

## Tự chạy / tự build từ mã nguồn

Yêu cầu: Python 3.11+ và [uv](https://docs.astral.sh/uv/).

```powershell
git clone https://github.com/takidang/quick-translate.git
cd quick-translate
uv sync
uv run quick-translate
```

Đóng gói lại thành 1 file `.exe` độc lập:

```powershell
.\build_exe.bat
```

File sau khi build nằm tại `dist\QuickTranslate.exe`.
