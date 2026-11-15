# 🤖 Gemini AutoPilot - Siêu Trợ Lý AI Điều Khiển Máy Tính Toàn Năng

**Gemini AutoPilot** là một hệ thống tự động hóa máy tính Windows thế hệ mới, kết hợp trí tuệ nhân tạo **Google Gemini Multimodal Vision** với kiến trúc **Hybrid Đa Tầng Toàn Năng (Direct OS CLI + Windows UIAutomation + Computer Vision + Dynamic Code Interpreter + Skill Acquisition)**.

Chương trình cho phép bạn chỉ cần ra lệnh bằng tiếng Việt tự nhiên, AI có thể làm được mọi tác vụ: từ văn phòng, xử lý tài liệu, lướt web, điều khiển ứng dụng đồ họa/game cho đến **tự viết mã Python để giải quyết bất kỳ bài toán hóc búa nào**.

---

## ⚡ 4 Trụ Cột Giúp Hệ Thống "Làm Được Mọi Thứ"

1. **Sức Mạnh Tự Viết & Chạy Code (Code Interpreter - `run_python_code`):**
   - Khi gặp bài toán khó (thuật toán game, xử lý ảnh pixel, tính toán toán học, bóc tách dữ liệu phức tạp): AI **tự viết script Python và chạy trực tiếp trên máy** để tìm ra lời giải chính xác 100%, không bao giờ phải đoán mò!
2. **Kho Tri Thức & Kỹ Năng Tự Học (`skills/`):**
   - Hỗ trợ `list_skills`, `load_skill` và `save_skill`. Khi AI học được một quy trình giải quyết vấn đề mới, nó sẽ tự lưu lại cẩm nang vào thư mục `skills/` để tái sử dụng mãi mãi.
3. **Mắt Thị Giác AI & Chuột Toàn Năng (Vision & Complete Mouse):**
   - AI có mắt thực sự: Chụp ảnh màn hình độ nét cao (`take_screenshot_to_see`) và nhận diện tọa độ chuẩn hóa `[0 - 1000]`.
   - Đầy đủ 6 thao tác chuột: Click đơn, nhấp đúp, click phải, kéo thả chuột (`mouse_drag_and_drop`), rê chuột (`mouse_hover`) và cuộn trang.
4. **Hệ Thống Phím Nóng & Quota Xoay Vòng:**
   - Dừng khẩn cấp bằng phím **`F8`** bất cứ lúc nào.
   - Hỗ trợ nhập nhiều API Key (phân cách bằng dấu phẩy) để tự động xoay vòng key khi chạm hạn ngạch.

---

## 🚀 Hướng Dẫn Sử Dụng Nhanh

### Bước 1: Khởi Chạy Chương Trình
* Nhấp đúp chuột vào tệp [**`run.bat`**](run.bat) (hoặc chạy `.\.venv\Scripts\python.exe main.py`).

### Bước 2: Cấu Hình API Key
* Bấm nút **`⚙ Cấu hình`** trên giao diện và dán một hoặc nhiều API Key của bạn vào ô.

### Bước 3: Ra Lệnh Cho AI!
Gõ bất kỳ yêu cầu nào và bấm **`▶ BẮT ĐẦU THỰC HIỆN`**!

---

## 💡 Ví Dụ Các Tác Vụ Toàn Năng Có Thể Làm

* **Tự lập trình & Tính toán nâng cao:**
  > *"Viết script Python tính toán thống kê và vẽ biểu đồ doanh số lưu ra Desktop."*
* **Tự học & Tra cứu cẩm nang kỹ năng:**
  > *"Đọc cẩm nang solitaire_rules trong thư mục skills và tóm tắt chiến thuật chơi bài."*
* **Xử lý tài liệu học tập:**
  > *"mở thư mục KTMT_HN Đoan ra và tóm tắt từng nội dung của 3 chapter đầu tiên, tìm nội dung cốt lõi và đưa vào trong notepad"*
* **Thao tác đồ họa & Game:**
  > *"Mở Paint và kéo thả chuột vẽ một ngôi nhà hoàn chỉnh."*
