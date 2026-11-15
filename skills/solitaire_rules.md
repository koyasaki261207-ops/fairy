# 🃏 KỸ NĂNG: CHIẾN THUẬT & LUẬT CHƠI GAME BÀI (SOLITAIRE KLONDIKE)

## 1. MỤC TIÊU VÁN BÀI
Đưa toàn bộ 52 lá bài lên 4 ô đích (Foundations ở góc trên bên phải), xếp theo 4 chất (Cơ, Rô, Bích, Tép) từ Át (A) đến K:
`A(1) -> 2 -> 3 -> 4 -> 5 -> 6 -> 7 -> 8 -> 9 -> 10 -> J(11) -> Q(12) -> K(13)`.

## 2. BẢNG TRA CỨU GIÁ TRỊ & MÀU SẮC (BẮT BUỘC TUÂN THỦ)
- **Thứ tự giá trị (Rank):** `K (13) > Q (12) > J (11) > 10 > 9 > 8 > 7 > 6 > 5 > 4 > 3 > 2 > A (1)`.
- **Phân loại màu (Color):**
  - **Màu ĐỎ:** Cơ (Hearts ♥), Rô (Diamonds ♦).
  - **Màu ĐEN:** Bích (Spades ♠), Tép/Chuồn (Clubs ♣).

## 3. QUY TẮC BẤT DI BẤT DỊCH TRÊN 7 CỘT BÀI (TABLEAU)
- **Ghép bài xen kẽ màu:** Chỉ được đặt quân **ĐEN lên ĐỎ** hoặc **ĐỎ lên ĐEN**.
  - Ví dụ hợp lệ: `7♦` (Đỏ 7) đặt lên `8♣` (Đen 8); `3♥` (Đỏ 3) đặt lên `4♣` (Đen 4); `10♠` (Đen 10) đặt lên `J♥` (Đỏ 11).
  - **CẤM KÉO CÙNG MÀU:** Không bao giờ được đặt Đen lên Đen (như J♣ lên 10♠ là SAI!), hoặc Đỏ lên Đỏ.
- **Giá trị giảm dần đúng 1 nút:** Quân chuyển đi (nguồn) phải có Giá trị = Giá trị quân đích - 1.
  - **CẤM KÉO QUÂN LỚN LÊN QUÂN NHỎ:** Kéo J(11) lên 10(10) là SAI HOÀN TOÀN! (Chỉ có thể kéo 10 lên J).
- **Cột trống (Empty Column):** Chỉ có duy nhất quân **K (King, 13)** hoặc dây bài bắt đầu bằng K mới được đặt vào cột trống.
- **Bốc cả cụm bài ngửa (Stack Moves):** Khi một cột có dây bài ngửa (ví dụ `4♣` ở trên `3♥`), ta ĐƯỢC PHÉP và NÊN bốc cả cụm này sang đè lên quân lớn hơn 1 nút khác màu (ví dụ đặt lên `5♦`). Thao tác này giúp mở khóa lá bài úp của cột nguồn!
- **Thao tác chuột tối ưu:** Dùng `solitaire_move_by_column(from_col, to_col, source_card, target_card)` để di chuyển theo số cột chuẩn xác 100%. Dùng `solitaire_draw_card()` để rút bài mới.

## 4. QUY TẮC ĐƯA LÊN 4 Ô ĐÍCH (FOUNDATIONS)
- Bắt đầu bằng lá Át (A - giá trị 1).
- Tăng dần cùng chất: `A -> 2 -> 3 -> 4 -> 5...`
- Khi thấy lá Át hoặc lá bài nhỏ tiếp theo xuất hiện: Nhấp đúp (`mouse_double_click`) trực tiếp vào lá bài đó để game tự động đưa lên ô đích.

## 5. THUẬT TOÁN 4 BƯỚC MỖI LƯỢT QUAN SÁT (HEURISTICS CHECKLIST)
Mỗi khi chụp ảnh màn hình, AI PHẢI duyệt kỹ theo 4 bước sau trong Thought trước khi ra lệnh chuột:
1. **Bước 1 (Ô đích):** Có quân Át (A) nào chưa lên ô đích không? Nếu có -> nhấp đúp `mouse_double_click` đưa lên ngay.
2. **Bước 2 (Quét toàn bộ 7 cột):** Quét từng lá bài ngửa trên 7 cột từ trái sang phải:
   - Có lá bài nào ghép được sang lá bài khác trên 7 cột không?
   - Ưu tiên 2.1: Chuyển lá bài để lật mở lá bài úp phía dưới (ví dụ: `7♦` ở Cột 5 sang `8♣` ở Cột 6 để mở bài úp Cột 5).
   - Ưu tiên 2.2: Chuyển lá bài để giải phóng toàn bộ cột thành CỘT TRỐNG (ví dụ: `3♥` ở Cột 1 sang `4♣` ở Cột 4 để Cột 1 trống sẵn sàng cho K).
3. **Bước 3 (Chồng bài lật - Waste Pile):** Nếu trên 7 cột không thể ghép với nhau, kiểm tra lá bài ngửa ở Chồng bài lật xem có ghép được vào cột nào không.
4. **Bước 4 (Rút bài mới từ Stockpile):** Nếu và CHỈ KHI toàn bộ bàn cờ KHÔNG CÒN NƯỚC ĐI NÀO HỢP LỆ:
   - Click chuột đơn `mouse_click_coords` vào **Chồng bài úp (Stockpile)** ở góc trên bên trái để rút lật bài mới!
   - TUYỆT ĐỐI KHÔNG click bừa hoặc kéo thả vu vơ vào các lá bài không hợp lệ.

## 6. CÔNG CỤ HỖ TRỢ KIỂM ĐỊNH (GUARDRAIL TOOL)
- Luôn có thể gọi `validate_card_move(source_card='...', target_card='...')` để kiểm tra tính hợp lệ trước khi thao tác chuột.

## 7. CÔNG CỤ DI CHUYỂN BÀI (ƯU TIÊN DÙNG)
- `solitaire_move_by_column(from_col, to_col, source_card, target_card)`: tự căn tọa độ cột, tự kiểm định luật, kích hoạt cửa sổ game.
  - `from_col`: 1..7 là Cột 1..7; 0 là Chồng bài lật (Waste).
  - `to_col`: 1..7 là Cột 1..7; 8 là 4 Ô đích (Foundations).
  - Ví dụ: 7 Rô ở Cột 5 sang 8 Tép ở Cột 6 -> `solitaire_move_by_column(from_col=5, to_col=6, source_card='7 Rô', target_card='8 Tép')`.
  - Bốc cả cụm [4♣, 3♥] ở Cột 4 sang 5♦ ở Cột 5 -> `solitaire_move_by_column(from_col=4, to_col=5, source_card='4 Tép', target_card='5 Rô')` (truyền lá GỐC của cụm).
- `solitaire_draw_card()`: rút bài mới từ Stockpile — chỉ khi đã quét hết mà không còn nước đi hợp lệ.
- Mẹo tiết kiệm: sau mỗi ảnh chụp, ghi ngắn trạng thái bàn bài (lá ngửa trên cùng của 7 cột, Waste, 4 ô đích) trong suy nghĩ, vì ảnh cũ sẽ bị lược khỏi lịch sử.
