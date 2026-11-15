# 📄 KỸ NĂNG: XỬ LÝ & TÓM TẮT TÀI LIỆU HÀNG LOẠT (BATCH PROCESSING)

## 1. MỤC TIÊU
Đọc, phân tích và tóm tắt nhanh hàng loạt tài liệu (PDF, Word, Text, Code) chỉ trong 3-5 bước, tiết kiệm tối đa số lượng API request.

## 2. QUY TRÌNH TỐI ƯU
1. **Tìm kiếm thư mục:** Dùng `run_powershell` quét ổ đĩa tìm thư mục mục tiêu:
   `Get-ChildItem -Path "D:\", "C:\Users" -Filter "*<keyword>*" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 5 FullName`
2. **Đọc nội dung:** Dùng `read_file_content(file_path=...)` đọc thẳng nội dung các tệp quan trọng (slide, tài liệu). Tuyệt đối không viết script giải nén XML thủ công!
3. **Phân tích trong đầu:** Tự chắt lọc kiến thức cốt lõi, công thức, định nghĩa trong trí não AI.
4. **Xuất kết quả:** Dùng `run_powershell` ghi tệp ra Desktop với mã hóa UTF-8:
   `Set-Content -Path "$env:USERPROFILE\Desktop\TomTat.txt" -Value $content -Encoding UTF8; Start-Process "$env:USERPROFILE\Desktop\TomTat.txt"`
5. **Hoàn thành:** Gọi `finish_task` tóm tắt kết quả cho người dùng.
