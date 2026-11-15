"""
BỘ NÃO ANTHROPIC CLAUDE (CLAUDE REACT ENGINE)
Hỗ trợ các mô hình: Claude 3.7 Sonnet, Claude 3.5 Sonnet, Claude 3.5 Haiku.
Hỗ trợ đầy đủ Computer Use, Tool Calling và Phân tích hình ảnh thị giác (Multimodal Vision).
"""

import base64
import inspect
import time
from pathlib import Path
import anthropic

from config import config
from core.safety import safety
from core.controller import controller
from core.vision import vision
from core.tools import ALL_TOOLS, TOOL_MAP
from core.brain import SYSTEM_INSTRUCTION


def func_to_anthropic_tool(func) -> dict:
    """Tự động chuyển đổi hàm Python sang schema Tool của Anthropic Claude"""
    sig = inspect.signature(func)
    doc = inspect.getdoc(func) or ""
    properties = {}
    required = []

    for param_name, param in sig.parameters.items():
        p_type = "string"
        if param.annotation == int:
            p_type = "integer"
        elif param.annotation == float:
            p_type = "number"
        elif param.annotation == bool:
            p_type = "boolean"

        properties[param_name] = {
            "type": p_type,
            "description": f"Tham số {param_name}"
        }
        if param.default == inspect.Parameter.empty:
            required.append(param_name)

    return {
        "name": func.__name__,
        "description": doc.strip()[:1000],
        "input_schema": {
            "type": "object",
            "properties": properties,
            "required": required
        }
    }


CLAUDE_TOOLS_SCHEMA = [func_to_anthropic_tool(f) for f in ALL_TOOLS]


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
        self.client = anthropic.Anthropic(api_key=key)

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

        model_name = config.claude_model or "claude-3-5-sonnet-20241022"
        self.set_status("Đang khởi động Claude...")
        self.log("INFO", f"Bắt đầu nhiệm vụ với Claude ({model_name}): '{goal}'")

        fg_win = controller.get_foreground_window()
        screen_w, screen_h = vision.get_screen_size()
        initial_context = (
            f"MỤC TIÊU CỦA NGƯỜI DÙNG: {goal}\n\n"
            f"Thông tin hệ thống:\n"
            f"- Cửa sổ đang mở: {fg_win.get('title', 'Không xác định')}\n"
            f"- Kích thước màn hình: {screen_w} x {screen_h} pixels.\n"
            f"Hãy bắt đầu phân tích và gọi công cụ phù hợp để thực thi mục tiêu."
        )

        messages = [
            {"role": "user", "content": initial_context}
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

            self.set_status(f"Bước {step}/{max_steps}: Claude đang suy luận...")
            self.log("STEP", f"=== BƯỚC {step} (Claude) ===")

            try:
                response = self.client.messages.create(
                    model=model_name,
                    max_tokens=2048,
                    system=SYSTEM_INSTRUCTION,
                    tools=CLAUDE_TOOLS_SCHEMA,
                    messages=messages
                )
            except Exception as e:
                err_msg = str(e)
                self.log("ERROR", f"Lỗi Claude API: {err_msg}")
                self.set_status("Lỗi API Claude")
                return {"success": False, "error": err_msg}

            # Lưu response vào messages
            messages.append({"role": "assistant", "content": response.content})

            # Tách suy nghĩ (text / thinking) và tool calls
            tool_use_blocks = []
            for block in response.content:
                if block.type == "thinking":
                    thinking_content = getattr(block, "thinking", "")
                    if thinking_content.strip():
                        self.log("THOUGHT", f"🤔 [Suy nghĩ sâu]: {thinking_content.strip()}")
                elif block.type == "text" and getattr(block, "text", "").strip():
                    text_content = block.text.strip()
                    self.log("THOUGHT", text_content)
                    if "hoàn thành" in text_content.lower() or "đã xong" in text_content.lower():
                        final_summary = text_content
                elif block.type == "tool_use":
                    tool_use_blocks.append(block)

            if not tool_use_blocks:
                if final_summary:
                    task_finished = True
                    break
                messages.append({
                    "role": "user",
                    "content": "Hãy gọi công cụ tiếp theo hoặc gọi finish_task nếu bạn đã hoàn thành nhiệm vụ."
                })
                continue

            # Thực thi các tool calls
            tool_results = []
            for block in tool_use_blocks:
                fn_name = block.name
                fn_args = block.input or {}
                tool_id = block.id

                if safety.is_stopped():
                    reason = safety.get_stop_reason()
                    self.log("STOP", f"ĐÃ DỪNG KHẨN CẤP: {reason}")
                    self.set_status("Đã dừng")
                    return {"success": False, "error": reason}

                args_preview = ", ".join(f"{k}='{v}'" if isinstance(v, str) else f"{k}={v}" for k, v in fn_args.items())
                self.log("ACTION", f"⚡ {fn_name}({args_preview})")
                self.set_status(f"Claude thực thi: {fn_name}")

                extra_image_b64 = None
                if fn_name == "finish_task":
                    task_finished = True
                    final_summary = fn_args.get("summary", "Đã hoàn thành nhiệm vụ.")
                    tool_res_str = f"Nhiệm vụ hoàn thành: {final_summary}"
                elif fn_name == "take_screenshot_to_see":
                    try:
                        img_bytes, sw, sh = vision.capture_screen_bytes(max_dimension=1280, quality=75)
                        extra_image_b64 = base64.b64encode(img_bytes).decode("utf-8")
                        tool_res_str = f"Đã chụp ảnh màn hình ({sw}x{sh} px). Ảnh đính kèm vào tầm nhìn AI."
                    except Exception as ex:
                        tool_res_str = f"Lỗi chụp màn hình: {ex}"
                elif fn_name in TOOL_MAP:
                    try:
                        tool_func = TOOL_MAP[fn_name]
                        tool_res_str = str(tool_func(**fn_args))
                    except Exception as ex:
                        tool_res_str = f"Lỗi thực thi công cụ {fn_name}: {ex}"
                else:
                    tool_res_str = f"Lỗi: Không tìm thấy công cụ '{fn_name}'"

                self.log("OBSERVATION", f"👁️ Kết quả: {tool_res_str}")

                if extra_image_b64:
                    tool_content = [
                        {"type": "text", "text": tool_res_str},
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": extra_image_b64
                            }
                        }
                    ]
                else:
                    tool_content = tool_res_str

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": tool_content
                })

            messages.append({
                "role": "user",
                "content": tool_results
            })

            if task_finished:
                break

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
