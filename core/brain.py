"""
BỘ NÃO GEMINI REACT (COGNITIVE ENGINE & REASONING LOOP)
Điều phối các tầng tự động hóa: Lập kế hoạch -> Thực thi -> Tự kiểm tra -> Hoàn thành.
Kiến trúc State-Preserving Multi-Turn History, tự động xoay vòng nhiều API Key (Key Pool)
và tự động chuyển mô hình dự phòng khi gặp 429/503.

Tối ưu token:
- System prompt cố định + tiền tố lịch sử ổn định -> tận dụng implicit caching của Gemini.
- Chỉ giữ N ảnh chụp màn hình gần nhất; kết quả công cụ bị cắt gọn; lịch sử cũ được nén theo đợt.
"""

import time
from collections import deque

from google import genai
from google.genai import types

from config import config
from core.safety import safety
from core.controller import controller
from core.vision import vision
from core.tools import ALL_TOOLS, dispatch_tool, reset_run_state, select_tools
from core.guard import RunGuard, skill_hint
from core.prompts import SYSTEM_INSTRUCTION  # noqa: F401  (giữ để tương thích import cũ)
from core.context import (
    IMAGE_PLACEHOLDER,
    COMPACTED_RESULT_CHARS,
    KEEP_RECENT_MESSAGES,
    truncate_text,
    format_args,
    one_line,
)

FALLBACK_MODELS = [
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash",
    "gemini-3.8-flash",
    "gemini-3.7-flash",
]

_THINKING_LEVELS = {"minimal": "MINIMAL", "low": "LOW", "medium": "MEDIUM", "high": "HIGH"}

_MEDIA_RESOLUTION = {
    "low": "MEDIA_RESOLUTION_LOW",
    "medium": "MEDIA_RESOLUTION_MEDIUM",
    "high": "MEDIA_RESOLUTION_HIGH",
}

NUDGE_TEXT = "Hãy gọi công cụ tiếp theo hoặc gọi finish_task nếu bạn đã làm xong."


def _classify_error(e: Exception) -> str:
    """Phân loại lỗi API: quota | unavailable | fatal | other."""
    s = str(e).lower()
    code = getattr(e, "code", None) or getattr(e, "status_code", None)
    if code == 429 or "429" in s or "quota" in s or "resource_exhausted" in s:
        return "quota"
    if code in (500, 502, 503, 504) or any(k in s for k in ("503", "unavailable", "overloaded", "deadline", "timed out")):
        return "unavailable"
    if code in (401, 403) or any(k in s for k in ("api key not valid", "api_key_invalid", "permission_denied", "unauthenticated")):
        return "fatal"
    return "other"


# =====================================================================
# Quản lý lịch sử Gemini (list[types.Content])
# =====================================================================

def prune_gemini_images(contents: list, keep: int) -> int:
    """Thay ảnh cũ (ngoài `keep` ảnh gần nhất) bằng ghi chú chữ."""
    seen = pruned = 0
    for content in reversed(contents):
        if content.role != "user" or not content.parts:
            continue
        for i in range(len(content.parts) - 1, -1, -1):
            if getattr(content.parts[i], "inline_data", None) is not None:
                seen += 1
                if seen > keep:
                    content.parts[i] = types.Part.from_text(text=IMAGE_PLACEHOLDER)
                    pruned += 1
    return pruned


def _gemini_history_chars(contents: list) -> int:
    total = 0
    for content in contents:
        for p in content.parts or []:
            if getattr(p, "text", None):
                total += len(p.text)
            elif getattr(p, "function_response", None) is not None:
                total += len(str(p.function_response.response))
            elif getattr(p, "function_call", None) is not None:
                total += len(str(p.function_call.args))
            elif getattr(p, "inline_data", None) is not None:
                total += 4000
    return total


def compact_gemini_history(contents: list, max_chars: int) -> int:
    """Khi lịch sử vượt ngưỡng, nén kết quả công cụ cũ (ngoài các lượt gần nhất) về vài trăm ký tự."""
    if _gemini_history_chars(contents) <= max_chars:
        return 0
    compacted = 0
    for content in contents[:-KEEP_RECENT_MESSAGES]:
        if content.role != "user":
            continue
        for p in content.parts or []:
            fr = getattr(p, "function_response", None)
            if fr is None or not isinstance(fr.response, dict):
                continue
            result = fr.response.get("result")
            if isinstance(result, str) and len(result) > COMPACTED_RESULT_CHARS:
                fr.response = {"result": truncate_text(result, COMPACTED_RESULT_CHARS)}
                compacted += 1
    return compacted


class GeminiBrain:
    def __init__(self, log_callback=None, status_callback=None):
        self.log_callback = log_callback or (lambda tag, msg: print(f"[{tag}] {msg}"))
        self.status_callback = status_callback or (lambda st: None)
        self.client = None
        self.key_index = 0
        self._thinking_ok = True

    def _init_client(self):
        """Khởi tạo Google GenAI Client với API Key hiện tại"""
        keys = config.gemini_api_keys
        if not keys:
            raise ValueError(
                "Chưa cấu hình GEMINI_API_KEY! Hãy nhập API Key trong phần Cài Đặt hoặc file .env."
            )
        active_key = keys[self.key_index % len(keys)]
        if self.client is None or getattr(self, "_client_key", None) != active_key:
            self.client = genai.Client(api_key=active_key)   # dùng lại client giữa các nhiệm vụ con
            self._client_key = active_key
        return active_key

    def rotate_key(self) -> bool:
        """Tự động chuyển sang API Key tiếp theo nếu có nhiều key được cấu hình"""
        keys = config.gemini_api_keys
        if len(keys) > 1:
            self.key_index = (self.key_index + 1) % len(keys)
            self.client = genai.Client(api_key=keys[self.key_index])
            self._client_key = keys[self.key_index]
            self.log("INFO", f"🔄 Tự động chuyển sang API Key dự phòng #{self.key_index + 1}...")
            return True
        return False

    def log(self, tag: str, msg: str):
        if self.log_callback:
            self.log_callback(tag, msg)

    def set_status(self, status: str):
        if self.status_callback:
            self.status_callback(status)

    def _build_config(self, tools=None) -> types.GenerateContentConfig:
        kwargs = dict(
            system_instruction=SYSTEM_INSTRUCTION,
            temperature=0.2,
            tools=tools if tools is not None else ALL_TOOLS,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )
        media_res = _MEDIA_RESOLUTION.get(config.gemini_media_resolution)
        if media_res:
            kwargs["media_resolution"] = media_res
        level = _THINKING_LEVELS.get(config.gemini_thinking_level)
        if level and self._thinking_ok:
            kwargs["thinking_config"] = types.ThinkingConfig(thinking_level=level)
        return types.GenerateContentConfig(**kwargs)

    def _generate(self, contents, tools, models):
        """
        Gọi API với chiến lược dự phòng:
        - 429/quota: xoay API key (tối đa số key), rồi mới chuyển model.
        - 503/quá tải: thử lại cùng model 1 lần sau 1.5s, rồi chuyển model.
        - Lỗi xác thực (401/403): dừng ngay, không phí request.
        """
        n_keys = max(1, len(config.gemini_api_keys))
        last_err = ""
        for model in models:
            rotations = 0
            retried = False
            while True:
                if safety.is_stopped():
                    return None, None, safety.get_stop_reason()
                try:
                    resp = self.client.models.generate_content(
                        model=model, contents=contents, config=self._build_config(tools))
                    return model, resp, ""
                except Exception as e:
                    kind = _classify_error(e)
                    last_err = str(e)
                    if kind == "fatal":
                        raise
                    if self._thinking_ok and "thinking" in last_err.lower():
                        # Mô hình không hỗ trợ mức suy nghĩ -> tắt tùy chọn và thử lại cùng mô hình
                        self._thinking_ok = False
                        self.log("INFO", "Mô hình không hỗ trợ GEMINI_THINKING_LEVEL, bỏ qua tùy chọn này.")
                        continue
                    if kind == "quota" and rotations < n_keys - 1 and self.rotate_key():
                        rotations += 1
                        continue
                    if kind == "unavailable" and not retried:
                        retried = True
                        time.sleep(1.5)
                        continue
                    label = {"quota": "Hết hạn ngạch 429", "unavailable": "Bận 503"}.get(kind, "Lỗi")
                    self.log("WARN", f"Mô hình {model} ({label}): {one_line(last_err, 160)} → thử mô hình tiếp theo...")
                    break
        return None, None, last_err

    # =================================================================
    # API CÔNG KHAI
    # =================================================================
    def run_task(self, goal: str) -> dict:
        """Chế độ độc lập: Gemini vừa suy nghĩ vừa thao tác cho toàn bộ mục tiêu."""
        safety.reset()
        safety.start_hotkey_listener()
        self.log("INFO", f"Bắt đầu nhiệm vụ: '{goal}'")
        context = (
            f"MỤC TIÊU CỦA NGƯỜI DÙNG: {goal}\n\n"
            f"{self._system_info()}"
            f"{skill_hint(goal)}"
            f"Hãy bắt đầu suy nghĩ và gọi các công cụ phù hợp nhất để hoàn thành mục tiêu."
        )
        result = self._run_loop(context, config.max_steps, standalone=True, goal=goal)
        if result.get("success"):
            self.set_status("Hoàn thành xuất sắc!")
            self.log("SUCCESS", f"🎉 {result['summary']}")
        elif not result.get("stopped"):
            self.log("WARN", result.get("error") or result.get("summary") or "Chưa hoàn thành.")
        return result

    def run_subtask(self, instruction: str, success_criteria: str = "", max_steps: int = 15, checks=None) -> dict:
        """
        Chế độ "tay chân": thực hiện 1 nhiệm vụ con do bộ não điều phối (Claude) giao,
        rồi trả về báo cáo ngắn gọn. Không reset trạng thái dừng khẩn cấp của lượt chạy cha.
        """
        context = (
            f"NHIỆM VỤ CON (do bộ não điều phối giao): {instruction}\n"
            f"Tiêu chí hoàn thành: {success_criteria or 'tự xác định hợp lý theo nhiệm vụ con'}\n\n"
            f"{self._system_info()}"
            f"{skill_hint(instruction)}"
            "Chỉ làm đúng nhiệm vụ con này, không làm thêm việc khác. Khi xong hoặc bế tắc, gọi finish_task với "
            "summary nêu RÕ và NGẮN: đã làm gì, kết quả đã kiểm chứng thực tế, và mọi dữ liệu bộ não cần "
            "(đường dẫn, giá trị, nội dung đọc được, lỗi gặp phải). is_success=False nếu chưa đạt tiêu chí."
        )
        return self._run_loop(context, max(1, max_steps), standalone=False, goal=instruction, checks=checks)

    # =================================================================
    # VÒNG LẶP REACT DÙNG CHUNG
    # =================================================================
    def _system_info(self) -> str:
        fg_win = controller.get_foreground_window()
        screen_w, screen_h = vision.get_screen_size()
        return (
            f"Thông tin hệ thống:\n"
            f"- Cửa sổ đang mở: {fg_win.get('title', 'Không xác định')}\n"
            f"- Kích thước màn hình: {screen_w} x {screen_h} pixels.\n"
        )

    def _run_loop(self, initial_context: str, max_steps: int, standalone: bool, goal: str = "", checks=None) -> dict:
        """
        Trả về dict: success, summary, error, steps, usage, trace (vài thao tác cuối), notes, stopped.
        """
        usage_total = {"in": 0, "cached": 0, "out": 0}
        trace = deque(maxlen=6)
        guard = RunGuard(checks=checks)

        def result(success: bool, summary: str = "", error: str = "", stopped: bool = False, steps: int = 0,
                   api_error: bool = False):
            self.log(
                "INFO",
                f"📊 Gemini: vào {usage_total['in']} (cache {usage_total['cached']}) · ra {usage_total['out']} · {steps} bước",
            )
            return {
                "success": success, "summary": summary, "error": error, "stopped": stopped,
                "steps": steps, "usage": dict(usage_total), "trace": list(trace), "notes": guard.notes,
                "api_error": api_error, "checks": guard.check_report,
            }

        try:
            self._init_client()
        except Exception as e:
            self.log("ERROR", str(e))
            self.set_status("Lỗi API Key")
            return result(False, error=str(e), api_error=True)

        extra_tools: set = set()
        active_tools = select_tools(goal, extra_tools)
        reset_run_state()

        # Mô hình người dùng chọn luôn được ưu tiên đầu tiên (kể cả khi không nằm trong danh sách dự phòng)
        current_model = config.gemini_model or FALLBACK_MODELS[0]
        fallback_models = [current_model] + [m for m in FALLBACK_MODELS if m != current_model]
        if standalone:
            self.log("INFO", f"Mô hình khởi động: {current_model}")

        contents: list[types.Content] = [
            types.Content(role="user", parts=[types.Part.from_text(text=initial_context)])
        ]
        step_label = "BƯỚC" if standalone else "GEMINI · BƯỚC"

        def stopped_result(step):
            reason = safety.get_stop_reason()
            self.log("STOP", f"ĐÃ DỪNG KHẨN CẤP: {reason}")
            self.set_status("Đã dừng")
            return result(False, error=reason, stopped=True, steps=step)

        step = 0
        while step < max_steps:
            step += 1
            if safety.is_stopped():
                return stopped_result(step)

            self.set_status(f"Bước {step}/{max_steps}: Gemini đang thực thi ({current_model})...")
            self.log("STEP", f"=== {step_label} {step} ===")

            # Giữ ngữ cảnh gọn trước mỗi request
            prune_gemini_images(contents, config.keep_screenshots)
            if compact_gemini_history(contents, config.history_compact_chars):
                self.log("INFO", "🗜️ Đã nén các kết quả công cụ cũ để tiết kiệm token.")

            candidate_list = [current_model] + [m for m in fallback_models if m != current_model]
            try:
                used_model, response, err = self._generate(contents, active_tools, candidate_list)
            except Exception as e:
                self.log("ERROR", f"Lỗi xác thực Gemini API: {e}")
                self.set_status("Lỗi API Key")
                return result(False, error=str(e), steps=step, api_error=True)

            if safety.is_stopped():
                return stopped_result(step)
            if response is None:
                self.log("ERROR", f"Tất cả các mô hình Gemini đều không phản hồi. Lỗi cuối: {one_line(err, 200)}")
                self.set_status("Lỗi API/Hết Quota")
                return result(False, error=f"Không thể nhận phản hồi từ Gemini API: {one_line(err, 200)}", steps=step,
                              api_error=True)
            current_model = used_model

            um = getattr(response, "usage_metadata", None)
            if um is not None:
                p_in = um.prompt_token_count or 0
                p_cached = um.cached_content_token_count or 0
                p_out = (um.candidates_token_count or 0) + (getattr(um, "thoughts_token_count", 0) or 0)
                usage_total["in"] += p_in
                usage_total["cached"] += p_cached
                usage_total["out"] += p_out
                self.log("INFO", f"📊 Token: vào {p_in} (cache {p_cached}) · ra {p_out}")

            candidate = response.candidates[0] if response.candidates else None
            model_content = getattr(candidate, "content", None)
            if model_content is None or not model_content.parts:
                reason = getattr(candidate, "finish_reason", None) if candidate else "không có candidate"
                self.log("WARN", f"Phản hồi rỗng từ mô hình ({reason}). Yêu cầu thử lại.")
                contents.append(types.Content(role="user", parts=[types.Part.from_text(text=NUDGE_TEXT)]))
                continue

            contents.append(model_content)

            texts = [p.text for p in model_content.parts if getattr(p, "text", None) and not getattr(p, "thought", False)]
            thought_text = "\n".join(texts).strip()
            if thought_text:
                self.log("THOUGHT", thought_text)

            function_calls = response.function_calls
            if not function_calls:
                low = thought_text.lower()
                if "hoàn thành" in low or "đã xong" in low:
                    return result(True, summary=thought_text, steps=step)
                contents.append(types.Content(role="user", parts=[types.Part.from_text(text=NUDGE_TEXT)]))
                continue

            function_response_parts = []
            image_parts = []
            finished = None
            for fc in function_calls:
                if safety.is_stopped():
                    return stopped_result(step)

                fn_name = fc.name
                fn_args = dict(fc.args or {})
                self.log("ACTION", f"⚡ {fn_name}({format_args(fn_args)})")
                self.set_status(f"Gemini thực thi: {fn_name}")

                outcome = dispatch_tool(fn_name, fn_args, config.max_tool_result_chars, guard=guard)
                if outcome.tools_added and not outcome.tools_added <= extra_tools:
                    extra_tools |= outcome.tools_added
                    active_tools = select_tools(goal, extra_tools)
                if outcome.finished:
                    finished = outcome
                if outcome.image:
                    image_parts.append(types.Part.from_bytes(data=outcome.image, mime_type="image/jpeg"))

                self.log("OBSERVATION", f"👁️ Kết quả: {outcome.text}")
                trace.append(f"{fn_name}({format_args(fn_args, 40)}) → {one_line(outcome.text, 160)}")
                function_response_parts.append(
                    types.Part.from_function_response(name=fn_name, response={"result": outcome.text})
                )

            if finished is not None:
                return result(finished.success, summary=finished.summary,
                              error="" if finished.success else finished.summary, steps=step)

            notes = guard.pending_notes_text()
            extra = [types.Part.from_text(text=notes)] if notes else []
            contents.append(types.Content(role="user", parts=function_response_parts + image_parts + extra))

        self.set_status("Hết số bước tối đa")
        return result(False, error=f"Đã đạt giới hạn {max_steps} bước nhưng chưa hoàn thành.", steps=step)
