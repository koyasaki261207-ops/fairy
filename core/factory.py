"""
NHÀ MÁY TẠO "BỘ NÃO" + LỚP SMARTBRAIN BỌC NGOÀI
Thứ tự xử lý mỗi nhiệm vụ (rẻ -> đắt):
  1) Router: lệnh quen thuộc (mở app/web, tìm kiếm, tìm tệp) chạy thẳng bằng code        -> 0 token
  2) Recipe: cách làm đã thành công trước đó cho đúng mục tiêu này, chạy lại + kiểm chứng -> 0 token
  3) AI: Gemini / Claude / Hybrid
Sau khi AI thành công, cố gắng lưu recipe; mọi lượt đều ghi vào logs/runs.jsonl.
"""

import time

from config import config
from core.recorder import recorder
from core.safety import safety


class SmartBrain:
    def __init__(self, inner, provider: str, log_callback=None, status_callback=None):
        self.inner = inner
        self.provider = provider
        self.log_callback = log_callback or (lambda tag, msg: print(f"[{tag}] {msg}"))
        self.status_callback = status_callback or (lambda st: None)

    def log(self, tag, msg):
        self.log_callback(tag, msg)

    def _finish(self, goal, route, result, t0):
        from core import runlog
        runlog.append(goal, self.provider, route, result, time.time() - t0)
        result.setdefault("route", route)
        return result

    def run_task(self, goal: str) -> dict:
        from core import recipes, router
        from core.tools import reset_run_state

        t0 = time.time()
        safety.reset()
        safety.start_hotkey_listener()
        reset_run_state()
        recorder.begin()

        # 1) Router
        if config.router_enabled:
            self.status_callback("Đang xử lý nhanh...")
            try:
                routed = router.try_route(goal)
            except Exception as e:  # router không bao giờ được làm hỏng nhiệm vụ
                self.log("WARN", f"Router lỗi, chuyển sang AI: {e}")
                routed = None
            if routed and routed.get("success"):
                self.log("SUCCESS", f"Hoàn thành không dùng AI: {routed['summary']}")
                self.status_callback("Hoàn thành xuất sắc!")
                return self._finish(goal, "router", {"success": True, "summary": routed["summary"], "steps": 1}, t0)
            if routed:
                self.log("INFO", f"Xử lý nhanh chưa đạt ({routed.get('error')}), chuyển cho AI.")

        # 2) Recipe
        if config.recipes_enabled:
            rec = recipes.find(goal)
            if rec:
                self.log("INFO", "Tìm thấy cách làm đã lưu cho mục tiêu này, chạy lại không cần AI...")
                ok, report = recipes.replay(rec, self.log)
                if ok:
                    self.log("SUCCESS", "Hoàn thành bằng recipe đã lưu (0 token).")
                    self.status_callback("Hoàn thành xuất sắc!")
                    return self._finish(goal, "recipe",
                                        {"success": True, "summary": "Đã chạy lại cách làm đã lưu.", "steps": len(rec["steps"])}, t0)
                self.log("WARN", f"Recipe không còn đúng ({report}). Chuyển cho AI.")
                reset_run_state()
                recorder.begin()

        # 3) AI
        result = self.inner.run_task(goal)
        if result.get("success") and config.recipes_enabled:
            try:
                if recipes.maybe_save(goal):
                    self.log("INFO", "Đã lưu cách làm này để lần sau chạy không cần AI.")
            except Exception:
                pass
        return self._finish(goal, "ai", result, t0)


def make_brain(provider: str, log_callback=None, status_callback=None):
    """provider: 'gemini' | 'claude' | 'hybrid'."""
    if provider == "hybrid":
        from core.hybrid_brain import HybridBrain as Cls
    elif provider == "claude":
        from core.claude_brain import ClaudeBrain as Cls
    else:
        from core.brain import GeminiBrain as Cls
    inner = Cls(log_callback=log_callback, status_callback=status_callback)
    return SmartBrain(inner, provider, log_callback, status_callback)
