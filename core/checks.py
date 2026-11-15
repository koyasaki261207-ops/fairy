"""
KIỂM CHỨNG BẰNG MÁY (MACHINE-CHECKABLE SUCCESS CRITERIA)
Tiêu chí hoàn thành dạng chuỗi 'loại:tham_số' do bộ não (Claude) viết, code tự đối chiếu với trạng thái thật
-> AI không phải chụp màn hình/snapshot chỉ để tự xem mình đã xong chưa.

Các loại hỗ trợ:
  file_exists:<đường dẫn>            dir_exists:<đường dẫn>        file_not_exists:<đường dẫn>
  file_contains:<đường dẫn>::<chuỗi>                              (không phân biệt hoa/thường)
  window_title_contains:<chuỗi>      process_running:<tên tiến trình, vd notepad>
Đường dẫn hỗ trợ biến môi trường (%USERPROFILE%, $env:USERPROFILE) và ~.
"""

import os
import re
from pathlib import Path


def _path(p: str) -> Path:
    p = p.strip().strip('"').strip("'")
    p = re.sub(r"\$env:(\w+)", lambda m: os.environ.get(m.group(1), m.group(0)), p, flags=re.I)
    return Path(os.path.expanduser(os.path.expandvars(p)))


def _check_one(spec: str) -> tuple[bool, str]:
    kind, _, arg = spec.partition(":")
    kind = kind.strip().lower()
    arg = arg.strip()
    if kind == "file_exists":
        p = _path(arg)
        return p.is_file(), f"file_exists {p}"
    if kind == "dir_exists":
        p = _path(arg)
        return p.is_dir(), f"dir_exists {p}"
    if kind == "file_not_exists":
        p = _path(arg)
        return not p.exists(), f"file_not_exists {p}"
    if kind == "file_contains":
        path_s, _, needle = arg.partition("::")
        p = _path(path_s)
        if not p.is_file():
            return False, f"file_contains {p}: tệp không tồn tại"
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return False, f"file_contains {p}: {e}"
        return needle.strip().lower() in text.lower(), f"file_contains {p} '{needle.strip()[:40]}'"
    if kind == "window_title_contains":
        try:
            from core.controller import controller
            kw = arg.lower()
            return any(kw in w["title"].lower() for w in controller.list_visible_windows()), f"window '{arg}'"
        except Exception as e:
            return False, f"window '{arg}': {e}"
    if kind == "process_running":
        try:
            import psutil
            name = arg.lower().removesuffix(".exe")
            return any(name in (p.info["name"] or "").lower() for p in psutil.process_iter(["name"])), f"process {arg}"
        except Exception as e:
            return False, f"process {arg}: {e}"
    return True, f"(bỏ qua tiêu chí không hỗ trợ: {spec[:40]})"


def run_checks(checks: list[str]) -> tuple[bool, str]:
    """Chạy toàn bộ tiêu chí. Trả về (tất_cả_đạt, báo_cáo_ngắn)."""
    if not checks:
        return True, ""
    ok_all, lines = True, []
    for spec in checks:
        try:
            ok, desc = _check_one(str(spec))
        except Exception as e:
            ok, desc = False, f"{spec}: {e}"
        ok_all = ok_all and ok
        lines.append(f"{'ĐẠT' if ok else 'KHÔNG ĐẠT'}: {desc}")
    return ok_all, "\n".join(lines)
