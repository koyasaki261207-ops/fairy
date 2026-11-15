"""
BỘ NÃO KẾT HỢP: CLAUDE (NÃO) + GEMINI (TAY CHÂN)

- Claude chỉ lập kế hoạch và ra quyết định. Claude KHÔNG nhìn ảnh chụp màn hình, KHÔNG nhận
  kết quả thô của công cụ -> mỗi lượt Claude chỉ tốn vài trăm token (mục tiêu + các báo cáo ngắn).
- Gemini nhận từng nhiệm vụ con, tự chạy vòng ReAct đầy đủ (PowerShell, Accessibility, ảnh chụp, chuột/phím...)
  rồi trả về một báo cáo ngắn đã kiểm chứng.
- Claude đọc báo cáo -> giao việc tiếp / giao lại theo cách khác / kết thúc.

Số lượt gọi Claude ≈ số nhiệm vụ con + 1 (nhiệm vụ đơn giản: chỉ 2 lượt).
"""

import anthropic

from config import config
from core.safety import safety
from core.brain import GeminiBrain
from core.context import set_claude_cache_breakpoint, truncate_text, one_line

PLANNER_SYSTEM = """
Bạn là BỘ NÃO điều phối của AutoPilot trên Windows. Bạn KHÔNG tự thao tác máy tính; bạn giao việc cho
EXECUTOR (một AI khác) có đủ công cụ: PowerShell, đọc tệp PDF/Word/văn bản, cây Accessibility của ứng dụng,
chụp màn hình + chuột/bàn phím, chạy Python, và kho kỹ năng skills/ (ví dụ luật Solitaire).

CÁCH LÀM:
1. Chia mục tiêu thành ÍT nhiệm vụ con nhất có thể. Mỗi nhiệm vụ con là một khối việc trọn vẹn executor tự làm được.
   Mục tiêu đơn giản -> giao MỘT lần duy nhất.
2. delegate_to_executor: chỉ dẫn phải TỰ CHỨA (executor không thấy mục tiêu gốc hay lịch sử): ứng dụng, đường dẫn,
   nội dung chính xác cần gõ/ghi (nếu cần viết nội dung chất lượng, hãy tự soạn sẵn trong chỉ dẫn),
   và tiêu chí hoàn thành kiểm chứng được.
3. Việc đọc/tóm tắt dữ liệu lớn: giao executor đọc và báo cáo tóm tắt, đừng yêu cầu chép nguyên văn.
4. Đọc báo cáo. Nếu chưa đạt: chẩn đoán ngắn gọn rồi giao lại với cách tiếp cận KHÁC, không lặp y hệt.
5. Khi báo cáo cho thấy mục tiêu đã đạt -> finish_task. Nếu không thể đạt sau vài lần thử -> finish_task(is_success=false).

Trả lời cực ngắn, không giải thích dài dòng. Luôn kết thúc lượt bằng một lệnh gọi công cụ.
""".strip()

PLANNER_TOOLS = [
    {
        "name": "delegate_to_executor",
        "description": "Giao một nhiệm vụ con cho executor thực hiện trên máy và nhận về báo cáo ngắn.",
        "input_schema": {
            "type": "object",
            "properties": {
                "instruction": {"type": "string", "description": "Chỉ dẫn tự chứa, cụ thể."},
                "success_criteria": {"type": "string", "description": "Điều kiện kiểm chứng được để coi là xong."},
                "max_steps": {"type": "integer", "description": "Số bước tối đa cho executor (mặc định 12)."},
            },
            "required": ["instruction"],
        },
    },
    {
        "name": "finish_task",
        "description": "Kết thúc toàn bộ mục tiêu và báo cáo cho người dùng.",
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "is_success": {"type": "boolean"},
            },
            "required": ["summary"],
        },
        # Điểm cache cho (tools + system) - chỉ có hiệu lực khi đủ dài; không hại gì nếu ngắn
        "cache_control": {"type": "ephemeral"},
    },
]

NUDGE_TEXT = "Hãy gọi delegate_to_executor hoặc finish_task."


def format_report(res: dict, limit: int) -> str:
    """Rút báo cáo của executor thành vài dòng cho Claude."""
    if res.get("stopped"):
        status = "ĐÃ DỪNG"
    else:
        status = "THÀNH CÔNG" if res.get("success") else "CHƯA ĐẠT"
    lines = [f"Trạng thái: {status} ({res.get('steps', 0)} bước)"]
    if res.get("summary"):
        lines.append(f"Báo cáo: {res['summary']}")
    if res.get("error") and res.get("error") != res.get("summary"):
        lines.append(f"Lỗi: {res['error']}")
    if res.get("notes"):
        lines.append(f"Sổ nhớ executor: {res['notes']}")
    if not res.get("success") and res.get("trace"):
        lines.append("Thao tác cuối:")
        lines.extend(f"- {t}" for t in res["trace"][-4:])
    return truncate_text("\n".join(lines), limit)


class HybridBrain:
    def __init__(self, log_callback=None, status_callback=None):
        self.log_callback = log_callback or (lambda tag, msg: print(f"[{tag}] {msg}"))
        self.status_callback = status_callback or (lambda st: None)
        self.client = None
        self.executor = GeminiBrain(log_callback=self.log_callback, status_callback=self.status_callback)

    def log(self, tag: str, msg: str):
        self.log_callback(tag, msg)

    def set_status(self, status: str):
        self.status_callback(status)

    def _check_keys(self) -> str:
        if not config.anthropic_api_key:
            return "Chưa cấu hình ANTHROPIC_API_KEY (Claude làm bộ não)."
        if not config.gemini_api_keys:
            return "Chưa cấu hình GEMINI_API_KEY (Gemini làm tay chân)."
        return ""

    def run_task(self, goal: str) -> dict:
        safety.reset()
        safety.start_hotkey_listener()

        missing = self._check_keys()
        if missing:
            self.log("ERROR", missing)
            self.set_status("Thiếu API Key")
            return {"success": False, "error": missing}
        self.client = anthropic.Anthropic(api_key=config.anthropic_api_key, max_retries=4)

        model = config.claude_model or "claude-sonnet-5-5"
        self.log("INFO", f"Chế độ kết hợp: Claude ({model}) lập kế hoạch · Gemini ({config.gemini_model}) thực thi.")
        self.log("INFO", f"Bắt đầu nhiệm vụ: '{goal}'")

        messages = [{"role": "user", "content": f"MỤC TIÊU CỦA NGƯỜI DÙNG: {goal}"}]
        claude_usage = {"in": 0, "cache_read": 0, "out": 0}
        gemini_usage = {"in": 0, "cached": 0, "out": 0}
        rounds = 0
        max_rounds = config.planner_max_rounds

        def done(success: bool, summary: str = "", error: str = "") -> dict:
            self.log(
                "INFO",
                f"📊 Tổng · Claude: vào {claude_usage['in']} (đọc cache {claude_usage['cache_read']}) · ra {claude_usage['out']} "
                f"| Gemini: vào {gemini_usage['in']} (cache {gemini_usage['cached']}) · ra {gemini_usage['out']} "
                f"| {rounds} lượt Claude",
            )
            if success:
                self.set_status("Hoàn thành xuất sắc!")
                self.log("SUCCESS", f"🎉 {summary}")
            elif not safety.is_stopped():
                self.set_status("Chưa hoàn thành")
                self.log("WARN", error or summary)
            return {"success": success, "summary": summary, "error": error}

        while rounds < max_rounds:
            if safety.is_stopped():
                return done(False, error=safety.get_stop_reason())
            rounds += 1
            self.set_status(f"Lượt {rounds}/{max_rounds}: Claude đang lập kế hoạch...")
            self.log("STEP", f"=== CLAUDE · LƯỢT {rounds} ===")

            set_claude_cache_breakpoint(messages)
            try:
                response = self.client.messages.create(
                    model=model,
                    max_tokens=config.planner_max_tokens,
                    system=PLANNER_SYSTEM,
                    tools=PLANNER_TOOLS,
                    messages=messages,
                )
            except Exception as e:
                self.log("ERROR", f"Lỗi Claude API: {e}")
                self.set_status("Lỗi API Claude")
                return done(False, error=str(e))

            u = response.usage
            claude_usage["in"] += u.input_tokens or 0
            claude_usage["cache_read"] += getattr(u, "cache_read_input_tokens", 0) or 0
            claude_usage["out"] += u.output_tokens or 0
            self.log("INFO", f"📊 Claude: vào {u.input_tokens} · ra {u.output_tokens}")

            messages.append({"role": "assistant", "content": response.content})
            tool_uses = []
            for block in response.content:
                if block.type == "text" and block.text.strip():
                    self.log("THOUGHT", f"Claude: {block.text.strip()}")
                elif block.type == "tool_use":
                    tool_uses.append(block)

            if response.stop_reason == "refusal":
                return done(False, error="Claude từ chối thực hiện yêu cầu này.")
            if not tool_uses:
                messages.append({"role": "user", "content": NUDGE_TEXT})
                continue

            results = []
            for block in tool_uses:
                args = block.input or {}
                if block.name == "finish_task":
                    ok = bool(args.get("is_success", True))
                    summary = args.get("summary") or "Đã hoàn thành."
                    return done(ok, summary=summary, error="" if ok else summary)

                if block.name != "delegate_to_executor":
                    results.append({"type": "tool_result", "tool_use_id": block.id,
                                    "content": f"Không có công cụ '{block.name}'.", "is_error": True})
                    continue

                instruction = str(args.get("instruction", "")).strip()
                criteria = str(args.get("success_criteria", "")).strip()
                try:
                    budget = int(args.get("max_steps") or 12)
                except (TypeError, ValueError):
                    budget = 12
                budget = max(1, min(budget, config.executor_max_steps))

                self.log("ACTION", f"⚡ Giao cho Gemini ({budget} bước): {one_line(instruction, 300)}")
                res = self.executor.run_subtask(instruction, criteria, budget)
                for k in gemini_usage:
                    gemini_usage[k] += res.get("usage", {}).get(k, 0)

                if res.get("stopped"):
                    return done(False, error=res.get("error") or "Đã dừng.")
                if res.get("api_error"):
                    # Gemini không dùng được -> hỏi Claude cũng vô ích, dừng sớm để không tốn token
                    return done(False, error=f"Gemini (tay chân) không khả dụng: {res.get('error')}")

                report = format_report(res, config.report_max_chars)
                self.log("OBSERVATION", f"👁️ Báo cáo cho Claude: {report}")
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": report})

            messages.append({"role": "user", "content": results})

        return done(False, error=f"Đã hết {max_rounds} lượt lập kế hoạch của Claude mà chưa hoàn thành.")
