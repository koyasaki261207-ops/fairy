"""
CÔNG CỤ MỞ RỘNG: GỘP BƯỚC, SNAPSHOT GỌN/DIFF, ĐÁNH SỐ PHẦN TỬ, KỸ NĂNG CHẠY ĐƯỢC
Mục tiêu: mỗi lượt AI làm được nhiều việc hơn và nhận về ít token hơn.

- desktop_snapshot: định dạng dòng gọn `e12 button "Lưu"` (~70% nhỏ hơn JSON thô) + chỉ báo thay đổi so với lần trước.
- write_text_file / open_app_and_wait / run_actions: gộp nhiều bước thành 1 lệnh gọi.
- click_mark: bấm theo số đánh trên ảnh chụp (Set-of-Mark) thay vì đoán tọa độ.
- run_skill: chạy kỹ năng dạng script (skills/*.py) bằng 1 lệnh.
- solitaire_best_move: code tính nước đi, AI chỉ đọc trạng thái bàn bài.
"""

import json
import os
import re
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

from config import config
from core.agent_desktop import agent_desktop
from core.checks import _path as expand_path
from core.context import one_line, truncate_text
from core.controller import controller
from core.safety import safety

ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = ROOT / "skills"

# ----------------------------------------------------------------------
# Trạng thái theo từng lượt chạy
# ----------------------------------------------------------------------
_prev_sigs: dict = {}      # khóa ứng dụng -> Counter chữ ký phần tử của snapshot gần nhất
_base_snap: dict = {}      # khóa ứng dụng -> snapshot_id của lần liệt kê ĐẦY ĐỦ gần nhất
_last_base = {"id": ""}    # snapshot_id đầy đủ gần nhất (để giải mã ref rút gọn eN)
_marks: dict = {}          # số -> thông tin phần tử đã đánh số trên ảnh chụp gần nhất
_pref = {"headed": 0}      # số lần click nền thất bại phải dùng chế độ headed


def reset_state():
    _prev_sigs.clear()
    _base_snap.clear()
    _last_base["id"] = ""
    _marks.clear()
    _pref["headed"] = 0


# ----------------------------------------------------------------------
# Snapshot gọn + diff
# ----------------------------------------------------------------------
_IGNORED_STATES = {"offscreen", "enabled", "visible"}


def _walk(node, out):
    if not isinstance(node, dict):
        return
    if node.get("ref_id"):
        out.append(node)
    for child in node.get("children", []) or []:
        _walk(child, out)


def _entry(node) -> dict:
    states = [s for s in (node.get("states") or []) if s not in _IGNORED_STATES]
    return {
        "ref": node["ref_id"],
        "short": node["ref_id"].split(":")[-1],
        "role": node.get("role", "?"),
        "name": one_line(node.get("name") or "", 60),
        "value": one_line(str(node.get("value") or ""), 60),
        "states": states,
        "bounds": node.get("bounds"),
    }


def _sig(e) -> tuple:
    return e["role"], e["name"], e["value"]


def _fmt(e, full: bool) -> str:
    s = f'{e["ref"] if full else e["short"]} {e["role"]}'
    if e["name"]:
        s += f' "{e["name"]}"'
    if e["value"] and e["value"] != e["name"]:
        s += f' ={e["value"]}'
    if e["states"]:
        s += " [" + ",".join(e["states"]) + "]"
    return s


def desktop_snapshot(app_name: str = "") -> str:
    """
    Chụp cây Accessibility của ứng dụng (agent-desktop): danh sách dòng gọn `eN role "tên" =giá_trị`.
    Dùng mã eN (hoặc @ref đầy đủ) cho desktop_click / desktop_type. Bỏ trống app_name = cửa sổ đang focus.
    Lần gọi sau chỉ trả về phần thay đổi; báo "KHÔNG thay đổi" nếu giao diện y nguyên.
    """
    res = agent_desktop.snapshot(app=app_name, interactive_only=True, compact=True)
    if not res.get("ok"):
        err = res.get("error")
        if isinstance(err, dict):
            err = err.get("message")
        return f"Snapshot thất bại: {err or res.get('raw_stderr') or 'Lỗi không xác định'}"

    data = res.get("data", {})
    els = []
    _walk(data.get("tree"), els)
    entries = [_entry(n) for n in els]
    cur = Counter(_sig(e) for e in entries)
    key = (app_name or "*").lower()
    snap_id = data.get("snapshot_id", "")
    prev = _prev_sigs.get(key)
    _prev_sigs[key] = cur

    if prev is not None and prev == cur:
        return (
            "Giao diện KHÔNG thay đổi so với snapshot trước (các @ref cũ vẫn hợp lệ). "
            "Hành động vừa rồi có thể chưa có tác dụng - hãy thử cách khác hoặc xác nhận bằng ảnh chụp."
        )

    if prev is not None:
        added, removed = cur - prev, prev - cur
        if len(added) + len(removed) <= max(6, int(0.4 * len(entries))):
            lines = ["# THAY ĐỔI so với snapshot trước (eN/@ref cũ của phần tử không đổi vẫn dùng được)"]
            pool = Counter(added)
            for e in entries:
                if pool[_sig(e)] > 0:
                    pool[_sig(e)] -= 1
                    lines.append("+ " + _fmt(e, full=True))
            for (role, name, value), n in removed.items():
                lines.extend([f'- {role} "{name}"' + (f" ={value}" if value else "")] * n)
            return "\n".join(lines)

    _base_snap[key] = snap_id
    _last_base["id"] = snap_id
    win = (data.get("window") or {}).get("title", "")
    header = f'# @{snap_id.lstrip("@")} app={data.get("app", "")} cửa sổ="{one_line(win, 60)}" ({len(entries)} phần tử)'
    return "\n".join([header] + [_fmt(e, full=False) for e in entries])


def resolve_ref(ref_id: str) -> str:
    """'e12' / '@e12' -> '@<snapshot_id>:e12' dựa trên lần liệt kê đầy đủ gần nhất."""
    r = (ref_id or "").strip()
    if r.startswith("@") and ":" in r:
        return r
    m = re.fullmatch(r"@?(e\d+)", r)
    if m and _last_base["id"]:
        return f'@{_last_base["id"].lstrip("@")}:{m.group(1)}'
    return r


def desktop_click(ref_id: str) -> str:
    """
    Click một phần tử bằng mã eN (hoặc @ref đầy đủ) từ desktop_snapshot, qua Accessibility API
    (không di chuyển chuột thật nếu không cần).
    """
    ref = resolve_ref(ref_id)
    first_headed = _pref["headed"] >= 2
    res = agent_desktop.click(ref, headed=first_headed)
    if res.get("ok"):
        return f"Thành công: Đã click '{ref_id}'."
    if not first_headed:
        res_h = agent_desktop.click(ref, headed=True)
        if res_h.get("ok"):
            _pref["headed"] += 1
            return f"Thành công (headed): Đã click '{ref_id}'."
    err = res.get("error")
    if isinstance(err, dict):
        err = err.get("message")
    return f"Thất bại khi click '{ref_id}': {err}"


def desktop_type(ref_id: str, text: str) -> str:
    """Nhập văn bản vào ô nhập bằng mã eN (hoặc @ref đầy đủ) từ desktop_snapshot."""
    res = agent_desktop.type_text(resolve_ref(ref_id), text)
    if res.get("ok"):
        return f"Thành công: Đã nhập {len(text)} ký tự vào '{ref_id}'."
    err = res.get("error")
    if isinstance(err, dict):
        err = err.get("message")
    return f"Thất bại khi nhập văn bản: {err}"


# ----------------------------------------------------------------------
# Đánh số phần tử (Set-of-Mark)
# ----------------------------------------------------------------------
_MARK_ROLES = {
    "button", "link", "menuitem", "tab", "tabitem", "checkbox", "radiobutton", "edit", "textfield", "textbox",
    "combobox", "listitem", "treeitem", "hyperlink", "splitbutton", "slider", "searchbox", "switch", "menu",
}


def capture_marks(max_marks: int = 50) -> list[dict]:
    """Lấy các phần tử tương tác của cửa sổ đang focus (kèm khung hình chữ nhật) và đánh số 1..N."""
    _marks.clear()
    res = agent_desktop.snapshot(app="", interactive_only=True, compact=True)
    if not res.get("ok"):
        return []
    els = []
    _walk((res.get("data") or {}).get("tree"), els)
    out, seen = [], set()
    for node in els:
        b = node.get("bounds") or {}
        w, h = b.get("width", 0), b.get("height", 0)
        role = str(node.get("role", "")).lower()
        if w < 6 or h < 6 or (b.get("x", 0) + w) <= 0 or (b.get("y", 0) + h) <= 0:
            continue
        if role not in _MARK_ROLES and not node.get("name"):
            continue
        box = (round(b["x"]), round(b["y"]), round(w), round(h))
        if box in seen:
            continue
        seen.add(box)
        n = len(out) + 1
        item = {
            "n": n, "ref": node["ref_id"], "role": role, "name": one_line(node.get("name") or "", 40),
            "x": box[0], "y": box[1], "w": box[2], "h": box[3],
            "cx": box[0] + box[2] // 2, "cy": box[1] + box[3] // 2,
        }
        out.append(item)
        _marks[n] = item
        if n >= max_marks:
            break
    return out


def click_mark(number: int, double: bool = False) -> str:
    """
    Click phần tử theo SỐ đã đánh trên ảnh chụp gần nhất (gọi take_screenshot_to_see(marks=true) trước).
    Chính xác hơn đoán tọa độ. double=true để nhấp đúp.
    """
    try:
        n = int(number)
    except (TypeError, ValueError):
        return f"Lỗi: số '{number}' không hợp lệ."
    m = _marks.get(n)
    if not m:
        return f"Lỗi: chưa có phần tử #{n}. Hãy gọi take_screenshot_to_see(marks=true) để đánh số lại."
    label = f'#{n} {m["role"]} "{m["name"]}"'
    if not double:
        res = agent_desktop.click(m["ref"], headed=False)
        if res.get("ok"):
            return f"Đã click {label}."
    ok = controller.mouse_double_click(m["cx"], m["cy"]) if double else controller.mouse_click(m["cx"], m["cy"])
    if ok:
        return f"Đã {'nhấp đúp' if double else 'click'} {label} tại ({m['cx']}, {m['cy']})."
    return f"Thất bại khi click {label} (giao diện có thể đã đổi - chụp lại để đánh số mới)."


def marks_legend(marks: list[dict], limit: int = 40) -> str:
    return "; ".join(f'{m["n"]}={m["name"] or m["role"]}' for m in marks[:limit])


# ----------------------------------------------------------------------
# Công cụ gộp bước
# ----------------------------------------------------------------------
_PROTECTED = ("c:\\windows", "c:\\program files", "c:\\programdata")


def write_text_file(path: str, content: str, open_after: bool = False) -> str:
    """
    Ghi nội dung văn bản (UTF-8) ra tệp, tự tạo thư mục; tùy chọn mở tệp ngay sau đó.
    GỘP: mở Notepad + gõ + Ctrl+S + chọn thư mục thành 1 lệnh. Hỗ trợ ~ và %USERPROFILE%/$env:USERPROFILE.
    """
    if safety.is_stopped():
        return f"Thất bại: {safety.get_stop_reason()}"
    p = expand_path(path)
    if config.safe_mode and str(p).lower().startswith(_PROTECTED):
        return f"Thất bại: Safe Mode chặn ghi vào thư mục hệ thống '{p}'."
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    except Exception as e:
        return f"Thất bại khi ghi '{p}': {e}"
    msg = f"Đã ghi {len(content)} ký tự vào '{p}'."
    if open_after:
        r = controller.run_powershell(f"Start-Process -FilePath '{str(p)}'")
        if r.get("success"):
            w = controller.wait_for_window(p.stem, timeout=5)
            msg += f" Đã mở tệp (cửa sổ: {w['title']})." if w else " Đã gửi lệnh mở tệp."
        else:
            msg += f" Không mở được tệp: {r.get('error') or r.get('stderr')}"
    return msg


def open_app_and_wait(name: str, timeout: float = 8.0) -> str:
    """
    Mở ứng dụng/tệp/URL (Start-Process) và CHỜ tới khi cửa sổ xuất hiện; trả về tiêu đề cửa sổ.
    Ví dụ: 'notepad', 'calc', 'chrome', 'https://google.com', 'D:\\\\Tai lieu'.
    """
    timeout = min(max(float(timeout or 8), 1.0), 20.0)
    before = controller.get_foreground_window().get("title", "")
    safe = str(name).strip().replace("'", "''")
    res = controller.run_powershell(f"Start-Process '{safe}'")
    if not res.get("success"):
        return f"Thất bại: {res.get('error') or res.get('stderr')}"
    keyword = re.sub(r"\.(exe|lnk)$", "", Path(safe.replace("'", "")).name.split("?")[0], flags=re.I)
    deadline = time.time() + timeout
    while time.time() < deadline:
        if safety.is_stopped():
            return f"Thất bại: {safety.get_stop_reason()}"
        title = controller.get_foreground_window().get("title", "")
        if title and title != before:
            time.sleep(0.2)  # cho cửa sổ ổn định
            return f"Đã mở '{name}'. Cửa sổ đang focus: {controller.get_foreground_window().get('title', title)}"
        w = controller.wait_for_window(keyword, timeout=0.3) if keyword else None
        if w:
            return f"Đã mở '{name}'. Cửa sổ: {w['title']}"
    return f"Đã chạy lệnh mở '{name}' nhưng CHƯA thấy cửa sổ mới sau {timeout:.0f}s (có thể đã mở sẵn hoặc chậm)."


BATCH_ALLOWED = {
    "run_powershell", "write_text_file", "open_app_and_wait", "keyboard_shortcut", "type_vietnamese_text",
    "wait_seconds", "desktop_click", "desktop_type", "desktop_focus_window", "click_mark",
    "mouse_click_coords", "mouse_double_click", "mouse_right_click", "mouse_hover", "mouse_scroll_page",
    "mouse_drag_and_drop", "solitaire_move_by_column", "solitaire_draw_card",
}


def run_actions(actions: str) -> str:
    """
    Chạy tuần tự nhiều thao tác trong MỘT lệnh gọi (tối đa 12), dừng ngay ở thao tác lỗi đầu tiên.
    actions: chuỗi JSON dạng [{"tool":"open_app_and_wait","args":{"name":"notepad"}},
    {"tool":"type_vietnamese_text","args":{"text":"xin chào"}}, {"tool":"keyboard_shortcut","args":{"keys":"ctrl+s"}}].
    Chỉ dùng khi bạn đã chắc chắn các bước (không cần nhìn kết quả từng bước).
    """
    from core.tools import TOOL_MAP
    from core.recorder import recorder
    from core.guard import is_failure

    try:
        items = json.loads(actions) if isinstance(actions, str) else list(actions)
        assert isinstance(items, list) and items
    except Exception:
        return 'Lỗi: actions phải là chuỗi JSON dạng [{"tool": "...", "args": {...}}, ...].'
    if len(items) > 12:
        return "Lỗi: tối đa 12 thao tác mỗi lần run_actions."

    lines = []
    for i, it in enumerate(items, 1):
        if safety.is_stopped():
            lines.append(f"{i}. DỪNG: {safety.get_stop_reason()}")
            break
        name = str(it.get("tool", "")) if isinstance(it, dict) else ""
        args = it.get("args", {}) if isinstance(it, dict) else {}
        if name not in BATCH_ALLOWED:
            lines.append(f"{i}. Lỗi: công cụ '{name}' không được phép trong run_actions.")
            break
        try:
            result = str(TOOL_MAP[name](**(args or {})))
        except Exception as e:
            result = f"Lỗi khi thực thi {name}: {e}"
        failed = is_failure(result)
        recorder.record(name, args, result)
        lines.append(f"{i}. {name}: {'LỖI - ' if failed else ''}{one_line(result, 140)}")
        if failed:
            lines.append(f"(đã dừng ở thao tác {i}/{len(items)})")
            break
    lines.append(f"[Cửa sổ] {controller.get_foreground_window().get('title', '')}")
    return "\n".join(lines)


# ----------------------------------------------------------------------
# Kỹ năng chạy được
# ----------------------------------------------------------------------
def run_skill(skill_name: str, args: str = "{}") -> str:
    """
    Chạy một kỹ năng dạng script Python trong skills/ (xem list_skills: đuôi .py) và nhận kết quả.
    args: chuỗi JSON tham số, ví dụ '{"folder": "D:\\\\Tai lieu", "max_files": 5}'. Rẻ hơn nhiều so với tự làm từng bước.
    """
    clean = re.sub(r"\.py$", "", str(skill_name).strip())
    target = SKILLS_DIR / f"{clean}.py"
    if not target.is_file():
        return f"Không có kỹ năng chạy được '{skill_name}'. Gọi list_skills để xem danh sách."
    if "pyautogui" in target.read_text(encoding="utf-8", errors="replace"):
        return "Lỗi: kỹ năng dùng pyautogui không được phép chạy."
    try:
        json.loads(args or "{}")
    except Exception:
        return "Lỗi: args phải là chuỗi JSON hợp lệ."
    try:
        proc = subprocess.run(
            [sys.executable, str(target), args or "{}"], capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=60, cwd=str(ROOT),
        )
    except subprocess.TimeoutExpired:
        return "Lỗi: kỹ năng chạy quá 60 giây."
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    status = "Thành công" if proc.returncode == 0 else f"Lỗi (mã {proc.returncode})"
    return f"[{status}]\n{out}" + (f"\nSTDERR:\n{truncate_text(err, 800)}" if err else "")


# ----------------------------------------------------------------------
# Solitaire: code tính nước đi
# ----------------------------------------------------------------------
def solitaire_best_move(state: str) -> str:
    """
    Tính NƯỚC ĐI TỐT NHẤT cho Solitaire Klondike từ trạng thái bàn bài (JSON) và trả về lệnh gọi công cụ cần dùng.
    Đọc bàn bài MỘT lần thành JSON: {"tableau":[{"down":3,"up":["K Cơ","Q Bích"]}, ...7 cột...],
    "waste":"3 Cơ" hoặc null, "foundations":{"co":0,"ro":0,"bich":0,"tep":0}, "stock":24}.
    "up" liệt kê từ lá ngửa đầu cột đến lá trên cùng. Nhanh và chuẩn hơn tự nghĩ nước đi.
    """
    from core.solitaire import best_move_text
    return best_move_text(state)
