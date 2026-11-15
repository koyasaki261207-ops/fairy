"""
BỘ ĐỊNH TUYẾN LỆNH QUEN THUỘC (0 TOKEN, ~VÀI TRĂM MS)
Nhận ra các yêu cầu đơn giản, có dạng cố định rồi thực thi thẳng bằng code, không gọi AI:
  - "mở notepad", "mở ứng dụng máy tính", "chạy chrome"
  - "mở youtube.com", "vào trang github"
  - "tìm kiếm thời tiết hà nội trên google", "google giá vàng"
  - "tìm file báo cáo", "tìm thư mục KTMT"
Chỉ khớp khi TOÀN BỘ câu lệnh là một yêu cầu đơn giản (neo đầu-cuối). Mọi câu phức tạp hơn
(nhiều vế, "và", "sau đó"...) hoặc không chắc chắn đều trả về None để AI xử lý.
"""

import re
import time
import urllib.parse

from core.controller import controller
from core.guard import _norm
from core.safety import safety

APPS = {
    "notepad": ("notepad", "notepad"),
    "ghi chu": ("notepad", "notepad"),
    "calculator": ("calc", ""), "may tinh": ("calc", ""), "calc": ("calc", ""),
    "paint": ("mspaint", "paint"),
    "word": ("winword", "word"), "excel": ("excel", "excel"), "powerpoint": ("powerpnt", "powerpoint"),
    "chrome": ("chrome", "chrome"), "google chrome": ("chrome", "chrome"),
    "edge": ("msedge", "edge"), "microsoft edge": ("msedge", "edge"), "firefox": ("firefox", "firefox"),
    "file explorer": ("explorer", ""), "explorer": ("explorer", ""), "quan ly tep": ("explorer", ""),
    "cmd": ("cmd", ""), "command prompt": ("cmd", ""), "powershell": ("powershell", "powershell"),
    "task manager": ("taskmgr", "task manager"), "trinh quan ly tac vu": ("taskmgr", ""),
    "snipping tool": ("snippingtool", ""), "cai dat": ("ms-settings:", "settings"), "settings": ("ms-settings:", "settings"),
    "spotify": ("spotify", "spotify"), "zalo": ("zalo", "zalo"), "telegram": ("telegram", "telegram"),
}
SITES = {
    "youtube": "https://www.youtube.com", "google": "https://www.google.com", "facebook": "https://www.facebook.com",
    "gmail": "https://mail.google.com", "github": "https://github.com", "chatgpt": "https://chatgpt.com",
    "claude": "https://claude.ai", "tiktok": "https://www.tiktok.com", "shopee": "https://shopee.vn",
}

_OPEN = r"(?:mo|open|chay|khoi dong|bat|launch|vao|truy cap|go to)"
_FILLER = r"(?:\s+(?:ung dung|app|phan mem|chuong trinh|trang|trang web|website|web))?"
_DOMAIN = re.compile(r"^(?:https?://)?([a-z0-9-]+(?:\.[a-z0-9-]+)+)(/\S*)?$")
_ADV = re.compile(r"\b(va|roi|sau do|then|and|xong|de|rồi)\b")  # có thêm vế phía sau -> để AI xử lý


def _run(cmd: str) -> dict:
    return controller.run_powershell(cmd)


def _open_app(exe: str, window_kw: str) -> dict:
    before = controller.get_foreground_window().get("title", "")
    res = _run(f"Start-Process '{exe}'")
    if not res.get("success"):
        return {"success": False, "error": res.get("error") or res.get("stderr")}
    deadline = time.time() + 6
    while time.time() < deadline:
        if safety.is_stopped():
            return {"success": False, "error": safety.get_stop_reason()}
        title = controller.get_foreground_window().get("title", "")
        if (title and title != before) or (window_kw and controller.wait_for_window(window_kw, 0.2)):
            time.sleep(0.2)
            now = controller.get_foreground_window().get("title", title)
            return {"success": True, "summary": f"Đã mở '{exe}'. Cửa sổ đang focus: {now}"}
        time.sleep(0.1)
    return {"success": False, "error": "chưa thấy cửa sổ xuất hiện"}  # để AI kiểm tra


def try_route(goal: str) -> dict | None:
    """Trả về {success, summary|error} nếu xử lý được, ngược lại None (chuyển cho AI)."""
    text = _norm(goal)
    if not text or len(text) > 90 or _ADV.search(text):
        return None
    # Chỉ dùng độ dài ký tự trùng khớp để cắt tham số từ chuỗi gốc
    same_len = len(text) == len(goal.strip().lower())
    orig = goal.strip().lower() if same_len else ""

    # 1) mở ứng dụng
    m = re.fullmatch(rf"{_OPEN}{_FILLER}\s+(.+)", text)
    if m:
        name = m.group(1).strip()
        if name in APPS:
            exe, kw = APPS[name]
            return _open_app(exe, kw)
        # 2) mở trang web
        site = name.removeprefix("trang ").removeprefix("web ").strip()
        if site in SITES:
            res = _run(f"Start-Process '{SITES[site]}'")
            return {"success": True, "summary": f"Đã mở {SITES[site]}"} if res.get("success") \
                else {"success": False, "error": res.get("error") or res.get("stderr")}
        dm = _DOMAIN.fullmatch(site)
        if dm:
            url = site if site.startswith("http") else f"https://{site}"
            res = _run(f"Start-Process '{url}'")
            return {"success": True, "summary": f"Đã mở {url}"} if res.get("success") \
                else {"success": False, "error": res.get("error") or res.get("stderr")}
        return None

    # 3) tìm kiếm Google
    m = re.fullmatch(r"(?:tim kiem|tra cuu|search|google)\s+(.+?)(?:\s+(?:tren|on)\s+google)?", text)
    if m and orig and not re.search(r"\b(file|tep|thu muc|folder|o dia)\b", text):
        start, end = m.span(1)
        query = orig[start:end].strip()
        if query:
            url = "https://www.google.com/search?q=" + urllib.parse.quote_plus(query)
            res = _run(f"Start-Process '{url}'")
            return {"success": True, "summary": f"Đã mở kết quả tìm kiếm Google cho '{query}'"} if res.get("success") \
                else {"success": False, "error": res.get("error") or res.get("stderr")}
        return None

    # 4) tìm tệp / thư mục
    m = re.fullmatch(r"tim\s+(file|tep|thu muc|folder)\s+(.+)", text)
    if m and orig:
        start, end = m.span(2)
        keyword = orig[start:end].strip().replace("'", "''").replace("*", "")
        if not keyword:
            return None
        kind = "-Directory" if m.group(1) in ("thu muc", "folder") else "-File"
        cmd = (
            f"Get-ChildItem -Path 'D:\\','C:\\Users' -Filter '*{keyword}*' {kind} -Recurse -ErrorAction SilentlyContinue "
            "| Select-Object -First 10 -ExpandProperty FullName"
        )
        res = _run(cmd)
        if res.get("success") and res.get("stdout"):
            return {"success": True, "summary": f"Tìm thấy:\n{res['stdout']}"}
        return None  # không thấy / lỗi -> để AI thử cách khác
    return None
