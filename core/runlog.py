"""
NHẬT KÝ CHẠY (logs/runs.jsonl): mỗi lượt một dòng JSON để phân tích token, tốc độ và tỉ lệ thành công
-> chỉnh các ngưỡng (số bước, cảnh báo lặp, leo thang...) dựa trên số liệu thật thay vì đoán.
Chỉ ghi cục bộ (logs/ nằm trong .gitignore).
"""

import json
import time
from pathlib import Path

from config import config

LOG_PATH = Path(__file__).resolve().parent.parent / "logs" / "runs.jsonl"


def append(goal: str, provider: str, route: str, result: dict, duration: float):
    if not config.runlog_enabled:
        return
    entry = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "goal": goal[:200],
        "provider": provider,
        "route": route,                      # router | recipe | ai
        "success": bool(result.get("success")),
        "steps": result.get("steps"),
        "usage": result.get("usage"),
        "duration_s": round(duration, 2),
        "error": (result.get("error") or "")[:200] or None,
    }
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


def summarize(path: Path = LOG_PATH, last: int = 200) -> dict:
    """Thống kê nhanh từ nhật ký: tỉ lệ thành công và thời gian trung bình theo tuyến."""
    try:
        rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()[-last:]]
    except Exception:
        return {}
    out = {}
    for r in rows:
        s = out.setdefault(r["route"], {"runs": 0, "ok": 0, "secs": 0.0})
        s["runs"] += 1
        s["ok"] += 1 if r["success"] else 0
        s["secs"] += r.get("duration_s") or 0
    return {k: {"runs": v["runs"], "success_rate": round(v["ok"] / v["runs"], 2),
                "avg_s": round(v["secs"] / v["runs"], 1)} for k, v in out.items()}
