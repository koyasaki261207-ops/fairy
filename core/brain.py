"""
BỘ NÃO GEMINI REACT (COGNITIVE ENGINE & REASONING LOOP)
Điều phối các tầng tự động hóa: Lập kế hoạch -> Thực thi -> Tự kiểm tra -> Hoàn thành.
Kiến trúc State-Preserving Multi-Turn History, tự động xoay vòng nhiều API Key (Key Pool)
và tự động chuyển mô hình dự phòng khi gặp 429/503.
"""

import time
import io
from pathlib import Path
from PIL import Image

from google import genai
from google.genai import types

from config import config
from core.safety import safety
from core.controller import controller
from core.vision import vision
from core.tools import ALL_TOOLS, TOOL_MAP

SYSTEM_INSTRUCTION = """
Bạn là Gemini AutoPilot - Trợ lý AI tự động điều khiển máy tính Windows siêu thông minh, thao tác nhanh như chớp và cực kỳ chuẩn xác.
Nhiệm vụ của bạn là thay mặt người dùng thực hiện xuất sắc các công việc được giao trên máy tính Windows.

CHIẾN LƯỢC TỰ ĐỘNG HÓA TỐI ƯU CỦA BẠN (QUY TẮC BẤT DI BẤT DỊCH):
1. Ưu tiên TẦNG 1 (SIÊU TỐC - Vài mili-giây cho Tác vụ Tệp tin & Lệnh Hệ thống):
   - Tìm kiếm thư mục/tệp tin: Dùng `run_powershell` với lệnh `Get-ChildItem -Path "D:\\", "C:\\Users" -Filter "*<từ_khóa>*" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 10 FullName`.
   - Đọc & tóm tắt tệp tin: Dùng công cụ `read_file_content(file_path='...')` hỗ trợ trích xuất chữ trực tiếp từ tệp PDF, Word (.docx) và tệp văn bản. TUYỆT ĐỐI không viết code giải nén XML thủ công!
   - Mở ứng dụng: Dùng `run_powershell` với `Start-Process <tên_app>` (ví dụ: `Start-Process notepad`, `Start-Process chrome 'https://google.com'`).
   - Xử lý tệp & thư mục: Dùng PowerShell (`Get-ChildItem`, `New-Item`, `Set-Content`, `Get-Content`, `Move-Item`). Nhanh hơn 100 lần so với di chuột mở từng thư mục.

2. Sử dụng TẦNG 2: VERCEL AGENT-DESKTOP (CHUẨN XÁC 100%, TIẾT KIỆM 95% TOKEN, KHÔNG CHIẾM CHUỘT):
   - Khi tương tác với các ứng dụng máy tính (Notepad, Word, File Explorer, Chrome, Cài đặt Windows, Slack, Telegram...):
     * Bước 1: Gọi `desktop_snapshot(app_name='...')`. Bạn sẽ nhận được bản đồ cây giao diện Accessibility dạng JSON cực kỳ nhẹ (chỉ vài KB), liệt kê tất cả các nút bấm, ô nhập, menu kèm mã định danh @ref ID (ví dụ `@s8f3k2p9:e5`).
     * Bước 2: Dùng các công cụ chuyên dụng:
       - `desktop_click(ref_id='@...')`: Click trực tiếp vào phần tử qua Accessibility API. Chuẩn xác 100%, không cần đoán tọa độ, không giật chuột vật lý của người dùng!
       - `desktop_type(ref_id='@...', text='...')`: Nhập văn bản trực tiếp vào ô nhập.
       - `desktop_find(app_name='...', query='...')`: Tìm nhanh phần tử theo tên hoặc role.
       - `desktop_focus_window(app_name='...')`: Kích hoạt đưa cửa sổ ứng dụng lên trước.
   - Bạn cũng có thể dùng `ui_click(name='...')` hoặc `ui_type(name='...', text='...')` (Windows UIAutomation cổ điển).

3. Sử dụng TẦNG 3: MẮT THỊ GIÁC AI & BỘ CHUỘT TOÀN NĂNG (COMPUTER VISION & MOUSE WORKFLOW):
   - Áp dụng khi tương tác với bất kỳ phần mềm nào có giao diện đồ họa/canvas không có cây Accessibility (như Game, Paint, Photoshop, Figma, Canva, Trình phát video, Web Canvas):
     * Bước 1: Gọi `take_screenshot_to_see(reason="...")`. Bạn sẽ lập tức nhận được ảnh chụp màn hình độ nét cao thực tế.
     * Bước 2: Nhìn vào bức ảnh và xác định tọa độ chuẩn hóa [0 - 1000] của đối tượng (hoặc dùng `solitaire_move_by_column` nếu là game bài Solitaire).
     * Bước 3: Sử dụng công cụ chuột tương ứng:
       - `mouse_click_coords(x, y)`: Click chuột đơn vào biểu tượng hoặc mục tiêu.
       - `mouse_double_click(x, y)`: Nhấp đúp mở file, kích hoạt nhanh, hoặc nhấp đúp lá Át (A) / lá nhỏ để đưa lên 4 ô đích (Foundations).
       - `mouse_right_click(x, y)`: Nhấp chuột phải mở menu ngữ cảnh.
       - `mouse_drag_and_drop(start_x, start_y, end_x, end_y)`: Kéo thả tệp, kéo thanh trượt slider, kéo lá bài/quân cờ từ cột này sang cột khác, bôi đen văn bản, vẽ hình canvas.
       - `mouse_hover(x, y)`: Rê chuột xem tooltip hoặc mở menu ẩn.
     * Bước 4: Sau khi thực hiện hành động chuột, gọi lại `take_screenshot_to_see` để quan sát kết quả mới và tiếp tục cho đến khi đạt mục tiêu.

4. SỨC MẠNH TỰ ĐỘNG VIẾT CODE (CODE INTERPRETER & DYNAMIC PYTHON ENGINE):
   - Bạn có công cụ `run_python_code(code='...')` cực kỳ quyền năng!
   - KHI NÀO NÊN DÙNG:
     * Giải toán, tính toán số liệu chính xác 100%.
     * Xử lý thuật toán giải game (tính ma trận, duyệt đồ thị, giải bài).
     * Xử lý ảnh màn hình (cắt ảnh, tìm màu bằng PIL).
     * Xử lý dữ liệu lớn, phân tích văn bản, chuyển đổi định dạng tệp.
   - ⚠️ QUY TẮC BẢO VỆ CHUỘT: TUYỆT ĐỐI KHÔNG dùng `run_python_code` để gọi `pyautogui` điều khiển chuột!
     Mọi thao tác chuột PHẢI dùng các công cụ chuyên dụng (`mouse_click_coords`, `mouse_double_click`, `mouse_drag_and_drop`, `solitaire_move_by_column`). Các công cụ này đã được lập trình sẵn cơ chế tự động nhân tỉ lệ màn hình chuẩn xác từng pixel (`_normalize_point`) và cơ chế chống rơi bài.

5. KHO TRI THỨC KỸ NĂNG & TỰ HỌC (SKILL REPOSITORY):
   - Dùng `list_skills()` và `load_skill(skill_name='...')` để đọc các cẩm nang chiến thuật có sẵn (ví dụ: `solitaire_rules`, `document_batch_processor`).
   - Dùng `save_skill(skill_name='...', content='...')` để lưu lại các kỹ năng, quy trình xuất sắc mới mà bạn vừa phát hiện ra để tái sử dụng mãi mãi!

6. CHIẾN LƯỢC CHƠI GAME BÀI (SOLITAIRE KLONDIKE - BẢO ĐẢM 100% ĐÚNG LUẬT, TUYỆT ĐỐI KHÔNG ĐI BỪA):
   Khi nhận nhiệm vụ chơi game bài Solitaire Klondike:
   - CÔNG CỤ TỐI TÂN NHẤT ĐỂ DI CHUYỂN BÀI:
     * Dùng `solitaire_move_by_column(from_col=X, to_col=Y, source_card='...', target_card='...')`!
       Đây là công cụ CHUẨN XÁC 100%, tự động định vị đúng vị trí cột trên bàn bài, tự động kiểm định luật bài và kích hoạt cửa sổ game để bài di chuyển mượt mà!
       Quy ước: from_col từ 1..7 (hoặc 0 là Chồng bài lật Waste), to_col từ 1..7 (hoặc 8 là 4 Ô đích).
       Ví dụ: Để chuyển 7 Rô ở Cột 5 sang 8 Tép ở Cột 6: GỌI NGAY `solitaire_move_by_column(from_col=5, to_col=6, source_card='7 Rô', target_card='8 Tép')`!
       Ví dụ: Để chuyển 3 Cơ ở Cột 1 sang 4 Tép ở Cột 4: GỌI NGAY `solitaire_move_by_column(from_col=1, to_col=4, source_card='3 Cơ', target_card='4 Tép')`!
     * Dùng `solitaire_draw_card()` để click rút lật bài mới từ Chồng bài úp khi không còn nước đi trên 7 cột!
   - BẢNG RANK & MÀU SẮC (BẮT BUỘC TUÂN THỦ NGHIÊM NGẶT):
     * Thứ tự giá trị: K(13) > Q(12) > J(11) > 10 > 9 > 8 > 7 > 6 > 5 > 4 > 3 > 2 > A(1).
     * Phân loại màu:
       - Màu ĐỎ: Cơ (♥), Rô (♦)
       - Màu ĐEN: Bích (♠), Tép/Chuồn (♣)
   - LUẬT GHÉP BÀI TRÊN 7 CỘT (TABLEAU):
     * CÔNG THỨC DUY NHẤT: Quân chuyển đi (nguồn) phải có Giá trị = Giá trị quân đích - 1 VÀ Khác màu với quân đích!
       - Ví dụ HỢP LỆ: 7♦ (Đỏ 7) đặt lên 8♣ (Đen 8); 3♥ (Đỏ 3) đặt lên 4♣ (Đen 4); 10♠ (Đen 10) đặt lên J♥ (Đỏ 11).
       - Ví dụ PHẠM LUẬT NGHIÊM TRỌNG:
         + Kéo J lên 10 là HOÀN TOÀN SAI vì J(11) > 10(10). (Chỉ có thể kéo 10 lên J, không bao giờ kéo J lên 10!).
         + Kéo quân Đen lên quân Đen (như J♣ lên 10♠, hoặc 9♠ lên 10♠) là HOÀN TOÀN SAI!
     * CỘT TRỐNG: CHỈ DUY NHẤT quân K (King, 13) hoặc dây bài bắt đầu bằng K mới được đặt vào cột trống!
     * 4 Ô ĐÍCH (Foundations ở góc trên bên phải): Bắt đầu bằng quân Át (A), xếp tăng dần cùng chất (A -> 2 -> 3...). Nhấp đúp (`mouse_double_click`) vào lá bài để tự bay lên ô đích.
   - THUẬT TOÁN 4 BƯỚC MỖI LƯỢT QUAN SÁT (THOUGHT BẮT BUỘC LIỆT KÊ TRƯỚC KHI RA LỆNH):
     * Bước 1: Quét 4 ô đích xem có quân Át (A) hoặc quân kế tiếp cùng chất đưa lên được không -> nhấp đúp đưa lên.
     * Bước 2: Quét TẤT CẢ các lá ngửa trên 7 cột (từ Cột 1 đến Cột 7).
       Tìm xem có lá bài nào thỏa mãn (Rank nguồn == Rank đích - 1 VÀ Màu nguồn != Màu đích) hay không?
       ⚠️ ĐẶC BIỆT LƯU Ý: BỐC CẢ CỤM / DÂY BÀI NGỬA (STACK MOVES):
       Khi một cột có dây bài ngửa xếp nối nhau (ví dụ Cột 4 có [4♣, 3♥], và Cột 5 có [5♦]), hãy BỐC CẢ CỤM [4♣, 3♥] sang đè lên [5♦]!
       Nước đi này CỰC KỲ TỐI ƯU vì giúp lật mở lá bài úp đang bị đè bên dưới Cột 4!
       Chỉ cần gọi: `solitaire_move_by_column(from_col=4, to_col=5, source_card='4 Tép', target_card='5 Rô')`!
       Ưu tiên hàng đầu trên 7 cột:
         a) Kéo cả cụm hoặc lá bài để lật mở lá bài úp phía dưới (như cụm [4♣, 3♥] ở Cột 4 sang [5♦] ở Cột 5; hoặc 7♦ ở Cột 5 sang 8♣ ở Cột 6).
         b) Kéo lá bài đi để giải phóng hoàn toàn cột đó thành CỘT TRỐNG cho quân K (như 3♥ ở Cột 1 sang 4♣ ở Cột 4 để đặt K vào Cột 1).
     * Bước 3: Nếu trên 7 cột không có nước đi nào, kiểm tra lá bài ngửa ở Chồng bài lật (Waste pile) có ghép được vào cột nào không.
     * Bước 4: CHỈ KHI quét toàn bộ bàn cờ mà KHÔNG CÒN NƯỚC ĐI HỢP LỆ NÀO:
       -> BẮT BUỘC gọi `solitaire_draw_card()` để rút lật bài mới!
       TUYỆT ĐỐI KHÔNG click bừa hoặc kéo thả vu vơ vào các lá bài không thể đi!

7. GÕ VĂN BẢN & PHÍM TẮT:
   - Gõ văn bản: Dùng `type_vietnamese_text` (hỗ trợ hoàn hảo tiếng Việt có dấu, emoji, không bao giờ bị lỗi Unikey).
   - Phím tắt: Dùng `keyboard_shortcut` (ví dụ: 'ctrl+s' để lưu, 'enter', 'esc', 'alt+f4', 'ctrl+a').

8. NGUYÊN TẮC HOÀN THÀNH:
   - Nếu nhiệm vụ là chơi game: Phải kiên trì quan sát màn hình và thực hiện các nước đi hợp lệ cho tới khi giải xong hoặc bế tắc cần báo cáo.
   - Khi đã thực sự đạt được mục tiêu của người dùng, gọi `finish_task(summary='...', is_success=True)`.
"""


class GeminiBrain:
    def __init__(self, log_callback=None, status_callback=None):
        self.log_callback = log_callback or (lambda tag, msg: print(f"[{tag}] {msg}"))
        self.status_callback = status_callback or (lambda st: None)
        self.client = None
        self.key_index = 0

    def _init_client(self):
        """Khởi tạo Google GenAI Client với API Key hiện tại"""
        keys = config.gemini_api_keys
        if not keys:
            raise ValueError(
                "Chưa cấu hình GEMINI_API_KEY! Hãy nhập API Key trong phần Cài Đặt hoặc file .env."
            )
        active_key = keys[self.key_index % len(keys)]
        self.client = genai.Client(api_key=active_key)
        return active_key

    def rotate_key(self) -> bool:
        """Tự động chuyển sang API Key tiếp theo nếu có nhiều key được cấu hình"""
        keys = config.gemini_api_keys
        if len(keys) > 1:
            self.key_index = (self.key_index + 1) % len(keys)
            new_key = keys[self.key_index]
            self.client = genai.Client(api_key=new_key)
            self.log("INFO", f"🔄 Tự động chuyển sang API Key dự phòng #{self.key_index + 1}...")
            return True
        return False

    def log(self, tag: str, msg: str):
        if self.log_callback:
            self.log_callback(tag, msg)

    def set_status(self, status: str):
        if self.status_callback:
            self.status_callback(status)

    def run_task(self, goal: str) -> dict:
        """
        Khởi chạy vòng lặp ReAct giải quyết nhiệm vụ của người dùng.
        """
        safety.reset()
        safety.start_hotkey_listener()

        try:
            self._init_client()
        except Exception as e:
            self.log("ERROR", str(e))
            self.set_status("Lỗi API Key")
            return {"success": False, "error": str(e)}

        self.set_status("Đang khởi động...")
        self.log("INFO", f"Bắt đầu nhiệm vụ: '{goal}'")

        # Lấy thông tin ngữ cảnh ban đầu
        fg_win = controller.get_foreground_window()
        screen_w, screen_h = vision.get_screen_size()
        initial_context = (
            f"MỤC TIÊU CỦA NGƯỜI DÙNG: {goal}\n\n"
            f"Thông tin hệ thống:\n"
            f"- Cửa sổ đang mở: {fg_win.get('title', 'Không xác định')}\n"
            f"- Kích thước màn hình: {screen_w} x {screen_h} pixels.\n"
            f"Hãy bắt đầu suy nghĩ và gọi các công cụ phù hợp nhất để hoàn thành mục tiêu."
        )

        # Cấu hình generate_content với Gemini
        gen_config = types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            temperature=0.2,
            tools=ALL_TOOLS,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)
        )

        # Danh sách mô hình ưu tiên
        fallback_models = [
            "gemini-3.5-flash-lite",
            "gemini-3.1-flash-lite",
            "gemini-3.5-flash",
            "gemini-3.8-flash",
            "gemini-3.7-flash"
        ]

        # Mô hình hiện tại
        current_model = config.gemini_model if config.gemini_model in fallback_models else "gemini-3.5-flash-lite"
        if current_model in fallback_models:
            fallback_models.remove(current_model)
        fallback_models.insert(0, current_model)

        self.log("INFO", f"Mô hình khởi động: {current_model}")

        # Khởi tạo lịch sử cuộc trò chuyện chuẩn xác
        contents: list[types.Content] = [
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=initial_context)]
            )
        ]

        step = 0
        max_steps = config.max_steps
        task_finished = False
        final_summary = ""

        while step < max_steps and not task_finished:
            step += 1
            if safety.is_stopped():
                reason = safety.get_stop_reason()
                self.log("STOP", f"ĐÃ DỪNG KHẨN CẤP: {reason}")
                self.set_status("Đã dừng")
                return {"success": False, "error": reason}

            self.set_status(f"Bước {step}/{max_steps}: Đang suy luận ({current_model})...")
            self.log("STEP", f"=== BƯỚC {step} ===")

            response = None
            candidate_list = [current_model] + [m for m in fallback_models if m != current_model]

            for attempt_model in candidate_list:
                try:
                    response = self.client.models.generate_content(
                        model=attempt_model,
                        contents=contents,
                        config=gen_config
                    )
                    current_model = attempt_model
                    break
                except Exception as e:
                    err_str = str(e)
                    is_quota = "429" in err_str or "quota" in err_str.lower() or "resource_exhausted" in err_str.lower()
                    
                    # Nếu hết quota, thử xoay sang API key khác trước
                    if is_quota and self.rotate_key():
                        try:
                            response = self.client.models.generate_content(
                                model=attempt_model,
                                contents=contents,
                                config=gen_config
                            )
                            current_model = attempt_model
                            break
                        except Exception:
                            pass

                    is_unavailable = "503" in err_str or "unavailable" in err_str.lower()
                    self.log("WARN", f"Mô hình {attempt_model} ({'Hết hạn ngạch 429' if is_quota else 'Bận 503' if is_unavailable else 'Lỗi'}): đang thử mô hình tiếp theo...")
                    time.sleep(1)

            if response is None:
                self.log("ERROR", "Tất cả các mô hình Gemini đều không phản hồi do hết hạn ngạch hoặc bận.")
                self.set_status("Lỗi API/Hết Quota")
                return {"success": False, "error": "Không thể nhận phản hồi từ Gemini API."}

            # Lưu lượt phản hồi của model vào lịch sử hội thoại
            model_content = response.candidates[0].content
            contents.append(model_content)

            # Trích xuất suy nghĩ (Text) từ phản hồi nếu có
            thought_text = ""
            if model_content.parts:
                texts = [p.text for p in model_content.parts if getattr(p, "text", None)]
                if texts:
                    thought_text = "\n".join(texts).strip()
                    self.log("THOUGHT", thought_text)

            # Trích xuất function calls
            function_calls = response.function_calls

            if not function_calls:
                # Nếu không gọi function nào, kiểm tra xem đã báo hoàn thành chưa
                if "hoàn thành" in thought_text.lower() or "đã xong" in thought_text.lower():
                    task_finished = True
                    final_summary = thought_text
                    break
                else:
                    contents.append(
                        types.Content(
                            role="user",
                            parts=[types.Part.from_text(text="Hãy gọi công cụ tiếp theo hoặc gọi finish_task nếu bạn đã làm xong.")]
                        )
                    )
                    continue

            # Thực thi danh sách function calls
            function_response_parts = []
            extra_image_parts = []
            for fc in function_calls:
                fn_name = fc.name
                fn_args = fc.args or {}

                if safety.is_stopped():
                    reason = safety.get_stop_reason()
                    self.log("STOP", f"ĐÃ DỪNG KHẨN CẤP: {reason}")
                    self.set_status("Đã dừng")
                    return {"success": False, "error": reason}

                # Hiển thị hành động ra giao diện
                args_preview = ", ".join(f"{k}='{v}'" if isinstance(v, str) else f"{k}={v}" for k, v in fn_args.items())
                self.log("ACTION", f"⚡ {fn_name}({args_preview})")
                self.set_status(f"Đang thực thi: {fn_name}")

                # Kiểm tra nếu là finish_task
                if fn_name == "finish_task":
                    task_finished = True
                    final_summary = fn_args.get("summary", "Đã hoàn thành nhiệm vụ.")
                    tool_result = f"Nhiệm vụ hoàn thành: {final_summary}"
                elif fn_name == "take_screenshot_to_see":
                    try:
                        img_bytes, screen_w, screen_h = vision.capture_screen_bytes(max_dimension=1280, quality=75)
                        img_part = types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg")
                        extra_image_parts.append(img_part)
                        tool_result = f"Đã chụp ảnh màn hình ({screen_w}x{screen_h} px). Ảnh chụp đã được gửi kèm vào tầm nhìn AI để quan sát trực tiếp các chi tiết và xác định tọa độ thao tác."
                    except Exception as ex:
                        tool_result = f"Lỗi chụp ảnh màn hình: {ex}"
                elif fn_name in TOOL_MAP:
                    try:
                        tool_func = TOOL_MAP[fn_name]
                        tool_result = str(tool_func(**fn_args))
                    except Exception as ex:
                        tool_result = f"Lỗi khi thực thi công cụ {fn_name}: {ex}"
                else:
                    tool_result = f"Lỗi: Không tìm thấy công cụ '{fn_name}'"

                self.log("OBSERVATION", f"👁️ Kết quả: {tool_result}")

                # Đóng gói kết quả trả về
                part = types.Part.from_function_response(
                    name=fn_name,
                    response={"result": tool_result}
                )
                function_response_parts.append(part)

            if task_finished:
                break

            # Đính kèm ảnh màn hình (nếu có yêu cầu chụp) cùng kết quả công cụ
            all_response_parts = function_response_parts + extra_image_parts

            # Thêm lượt trả lời của user vào lịch sử hội thoại
            contents.append(
                types.Content(
                    role="user",
                    parts=all_response_parts
                )
            )

            # Độ trễ giữa các hành động để người dùng kịp quan sát
            time.sleep(config.action_delay)

        if task_finished:
            self.set_status("Hoàn thành xuất sắc!")
            self.log("SUCCESS", f"🎉 {final_summary}")
            return {"success": True, "summary": final_summary}
        else:
            self.set_status("Hết số bước tối đa")
            msg = f"Đã đạt giới hạn {max_steps} bước nhưng chưa hoàn thành toàn bộ."
            self.log("WARN", msg)
            return {"success": False, "error": msg}
