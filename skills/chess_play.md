# ♟️ KỸ NĂNG: CHƠI CỜ VUA (LICHESS, CHESS.COM, ỨNG DỤNG CỜ)

**Từ khóa:** chess, co vua, cờ vua, lichess, stockfish, nuoc co, van co

Gợi ý nhanh: mở trang cờ (vd open_app_and_wait('https://lichess.org') - không cần đăng nhập), bắt đầu ván với máy (desktop_snapshot/click_mark các nút "Chơi với máy tính" → chọn cấp độ/màu → "Chơi"), rồi gọi chess_play() MỘT lần: code tự dò bàn cờ, nhận nước đối thủ, tính nước và click tới hết ván (0 token mỗi nước). KHÔNG tự chụp ảnh để đi từng nước.

## Quy trình
1. Mở trang/ứng dụng cờ và bắt đầu một ván (đối thủ máy hoặc người).
2. Đảm bảo bàn cờ hiển thị trọn vẹn trên màn hình (không bị hộp thoại che, không cuộn mất).
3. `chess_play()` - tự chơi tới khi hết ván. Tham số:
   - `my_color`: auto (màu quân ở phía dưới bàn) / white / black.
   - `max_moves`: số nước tối đa trong lần gọi này (mặc định 200 = cả ván).
   - `think_seconds`: thời gian nghĩ mỗi nước (mặc định 0.6s; Stockfish nếu có STOCKFISH_PATH hoặc bin/stockfish.exe).
   - `fen`: chỉ dùng khi ván đã đi dở mà chưa theo dõi từ đầu.
4. Đọc báo cáo: "VÁN CỜ KẾT THÚC" → finish_task. "Tạm dừng: ..." → làm theo lý do (đóng hộp thoại, gọi lại chess_play để chơi tiếp).
