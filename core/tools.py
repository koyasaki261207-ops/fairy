"""
ĐỊNH NGHĨA CÁC CÔNG CỤ (TOOLS) CHO GEMINI
Bao gồm cả 3 tầng: Lệnh hệ thống, Windows UIAutomation và Thao tác chuột/phím Vision.
"""

import time
from core.controller import controller
from core.context import compact_json, one_line, truncate_text
from core.uiauto import uiauto
from core.safety import safety


def run_powershell(command: str) -> str:
    """
    Chạy lệnh PowerShell trên Windows để mở ứng dụng, quản lý file, thư mục hoặc tải dữ liệu.
    Đây là cách NHANH NHẤT (vài ms).
    Ví dụ: 'Start-Process notepad', 'Get-ChildItem C:\\Users', 'Get-Content test.txt'.
    """
    res = controller.run_powershell(command)
    if not res.get("success"):
        return f"Thất bại: {res.get('error') or res.get('stderr')}"
    out = res.get("stdout", "")
    err = res.get("stderr", "")
    if err:
        out = f"{out}\nSTDERR:\n{truncate_text(err, 800)}".strip()
    return f"Thành công. Kết quả:\n{out}" if out else "Thành công (lệnh không trả về output)."


def ui_click(name: str) -> str:
    """
    Click vào nút bấm, tab, menu hoặc liên kết trên cửa sổ hiện tại dựa theo tên hiển thị.
    Ví dụ: name='Save' hoặc 'Lưu' hoặc 'Search' hoặc 'Close'.
    Phương thức này dùng Windows UIAutomation, cực kỳ chuẩn xác và không sợ lệch độ phân giải.
    """
    res = uiauto.click_element_by_name(name)
    if res.get("success"):
        return f"Thành công: {res.get('action')}"
    return f"Thất bại: {res.get('error')}"


def ui_type(name: str, text: str) -> str:
    """
    Điền văn bản vào một ô nhập liệu (Edit Box) trên cửa sổ hiện tại dựa theo tên nhãn của ô đó.
    Ví dụ: name='Search', text='Tài liệu báo cáo'.
    """
    res = uiauto.type_into_element(name, text)
    if res.get("success"):
        return f"Thành công: {res.get('action')}"
    return f"Thất bại: {res.get('error')}"


import pyautogui

def _normalize_point(x: float, y: float) -> tuple[int, int]:
    """
    Chuyển đổi tọa độ từ thang chuẩn hóa [0 - 1000] của Gemini Vision
    sang tọa độ pixel thực tế của màn hình máy tính (ví dụ 1920x1200).
    Nếu tọa độ truyền vào đã lớn hơn 1000, giữ nguyên pixel thực tế.
    """
    screen_w, screen_h = pyautogui.size()
    if x <= 1000 and y <= 1000 and (screen_w > 1000 or screen_h > 1000):
        actual_x = int((x / 1000.0) * screen_w)
        actual_y = int((y / 1000.0) * screen_h)
    else:
        actual_x = int(x)
        actual_y = int(y)
    actual_x = max(0, min(screen_w - 1, actual_x))
    actual_y = max(0, min(screen_h - 1, actual_y))
    return actual_x, actual_y


def take_screenshot_to_see(reason: str = "") -> str:
    """
    Chụp ảnh màn hình thực tế và truyền trực tiếp vào tầm nhìn (mắt) của AI.
    DÙNG CHO: Nhìn các nút biểu tượng, hình ảnh, thanh trượt slider, giao diện web canvas,
    trình chỉnh sửa ảnh/video, game bài, cờ tướng hoặc bất kỳ giao diện đồ họa nào không có chữ.
    """
    return f"Đã chụp ảnh màn hình để quan sát thị giác: {reason or 'Cập nhật trạng thái hiển thị hiện tại'}"


def mouse_click_coords(x: float, y: float, button: str = "left", clicks: int = 1) -> str:
    """
    Click chuột tại tọa độ trên màn hình.
    HỖ TRỢ TỌA ĐỘ CHUẨN HÓA [0 - 1000] (Khuyên dùng):
    - x: từ 0 (mép trái ngoài cùng màn hình) đến 1000 (mép phải)
    - y: từ 0 (mép trên ngoài cùng màn hình) đến 1000 (mép dưới)
    Hệ thống tự động chuyển đổi sang tọa độ pixel thực tế của máy tính.
    """
    actual_x, actual_y = _normalize_point(x, y)
    ok = controller.mouse_click(actual_x, actual_y, button=button, clicks=clicks)
    if ok:
        return f"Đã click chuột {button} ({clicks} lần) tại tọa độ màn hình ({actual_x}, {actual_y}) [từ input {x}, {y}]."
    return "Không thể click chuột (có thể hệ thống đã bị dừng hoặc gặp lỗi FailSafe)."


def mouse_double_click(x: float, y: float) -> str:
    """
    Nhấp đúp chuột (Double Click) cực nhanh tại tọa độ trên màn hình.
    HỖ TRỢ TỌA ĐỘ CHUẨN HÓA [0 - 1000]:
    - x: từ 0 đến 1000 (mép trái -> mép phải màn hình)
    - y: từ 0 đến 1000 (mép trên -> mép dưới màn hình)
    Dùng để mở tệp tin, kích hoạt đối tượng, tự động đẩy lá bài lên ô đích (trong game bài).
    """
    actual_x, actual_y = _normalize_point(x, y)
    ok = controller.mouse_double_click(actual_x, actual_y)
    if ok:
        return f"Đã nhấp đúp chuột tại tọa độ màn hình ({actual_x}, {actual_y}) [từ input {x}, {y}]."
    return "Thất bại khi nhấp đúp chuột."


def mouse_right_click(x: float, y: float) -> str:
    """
    Nhấp chuột phải (Right Click) tại tọa độ trên màn hình (Hỗ trợ tọa độ chuẩn hóa 0-1000).
    """
    actual_x, actual_y = _normalize_point(x, y)
    ok = controller.mouse_right_click(actual_x, actual_y)
    if ok:
        return f"Đã nhấp chuột phải tại tọa độ màn hình ({actual_x}, {actual_y}) [từ input {x}, {y}]."
    return "Thất bại khi nhấp chuột phải."


# ========================================================
# BỘ THẨM ĐỊNH NƯỚC ĐI GAME BÀI (SOLITAIRE MOVE VALIDATOR)
# ========================================================

_CARD_RANK_MAP = {
    'a': 1, 'ace': 1, 'át': 1, 'at': 1, '1': 1,
    '2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, '9': 9, '10': 10,
    'j': 11, 'jack': 11, 'bồi': 11, 'boi': 11, '11': 11,
    'q': 12, 'queen': 12, 'đầm': 12, 'dam': 12, '12': 12,
    'k': 13, 'king': 13, 'già': 13, 'gia': 13, '13': 13
}

_CARD_SUIT_MAP = {
    'cơ': ('heart', 'red'), 'co': ('heart', 'red'), 'h': ('heart', 'red'), 'heart': ('heart', 'red'), '♥': ('heart', 'red'),
    'rô': ('diamond', 'red'), 'ro': ('diamond', 'red'), 'd': ('diamond', 'red'), 'diamond': ('diamond', 'red'), '♦': ('diamond', 'red'),
    'bích': ('spade', 'black'), 'bich': ('spade', 'black'), 's': ('spade', 'black'), 'spade': ('spade', 'black'), '♠': ('spade', 'black'),
    'tép': ('club', 'black'), 'tep': ('club', 'black'), 'c': ('club', 'black'), 'club': ('club', 'black'), 'chuồn': ('club', 'black'), 'chuon': ('club', 'black'), '♣': ('club', 'black')
}

def _parse_card_spec(s: str):
    if not s:
        return None
    s = s.strip().lower()
    if s in ['empty', 'trống', 'cột trống', 'none', '']:
        return None
    rank = None
    suit = None
    color = None
    if '10' in s:
        rank = 10
    else:
        for r_str, r_val in sorted(_CARD_RANK_MAP.items(), key=lambda x: -len(x[0])):
            if s.startswith(r_str) or f' {r_str}' in s or s.endswith(r_str):
                rank = r_val
                break
    for s_str, (s_name, s_col) in sorted(_CARD_SUIT_MAP.items(), key=lambda x: -len(x[0])):
        if s_str in s:
            suit = s_name
            color = s_col
            break
    return {'rank': rank, 'suit': suit, 'color': color, 'raw': s}


def validate_card_move(source_card: str, target_card: str, destination_type: str = "tableau") -> str:
    """
    Thẩm định và xác minh tính hợp lệ của nước đi bài Solitaire (Klondike) trước khi kéo thả chuột.
    DÙNG KHI CHƠI GAME BÀI ĐỂ TRÁNH ĐI BỪA, ĐI PHẠM LUẬT!
    - source_card: Tên quân bài muốn chuyển (ví dụ: '7 Rô', '7D', '3 Cơ', '10 Bích', 'J Tép', 'K Cơ').
    - target_card: Tên quân bài đích muốn đặt lên (ví dụ: '8 Tép', '4 Tép', hoặc 'empty' nếu là cột trống).
    - destination_type: 'tableau' (ghép vào 7 cột) hoặc 'foundation' (đưa lên 4 ô đích A -> K).
    """
    src = _parse_card_spec(source_card)
    dst = _parse_card_spec(target_card)
    if not src:
        return f"Lỗi: Không nhận diện được lá bài nguồn '{source_card}'."
    r_src = src['rank']
    if not r_src:
        return f"Lỗi: Không xác định được số/rank của lá nguồn '{source_card}'."

    if destination_type.lower() == 'foundation':
        if not dst:
            if r_src == 1:
                return f"✅ HỢP LỆ: Quân Át ({source_card}) được phép đưa lên ô đích trống! Hãy nhấp đúp mouse_double_click."
            return f"❌ PHẠM LUẬT: Ô đích trống chỉ nhận quân Át (A). Lá {source_card} (Rank {r_src}) không thể đưa lên ô trống."
        dst_suit = dst['suit']
        if src['suit'] != dst_suit:
            return f"❌ PHẠM LUẬT: Trên ô đích phải cùng chất ({dst_suit}), lá nguồn là {src['suit']}."
        if r_src != dst['rank'] + 1:
            return f"❌ PHẠM LUẬT: Trên ô đích phải tăng dần đúng 1 nút (cần rank {dst['rank'] + 1}, lá nguồn là {r_src})."
        return f"✅ HỢP LỆ: {source_card} đưa lên ô đích {target_card} thành công!"

    if not dst:
        if r_src == 13:
            return f"✅ HỢP LỆ XUẤT SẮC: Quân K ({source_card}) được phép đặt vào cột trống!"
        return f"❌ PHẠM LUẬT CỘT TRỐNG: Chỉ có duy nhất quân K (King, rank 13) mới được đặt vào cột trống. Lá {source_card} (rank {r_src}) không được phép!"

    errors = []
    r_dst = dst['rank']
    if r_src != r_dst - 1:
        if r_src > r_dst:
            errors.append(f"Sai thứ tự: Lá nguồn {source_card} (rank {r_src}) LỚN HƠN lá đích {target_card} (rank {r_dst})! Phải đặt số nhỏ hơn 1 nút lên số lớn hơn (Ví dụ {r_dst} lên {r_dst+1}, KHÔNG ĐƯỢC kéo {r_src} lên {r_dst}).")
        else:
            errors.append(f"Sai thứ tự: Lá nguồn {source_card} (rank {r_src}) không nhỏ hơn lá đích {target_card} (rank {r_dst}) đúng 1 nút (cần rank {r_dst - 1}).")

    if src['color'] and dst['color'] and src['color'] == dst['color']:
        col_vn = "ĐEN" if src['color'] == 'black' else "ĐỎ"
        errors.append(f"Sai màu sắc: Cả 2 lá đều màu {col_vn}! Luật Klondike bắt buộc xen kẽ màu: ĐEN lên ĐỎ hoặc ĐỎ lên ĐEN.")

    if errors:
        return "❌ NƯỚC ĐI HOÀN TOÀN KHÔNG HỢP LỆ (BỊ TỪ CHỐI THAO TÁC):\n" + "\n".join(f"- {e}" for e in errors)
    
    return f"✅ NƯỚC ĐI HỢP LỆ XUẤT SẮC: {source_card} (Rank {r_src}, {src['color']}) đặt lên {target_card} (Rank {r_dst}, {dst['color']}). Hãy dùng mouse_drag_and_drop để kéo!"


def mouse_drag_and_drop(start_x: float, start_y: float, end_x: float, end_y: float, duration: float = 0.5, source_card: str = "", target_card: str = "") -> str:
    """
    Kéo thả chuột từ (start_x, start_y) tới (end_x, end_y).
    HỖ TRỢ TỌA ĐỘ CHUẨN HÓA [0 - 1000]:
    - start_x, start_y: Tọa độ bắt đầu kéo (0-1000)
    - end_x, end_y: Tọa độ thả chuột (0-1000)
    - source_card, target_card (Tùy chọn): Nếu đang chơi game bài Solitaire, hãy truyền tên 2 lá bài để hệ thống tự động kiểm định luật trước khi kéo. Nếu phạm luật sẽ tự động chặn kéo bừa!
    Dùng để di chuyển tệp tin, kéo thanh trượt (slider), kéo lá bài/quân cờ,
    vẽ đường thẳng/hình khối trên canvas, hoặc bôi đen văn bản/vùng chọn.
    """
    if source_card and target_card:
        val_res = validate_card_move(source_card, target_card)
        if "❌" in val_res or "Lỗi" in val_res:
            return f"TỪ CHỐI KÉO THẢ VÌ PHẠM LUẬT:\n{val_res}\nHãy quan sát lại bàn cờ và tìm nước đi hợp lệ!"

    actual_start_x, actual_start_y = _normalize_point(start_x, start_y)
    actual_end_x, actual_end_y = _normalize_point(end_x, end_y)
    ok = controller.mouse_drag(actual_start_x, actual_start_y, actual_end_x, actual_end_y, duration=duration)
    if ok:
        card_info = f" ({source_card} -> {target_card})" if source_card and target_card else ""
        return f"Đã kéo thả chuột{card_info} từ ({actual_start_x}, {actual_start_y}) tới ({actual_end_x}, {actual_end_y})."
    return "Thất bại khi kéo thả chuột."


TABLEAU_COL_CENTERS = {
    1: 247,
    2: 330,
    3: 415,
    4: 500,
    5: 585,
    6: 670,
    7: 755
}


def solitaire_move_by_column(from_col: int, to_col: int, source_card: str = "", target_card: str = "", from_y: float = 0, to_y: float = 0) -> str:
    """
    Di chuyển lá bài trong game Solitaire chuẩn xác 100% theo số thứ tự cột (Cột 1 đến Cột 7).
    TỰ ĐỘNG CĂN TỌA ĐỘ VÀ KIỂM ĐỊNH LUẬT BÀI TRÁNH SAI LỆCH!
    
    Quy ước cột:
    - from_col:
      * 1 đến 7: Cột 1 đến Cột 7 trên bàn bài.
      * 0: Chồng bài lật (Waste pile ở góc trên bên trái).
    - to_col:
      * 1 đến 7: Cột 1 đến Cột 7 trên bàn bài.
      * 8: Bốn ô đích (Foundations ở góc trên bên phải).
    - source_card: Tên lá bài chuyển đi (ví dụ: '7 Rô', '3 Cơ').
    - target_card: Tên lá bài đích (ví dụ: '8 Tép', '4 Tép', hoặc 'empty' nếu chuyển vào cột trống).
    """
    if source_card and target_card:
        dest_type = "foundation" if to_col == 8 else "tableau"
        val_res = validate_card_move(source_card, target_card, destination_type=dest_type)
        if "❌" in val_res or "Lỗi" in val_res:
            return f"TỪ CHỐI DI CHUYỂN BÀI VÌ PHẠM LUẬT:\n{val_res}\nHãy quan sát lại bàn cờ và chọn nước đi hợp lệ!"

    # Tính tọa độ X, Y chuẩn hóa
    if from_col == 0:
        start_x = 335.0  # Waste pile
        start_y = from_y if from_y > 0 else 200.0
    elif 1 <= from_col <= 7:
        start_x = float(TABLEAU_COL_CENTERS[from_col])
        # Tọa độ Y nguồn: mặc định 415.0 nằm ở lá gốc của phần bài ngửa (cho phép bốc cả cụm/dây bài đi cùng)
        start_y = from_y if from_y > 0 else 415.0
    else:
        return f"Lỗi: Cột nguồn from_col={from_col} không hợp lệ (chỉ nhận 0..7)."

    if to_col == 8:
        end_x = 585.0  # Foundations
        end_y = to_y if to_y > 0 else 200.0
    elif 1 <= to_col <= 7:
        end_x = float(TABLEAU_COL_CENTERS[to_col])
        # Tọa độ Y đích: 490.0 nằm ở phần lá bài đón nhận tại cột đích
        end_y = to_y if to_y > 0 else 490.0
    else:
        return f"Lỗi: Cột đích to_col={to_col} không hợp lệ (chỉ nhận 1..8)."

    actual_start_x, actual_start_y = _normalize_point(start_x, start_y)
    actual_end_x, actual_end_y = _normalize_point(end_x, end_y)
    ok = controller.mouse_drag(actual_start_x, actual_start_y, actual_end_x, actual_end_y, duration=0.4)
    if ok:
        src_name = source_card or f"Cột {from_col}"
        dst_name = target_card or f"Cột {to_col}"
        return f"Đã di chuyển thành công '{src_name}' (Cột {from_col}) sang '{dst_name}' (Cột {to_col}) tại pixel ({actual_start_x}, {actual_start_y}) -> ({actual_end_x}, {actual_end_y})."
    return "Thất bại khi thao tác chuột di chuyển bài."


def solitaire_draw_card() -> str:
    """
    Rút lật lá bài mới từ Chồng bài úp (Stockpile ở góc trên bên trái).
    CHỈ DÙNG KHI CẢ 7 CỘT KHÔNG CÒN NƯỚC ĐI NÀO HỢP LỆ!
    """
    actual_x, actual_y = _normalize_point(247, 200)
    ok = controller.mouse_click(actual_x, actual_y)
    if ok:
        return f"Đã click rút lật bài mới từ Chồng bài úp (Stockpile) tại tọa độ ({actual_x}, {actual_y})."
    return "Thất bại khi click rút bài."


def mouse_hover(x: float, y: float) -> str:
    """
    Rê chuột lơ lửng tại tọa độ trên màn hình (Hỗ trợ tọa độ chuẩn hóa 0-1000).
    """
    actual_x, actual_y = _normalize_point(x, y)
    ok = controller.mouse_move(actual_x, actual_y)
    if ok:
        return f"Đã di chuột đến tọa độ màn hình ({actual_x}, {actual_y}) [từ input {x}, {y}]."
    return "Thất bại khi di chuột."


def type_vietnamese_text(text: str) -> str:
    """
    Gõ văn bản bất kỳ vào vị trí con trỏ hiện tại.
    Hỗ trợ 100% tiếng Việt có dấu, emoji, ký tự đặc biệt, không bao giờ bị lỗi bộ gõ.
    """
    ok = controller.type_text(text)
    if ok:
        return f"Đã gõ {len(text)} ký tự: '{one_line(text, 80)}'"
    return "Thất bại khi gõ văn bản."


def keyboard_shortcut(keys: str) -> str:
    """
    Nhấn tổ hợp phím tắt trên bàn phím.
    Các phím phân tách nhau bằng dấu cộng '+'.
    Ví dụ: 'ctrl+s' (lưu file), 'win+r' (mở hộp thoại Run), 'alt+tab' (đổi cửa sổ), 'ctrl+a', 'enter', 'esc'.
    """
    key_list = [k.strip().lower() for k in keys.split("+") if k.strip()]
    if not key_list:
        return "Lỗi: Danh sách phím trống."
    ok = controller.hotkey(*key_list)
    if ok:
        return f"Đã nhấn tổ hợp phím: {' + '.join(key_list)}"
    return "Thất bại khi nhấn phím."


def mouse_scroll_page(clicks: int) -> str:
    """
    Cuộn chuột trên trang hiện tại.
    clicks > 0: Cuộn lên.
    clicks < 0: Cuộn xuống (ví dụ: clicks=-5 để cuộn xuống 5 nấc).
    """
    ok = controller.mouse_scroll(clicks)
    if ok:
        direction = "lên" if clicks > 0 else "xuống"
        return f"Đã cuộn trang {direction} ({abs(clicks)} nấc)."
    return "Thất bại khi cuộn trang."


def inspect_active_window() -> str:
    """
    Lấy thông tin chi tiết về cửa sổ đang mở hiện tại và danh sách các nút bấm / ô nhập liệu.
    Dùng để 'quan sát' trước khi quyết định click vào đâu.
    """
    fg = controller.get_foreground_window()
    elements = uiauto.get_active_window_elements(max_elements=30)
    summary = {
        "active_window_title": fg.get("title", "Unknown"),
        "interactive_elements_count": len(elements),
        "sample_elements": elements[:15]
    }
    return compact_json(summary)


def wait_seconds(seconds: float) -> str:
    """
    Tạm dừng một khoảng thời gian ngắn (tối đa 10s) để chờ ứng dụng hoặc trang web tải xong.
    """
    sec = min(max(0.1, seconds), 10.0)
    time.sleep(sec)
    return f"Đã chờ {sec} giây."


def read_file_content(file_path: str, max_chars: int = 5000) -> str:
    """
    Đọc và trích xuất nội dung từ một tệp tin trên máy tính.
    Hỗ trợ tệp văn bản (txt, py, json, md, log, csv...), tệp PDF (trích xuất chữ) và tệp Word (.docx).
    Dùng để phân tích, tóm tắt tài liệu hoặc tìm nội dung cốt lõi.
    """
    from pathlib import Path
    p = Path(file_path.strip().strip('"').strip("'"))
    if not p.exists():
        return f"Lỗi: Không tìm thấy tệp tại đường dẫn '{file_path}'"

    ext = p.suffix.lower()
    content = ""

    try:
        if ext == ".pdf":
            from pypdf import PdfReader
            reader = PdfReader(str(p))
            extracted_pages = []
            for i, page in enumerate(reader.pages[:15]):  # Đọc tối đa 15 trang đầu
                t = page.extract_text() or ""
                if t.strip():
                    extracted_pages.append(f"--- TRANG {i+1} ---\n{t.strip()}")
            content = "\n\n".join(extracted_pages)
        elif ext == ".docx":
            import docx
            doc = docx.Document(str(p))
            paras = [para.text for para in doc.paragraphs if para.text.strip()]
            content = "\n".join(paras)
        else:
            # Tệp text thông thường
            with open(p, "r", encoding="utf-8", errors="replace") as f:
                content = f.read(max_chars * 2)
    except Exception as e:
        return f"Lỗi khi đọc tệp '{file_path}': {e}"

    if not content:
        return f"Tệp '{p.name}' rỗng hoặc không trích xuất được văn bản."

    if len(content) > max_chars:
        content = content[:max_chars] + f"\n\n...[Nội dung còn lại đã được cắt bớt vì vượt quá {max_chars} ký tự]"

    return f"Nội dung tệp '{p.name}':\n\n{content}"


def run_python_code(code: str) -> str:
    """
    Code Interpreter: Tự động chạy đoạn mã Python trực tiếp trên máy tính.
    DÙNG ĐỂ: Giải toán phức tạp, xử lý dữ liệu lớn, phân tích thuật toán game, xử lý ảnh,
    hoặc thực hiện bất kỳ phép biến đổi logic nào đòi hỏi độ chính xác tuyệt đối 100%.
    Được trang bị đầy đủ các thư viện: math, json, re, PIL, pypdf, docx, uiautomation, requests...
    """
    import sys
    import subprocess
    
    if safety.is_stopped():
        return f"Thất bại: {safety.get_stop_reason()}"
        
    if "pyautogui" in code:
        return (
            "Lỗi: Không được gọi trực tiếp thư viện pyautogui trong run_python_code vì sẽ gây sai lệch tọa độ hiển thị! "
            "Hãy gọi các công cụ chuột có sẵn: mouse_click_coords, mouse_double_click, mouse_drag_and_drop hoặc solitaire_move_by_column. "
            "Các công cụ này đã được tích hợp sẵn bộ chuẩn hóa tọa độ màn hình và đảm bảo kích hoạt đúng cửa sổ ứng dụng."
        )
        
    try:
        process = subprocess.Popen(
            [sys.executable, "-c", code],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace"
        )
        stdout, stderr = process.communicate(timeout=30)
        ret_code = process.returncode
        
        output = []
        if stdout.strip():
            output.append(f"STDOUT:\n{stdout.strip()}")
        if stderr.strip():
            output.append(f"STDERR:\n{stderr.strip()}")
            
        res_str = "\n".join(output) if output else "Chạy thành công (không có output)."
        if len(res_str) > 3000:
            res_str = res_str[:3000] + "\n...[Nội dung còn lại đã được cắt ngắn]"
            
        status = "Thành công" if ret_code == 0 else f"Lỗi (Mã lỗi {ret_code})"
        return f"[{status}]\n{res_str}"
    except subprocess.TimeoutExpired:
        process.kill()
        return "Lỗi: Đoạn mã Python chạy quá 30 giây (Timeout)."
    except Exception as e:
        return f"Lỗi khi thực thi Python: {e}"


def list_skills() -> str:
    """
    Liệt kê danh sách tất cả các kỹ năng / cẩm nang chuyên sâu đã được lưu trong hệ thống.
    Dùng để tra cứu trước khi bắt tay vào các nhiệm vụ phức tạp (như game bài, xử lý tệp, web...).
    """
    from pathlib import Path
    skills_dir = Path(__file__).resolve().parent.parent / "skills"
    if not skills_dir.exists():
        return "Chưa có kỹ năng nào được lưu."
        
    skills = list(skills_dir.glob("*.md")) + list(skills_dir.glob("*.py"))
    if not skills:
        return "Thư mục skills trống."
        
    res = [f"Danh sách {len(skills)} kỹ năng có sẵn:"]
    for s in skills:
        res.append(f"- {s.stem} ({s.suffix})")
    return "\n".join(res)


def load_skill(skill_name: str) -> str:
    """
    Tải và đọc nội dung của một kỹ năng / cẩm nang đã lưu trong hệ thống theo tên.
    Ví dụ: skill_name='solitaire_rules' hoặc 'document_batch_processor'.
    """
    from pathlib import Path
    skills_dir = Path(__file__).resolve().parent.parent / "skills"
    
    clean_name = skill_name.strip().replace(".md", "").replace(".py", "")
    target = skills_dir / f"{clean_name}.md"
    if not target.exists():
        target = skills_dir / f"{clean_name}.py"
        
    if not target.exists():
        return f"Không tìm thấy kỹ năng '{skill_name}'. Hãy gọi list_skills để xem danh sách."
        
    try:
        with open(target, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        return f"Nội dung kỹ năng '{target.name}':\n\n{content}"
    except Exception as e:
        return f"Lỗi khi đọc kỹ năng: {e}"


def save_skill(skill_name: str, content: str) -> str:
    """
    Tự học & Lưu kỹ năng mới vào hệ thống:
    Khi bạn tìm ra một giải pháp xuất sắc, một quy trình chuẩn hoặc một đoạn mã mẫu giải quyết bài toán khó,
    hãy gọi hàm này để lưu lại. Lần sau gặp bài toán tương tự, bạn có thể tái sử dụng ngay lập tức!
    """
    from pathlib import Path
    skills_dir = Path(__file__).resolve().parent.parent / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)
    
    clean_name = skill_name.strip().replace(".md", "").replace(".py", "").replace(" ", "_")
    target = skills_dir / f"{clean_name}.md"
    
    try:
        with open(target, "w", encoding="utf-8") as f:
            f.write(content.strip())
        return f"Đã lưu kỹ năng '{clean_name}.md' thành công vào kho tri thức của hệ thống!"
    except Exception as e:
        return f"Lỗi khi lưu kỹ năng: {e}"


from core.agent_desktop import agent_desktop


_snapshot_cache: dict = {}


def reset_run_state():
    """Xóa trạng thái theo từng lượt chạy (gọi ở đầu mỗi nhiệm vụ)."""
    _snapshot_cache.clear()


def desktop_snapshot(app_name: str = "") -> str:
    """
    Chụp cây Accessibility của ứng dụng (agent-desktop): JSON gọn liệt kê các phần tử tương tác
    (Button, Edit, Menu, Tab...) kèm mã @ref (ví dụ @s8f3k2p9:e5). Rẻ hơn nhiều so với ảnh chụp màn hình.
    Dùng @ref nhận được cho desktop_click / desktop_type.
    """
    res = agent_desktop.snapshot(app=app_name, interactive_only=True, compact=True)
    if not res.get("ok"):
        return f"Snapshot thất bại: {res.get('error') or res.get('raw_stderr') or 'Lỗi không xác định'}"
    payload = compact_json(res.get("data", {}))
    key = app_name or "*"
    prev = _snapshot_cache.get(key)
    _snapshot_cache[key] = payload
    if prev == payload:
        return (
            "Giao diện KHÔNG thay đổi so với snapshot trước (các @ref cũ vẫn hợp lệ). "
            "Hành động vừa rồi có thể chưa có tác dụng - hãy thử cách khác hoặc xác nhận bằng ảnh chụp."
        )
    return payload


def update_memory(notes: str) -> str:
    """
    Ghi đè sổ nhớ làm việc (tối đa ~800 ký tự): mục tiêu con, tiến độ, đường dẫn/giá trị quan trọng,
    trạng thái màn hình. Sổ luôn được đính vào lượt mới nhất và không bị lược bỏ như ảnh/kết quả cũ.
    """
    return "Đã ghi nhớ."


def desktop_click(ref_id: str) -> str:
    """
    Click trực tiếp vào một phần tử giao diện bằng mã @ref ID độc nhất (từ desktop_snapshot).
    Ví dụ: ref_id='@s8f3k2p9:e8'.
    Thao tác thực hiện qua API ngữ nghĩa, không di chuyển chuột vật lý của người dùng, chuẩn xác 100%!
    """
    res = agent_desktop.click(ref_id, headed=False)
    if res.get("ok"):
        return f"Thành công: Đã click vào phần tử '{ref_id}'."
    # Nếu headless thất bại, thử chế độ headed
    res_headed = agent_desktop.click(ref_id, headed=True)
    if res_headed.get("ok"):
        return f"Thành công (headed): Đã click vào phần tử '{ref_id}'."
    return f"Thất bại khi click '{ref_id}': {res.get('error') or res_headed.get('error')}"


def desktop_type(ref_id: str, text: str) -> str:
    """
    Nhập văn bản vào một ô nhập liệu bằng mã @ref ID độc nhất (từ desktop_snapshot).
    Ví dụ: ref_id='@s8f3k2p9:e3', text='Báo cáo công việc'.
    """
    res = agent_desktop.type_text(ref_id, text)
    if res.get("ok"):
        return f"Thành công: Đã nhập {len(text)} ký tự vào phần tử '{ref_id}'."
    return f"Thất bại khi nhập văn bản: {res.get('error')}"


def desktop_find(app_name: str, query: str = "", role: str = "") -> str:
    """
    Tìm kiếm nhanh phần tử giao diện trong một ứng dụng dựa theo tên văn bản hiển thị hoặc role (button, edit, tab...).
    Ví dụ: app_name='Notepad', query='Save' hoặc role='button'.
    """
    res = agent_desktop.find_elements(app=app_name, query=query, role=role)
    if not res.get("ok"):
        return f"Không tìm thấy phần tử: {res.get('error')}"
    return compact_json(res.get("data", {}))


def desktop_focus_window(app_name: str) -> str:
    """
    Kích hoạt và đưa cửa sổ ứng dụng lên trên cùng màn hình bằng Vercel agent-desktop.
    Ví dụ: app_name='Notepad' hoặc 'Solitaire' hoặc 'Chrome'.
    """
    res = agent_desktop.focus_window(app_name)
    if res.get("ok"):
        return f"Đã kích hoạt và đưa cửa sổ '{app_name}' lên trước."
    return f"Không thể focus cửa sổ '{app_name}': {res.get('error')}"


def finish_task(summary: str, is_success: bool = True) -> str:
    """
    Báo cáo hoàn thành nhiệm vụ và tóm tắt kết quả chi tiết cho người dùng.
    Gọi hàm này khi bạn đã thực hiện xong toàn bộ yêu cầu.
    """
    status = "Thành công mỹ mãn" if is_success else "Kết thúc với cảnh báo"
    return f"[HOÀN THÀNH - {status}]: {summary}"


# Danh sách các tools cung cấp cho Gemini
ALL_TOOLS = [
    run_python_code,
    list_skills,
    load_skill,
    save_skill,
    desktop_snapshot,
    update_memory,
    desktop_click,
    desktop_type,
    desktop_find,
    desktop_focus_window,
    take_screenshot_to_see,
    mouse_click_coords,
    mouse_double_click,
    mouse_right_click,
    mouse_drag_and_drop,
    solitaire_move_by_column,
    solitaire_draw_card,
    validate_card_move,
    mouse_hover,
    mouse_scroll_page,
    type_vietnamese_text,
    keyboard_shortcut,
    run_powershell,
    read_file_content,
    ui_click,
    ui_type,
    inspect_active_window,
    wait_seconds,
    finish_task
]

# Ánh xạ tên hàm -> hàm thực thi
TOOL_MAP = {func.__name__: func for func in ALL_TOOLS}


# ========================================================
# BỘ ĐIỀU PHỐI CÔNG CỤ DÙNG CHUNG CHO MỌI "BỘ NÃO" (GEMINI / CLAUDE)
# ========================================================

class ToolOutcome:
    __slots__ = ("text", "image", "finished", "summary")

    def __init__(self, text: str, image: bytes | None = None, finished: bool = False, summary: str = ""):
        self.text = text
        self.image = image
        self.finished = finished
        self.summary = summary


def dispatch_tool(fn_name: str, fn_args: dict, max_chars: int = 4000, guard=None) -> ToolOutcome:
    """
    Thực thi 1 lệnh gọi công cụ và chuẩn hóa kết quả (đã cắt gọn) để gửi lại cho AI.
    `guard` (core.guard.RunGuard) bổ sung: sổ nhớ, cổng xác minh khi kết thúc, cảnh báo vòng lặp.
    """
    fn_args = dict(fn_args or {})
    if fn_name == "finish_task":
        if guard is not None and fn_args.get("is_success", True):
            bounce = guard.check_finish()
            if bounce:
                return ToolOutcome(bounce)
        summary = fn_args.get("summary") or "Đã hoàn thành nhiệm vụ."
        return ToolOutcome(f"Nhiệm vụ hoàn thành: {summary}", finished=True, summary=summary)

    if fn_name == "update_memory" and guard is not None:
        return ToolOutcome(guard.set_notes(str(fn_args.get("notes", ""))))

    image = None
    if fn_name == "take_screenshot_to_see":
        try:
            from core.vision import vision
            img_bytes, sw, sh = vision.capture_screen_bytes()
            result = f"Đã chụp màn hình ({sw}x{sh} px), ảnh đính kèm. Tọa độ dùng thang chuẩn hóa 0-1000."
            image = img_bytes
        except Exception as ex:
            result = f"Lỗi chụp ảnh màn hình: {ex}"
    else:
        func = TOOL_MAP.get(fn_name)
        if func is None:
            return ToolOutcome(f"Lỗi: Không tìm thấy công cụ '{fn_name}'")
        try:
            result = str(func(**fn_args))
        except TypeError as ex:
            result = f"Lỗi tham số khi gọi {fn_name}: {ex}"
        except Exception as ex:
            result = f"Lỗi khi thực thi công cụ {fn_name}: {ex}"

    result = truncate_text(result, max_chars)
    if guard is not None:
        hint = guard.observe(fn_name, fn_args, result)
        if hint:
            result = f"{result}\n{hint}"
    return ToolOutcome(result, image=image)
