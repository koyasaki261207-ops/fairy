"""
BỘ NÃO ANTHROPIC CLAUDE (CLAUDE REACT ENGINE)
Hỗ trợ Tool Calling và Phân tích hình ảnh thị giác (Multimodal Vision).

Tối ưu token:
- Prompt caching: 1 điểm cache cho (tools + system) cố định, 1 điểm cache trượt ở cuối hội thoại
  -> mỗi bước chỉ trả giá đầy đủ cho phần mới, phần cũ đọc từ cache (~10% giá).
- Schema công cụ gọn (mô tả 1 dòng, không mô tả tham số lặp lại).
- Chỉ giữ N ảnh chụp màn hình gần nhất; kết quả công cụ bị cắt gọn; lịch sử cũ nén theo đợt.
"""

import base64
import inspect
import anthropic

from config import config
from core.safety import safety
from core.controller import controller
from core.vision import vision
from core.tools import ALL_TOOLS, dispatch_tool, reset_run_state
from core.guard import RunGuard, skill_hint
from core.prompts import SYSTEM_INSTRUCTION
from core.context import (
    prune_claude_images,
    compact_claude_history,
    set_claude_cache_breakpoint,
    format_args,
)

DEFAULT_CLAUDE_MODEL = "claude-sonnet-5-5"
NUDGE_TEXT = "Hãy gọi công cụ tiếp theo hoặc gọi finish_task nếu bạn đã hoàn thành nhiệm vụ."

_PY_TO_JSON_TYPE = {int: "integer", float: "number", bool: "boolean", str: "string"}


def func_to_anthropic_tool(func) -> dict:
    """Tự động chuyển đổi hàm Python sang schema Tool của Anthropic Claude (gọn nhẹ)."""
    sig = inspect.signature(func)
    doc = " ".join((inspect.getdoc(func) or "").split())  # gộp khoảng trắng/xuống dòng thừa
    properties = {}
    required = []

    for param_name, param in sig.parameters.items():
        prop = {"type": _PY_TO_JSON_TYPE.get(param.annotation, "string")}
        if param.default is inspect.Parameter.empty:
            required.append(param_name)
        else:
            prop["default"] = param.default
        properties[param_name] = prop

    return {
        "name": func.__name__,
        "description": doc[:600],
        "input_schema": {
            "type": "object",
            "properties": properties,
            "required": required,
        },
    }


CLAUDE_TOOLS_SCHEMA = [func_to_anthropic_tool(f) for f in ALL_TOOLS]

# System prompt dạng block có cache_control: cache luôn cả danh sách tools đứng trước nó.
CLAUDE_SYSTEM_BLOCKS = [
    {"type": "text", "text": SYSTEM_INSTRUCTION, "cache_control": {"type": "ephemeral"}}
]


class ClaudeBrain:
    def __init__(self, log_callback=None, status_callback=None):
        self.log_callback = log_callback or (lambda tag, msg: print(f"[{tag}] {msg}"))
        self.status_callback = status_callback or (lambda st: None)
        self.client = None

    def _init_client(self):
        key = config.anthropic_api_key
        if not key:
            raise ValueError(
                "Chưa cấu hình ANTHROPIC_API_KEY! Hãy nhập API Key trong phần Cài Đặt hoặc file .env."
            )
        # SDK tự retry 429/5xx/529 với backoff
        self.client = anthropic.Anthropic(api_key=key, max_retries=4)

    def log(self, tag: str, msg: str):
        if self.log_callback:
            self.log_callback(tag, msg)

    def set_status(self, status: str):
        if self.status_callback:
            self.status_callback(status)

    def run_task(self, goal: str) -> dict:
        """Khởi chạy vòng lặp ReAct giải quyết nhiệm vụ của người dùng với Claude"""
        safety.reset()
        safety.start_hotkey_listener()

        try:
            self._init_client()
        except Exception as e:
            self.log("ERROR", str(e))
            self.set_status("Lỗi Claude API Key")
            return {"success": False, "error": str(e)}

        model_name = config.claude_model or DEFAULT_CLAUDE_MODEL
        self.set_status("Đang khởi động Claude...")
        self.log("INFO", f"Bắt đầu nhiệm vụ với Claude ({model_name}): '{goal}'")

        fg_win = controller.get_foreground_window()
        screen_w, screen_h = vision.get_screen_size()
        initial_context = (
            f"MỤC TIÊU CỦA NGƯỜI DÙNG: {goal}\n\n"
            f"Thông tin hệ thống:\n"
            f"- Cửa sổ đang mở: {fg_win.get('title', 'Không xác định')}\n"
            f"- Kích thước màn hình: {screen_w} x {screen_h} pixels.\n"
            f"{skill_hint(goal)}"
            f"Hãy bắt đầu phân tích và gọi công cụ phù hợp để thực thi mục tiêu."
        )

        messages = [{"role": "user", "content": initial_context}]
        reset_run_state()
        guard = RunGuard()

        step = 0
        max_steps = config.max_steps
        task_finished = False
        final_summary = ""
        usage_total = {"in": 0, "cache_read": 0, "cache_write": 0, "out": 0}

        def stopped_result():
            reason = safety.get_stop_reason()
            self.log("STOP", f"ĐÃ DỪNG KHẨN CẤP: {reason}")
            self.set_status("Đã dừng")
            return {"success": False, "error": reason}

        while step < max_steps and not task_finished:
            step += 1
            if safety.is_stopped():
                return stopped_result()

            self.set_status(f"Bước {step}/{max_steps}: Claude đang suy luận...")
            self.log("STEP", f"=== BƯỚC {step} (Claude) ===")

            # Giữ ngữ cảnh gọn + đặt điểm cache trượt ở cuối hội thoại
            prune_claude_images(messages, config.keep_screenshots)
            if compact_claude_history(messages, config.history_compact_chars):
                self.log("INFO", "🗜️ Đã nén các kết quả công cụ cũ để tiết kiệm token.")
            set_claude_cache_breakpoint(messages)

            try:
                response = self.client.messages.create(
                    model=model_name,
                    max_tokens=config.max_output_tokens,
                    system=CLAUDE_SYSTEM_BLOCKS,
                    tools=CLAUDE_TOOLS_SCHEMA,
                    messages=messages,
                )
            except Exception as e:
                err_msg = str(e)
                self.log("ERROR", f"Lỗi Claude API: {err_msg}")
                self.set_status("Lỗi API Claude")
                return {"success": False, "error": err_msg}

            usage = getattr(response, "usage", None)
            if usage is not None:
                u_in = usage.input_tokens or 0
                u_read = getattr(usage, "cache_read_input_tokens", 0) or 0
                u_write = getattr(usage, "cache_creation_input_tokens", 0) or 0
                u_out = usage.output_tokens or 0
                usage_total["in"] += u_in
                usage_total["cache_read"] += u_read
                usage_total["cache_write"] += u_write
                usage_total["out"] += u_out
                self.log("INFO", f"📊 Token: vào {u_in} · đọc cache {u_read} · ghi cache {u_write} · ra {u_out}")

            messages.append({"role": "assistant", "content": response.content})

            tool_use_blocks = []
            for block in response.content:
                if block.type == "thinking":
                    thinking_content = (getattr(block, "thinking", "") or "").strip()
                    if thinking_content:
                        self.log("THOUGHT", f"🤔 [Suy nghĩ sâu]: {thinking_content}")
                elif block.type == "text" and (getattr(block, "text", "") or "").strip():
                    text_content = block.text.strip()
                    self.log("THOUGHT", text_content)
                    low = text_content.lower()
                    if "hoàn thành" in low or "đã xong" in low:
                        final_summary = text_content
                elif block.type == "tool_use":
                    tool_use_blocks.append(block)

            if response.stop_reason == "refusal":
                self.set_status("Claude từ chối")
                return {"success": False, "error": "Claude từ chối thực hiện yêu cầu này."}

            if not tool_use_blocks:
                if final_summary:
                    task_finished = True
                    break
                messages.append({"role": "user", "content": NUDGE_TEXT})
                continue

            tool_results = []
            for block in tool_use_blocks:
                if safety.is_stopped():
                    return stopped_result()

                fn_name = block.name
                fn_args = block.input or {}
                self.log("ACTION", f"⚡ {fn_name}({format_args(fn_args)})")
                self.set_status(f"Claude thực thi: {fn_name}")

                outcome = dispatch_tool(fn_name, fn_args, config.max_tool_result_chars, guard=guard)
                if outcome.finished:
                    task_finished = True
                    final_summary = outcome.summary
                self.log("OBSERVATION", f"👁️ Kết quả: {outcome.text}")

                if outcome.image:
                    tool_content = [
                        {"type": "text", "text": outcome.text},
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": base64.b64encode(outcome.image).decode("ascii"),
                            },
                        },
                    ]
                else:
                    tool_content = outcome.text

                tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": tool_content})

            notes = guard.pending_notes_text()
            if notes:
                tool_results.append({"type": "text", "text": notes})
            messages.append({"role": "user", "content": tool_results})

        self.log(
            "INFO",
            f"📊 Tổng token: vào {usage_total['in']} · đọc cache {usage_total['cache_read']} · "
            f"ghi cache {usage_total['cache_write']} · ra {usage_total['out']} · {step} bước",
        )
        if task_finished:
            self.set_status("Hoàn thành xuất sắc!")
            self.log("SUCCESS", f"🎉 {final_summary}")
            return {"success": True, "summary": final_summary}

        self.set_status("Hết số bước tối đa")
        msg = f"Đã đạt giới hạn {max_steps} bước nhưng chưa hoàn thành toàn bộ."
        self.log("WARN", msg)
        return {"success": False, "error": msg}
