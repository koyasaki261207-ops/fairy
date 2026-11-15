"""
RECIPES: LƯU & CHẠY LẠI CÁCH LÀM ĐÃ THÀNH CÔNG (BỎ QUA AI Ở LẦN SAU)
Chỉ lưu khi chuỗi thao tác hoàn toàn "xác định" (ghi tệp, mở ứng dụng, PowerShell, phím tắt, gõ chữ, chờ)
và có ít nhất một điều kiện kiểm chứng bằng máy (vd tệp đã được tạo). Lần sau gặp đúng mục tiêu đó:
chạy lại các bước rồi kiểm chứng; chỉ khi bước nào lệch hoặc kiểm chứng thất bại mới gọi AI.
Công thức hết hạn sau 30 ngày. Lưu tại memory/recipes.json (đã .gitignore).
"""

import difflib
import json
import re
import time
from pathlib import Path

from core.checks import run_checks
from core.guard import _norm, is_failure
from core.recorder import recorder

STORE = Path(__file__).resolve().parent.parent / "memory" / "recipes.json"
REPLAYABLE = {
    "write_text_file", "open_app_and_wait", "run_powershell", "keyboard_shortcut", "type_vietnamese_text",
    "wait_seconds",
}
TTL_SECONDS = 30 * 86400
MAX_STEPS = 12
MATCH_RATIO = 0.93


def norm_goal(goal: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", _norm(goal)).strip()


def _load() -> dict:
    try:
        return json.loads(STORE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save(data: dict):
    STORE.parent.mkdir(parents=True, exist_ok=True)
    STORE.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def find(goal: str) -> dict | None:
    key = norm_goal(goal)
    if not key:
        return None
    data = _load()
    now = time.time()
    rec = data.get(key)
    if rec is None:
        best = difflib.get_close_matches(key, list(data), n=1, cutoff=MATCH_RATIO)
        rec = data.get(best[0]) if best else None
    if rec and now - rec.get("ts", 0) <= TTL_SECONDS:
        return rec
    return None


def derive_checks(steps: list[dict]) -> list[str]:
    checks = []
    for st in steps:
        if st["tool"] == "write_text_file" and st["args"].get("path"):
            checks.append(f"file_exists:{st['args']['path']}")
    return checks


def maybe_save(goal: str) -> bool:
    """Gọi sau khi một lượt chạy thành công: lưu recipe nếu thỏa điều kiện an toàn."""
    steps = [s for s in recorder.action_steps() if not is_failure(s.get("result", ""))]
    if not steps or len(steps) > MAX_STEPS or any(s["tool"] not in REPLAYABLE for s in steps):
        return False
    # Bỏ cả khi có bước thất bại đã bị loại: lượt chạy "sạch" mới đáng lưu lại
    if len(steps) != len(recorder.action_steps()):
        return False
    checks = derive_checks(steps)
    if not checks:
        return False
    data = _load()
    data[norm_goal(goal)] = {
        "goal": goal[:200], "steps": [{"tool": s["tool"], "args": s["args"]} for s in steps],
        "checks": checks, "ts": time.time(),
    }
    _save(data)
    return True


def replay(rec: dict, log=lambda tag, msg: None) -> tuple[bool, str]:
    """Chạy lại recipe. Trả về (thành_công, báo_cáo)."""
    from core.tools import dispatch_tool
    for i, st in enumerate(rec["steps"], 1):
        out = dispatch_tool(st["tool"], st["args"])
        log("ACTION", f"↻ Recipe {i}/{len(rec['steps'])}: {st['tool']}")
        if is_failure(out.text):
            return False, f"Bước {i} ({st['tool']}) thất bại: {out.text[:160]}"
    ok, report = run_checks(rec.get("checks", []))
    return ok, report
