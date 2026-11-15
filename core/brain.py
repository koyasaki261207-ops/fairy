"""
BỘ NÃO GEMINI REACT (COGNITIVE ENGINE & REASONING LOOP)
Điều phối các tầng tự động hóa: Lập kế hoạch -> Thực thi -> Tự kiểm tra -> Hoàn thành.
Kiến trúc State-Preserving Multi-Turn History, tự động xoay vòng nhiều API Key (Key Pool)
và tự động chuyển mô hình dự phòng khi gặp 429/503.

Tối ưu token:
- System prompt cố định + tiền tố lịch sử ổn định -> tận dụng implicit caching của Gemini.
- Chỉ giữ N ảnh chụp màn hình gần nhất; kết quả công cụ bị cắt gọn; lịch sử cũ được nén theo đợt.
"""

import re
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
MAX_IDLE_TURNS = 2          # số lượt liên tiếp mô hình không gọi công cụ trước khi dừng (tránh đốt request)
MAX_RATE_WAIT_S = 45.0      # 429 theo phút: chờ tối đa chừng này rồi thử lại cùng mô hình
EXHAUSTED_TTL_S = 3600.0    # mô hình hết hạn ngạch ngày bị bỏ qua trong 1 giờ (không gõ lại mỗi bước/nhiệm vụ con)


def _classify_error(e: Exception) -> str:
    """Phân loại lỗi API: quota | unavailable | fatal | notfound | other."""
    s = str(e).lower()
    code = getattr(e, "code", None) or getattr(e, "status_code", None)
    if code == 429 or "429" in s or "quota" in s or "resource_exhausted" in s:
        return "quota"
    if code in (500, 502, 503, 504) or any(k in s for k in ("503", "unavailable", "overloaded", "deadline", "timed out")):
        return "unavailable"
    if code in (401, 403) or any(k in s for k in ("api key not valid", "api_key_invalid", "permission_denied", "unauthenticated")):
        return "fatal"
    if code == 404 or "not_found" in s or "is not found" in s:
        return "notfound"
    return "other"


def quota_info(err: str) -> tuple[bool, float | None]:
    """
    Đọc thông báo 429 của Gemini: (hết hạn ngạch NGÀY?, số giây nên chờ theo RetryInfo).
    Hạn ngạch theo phút (RPM/TPM) chỉ cần chờ vài giây; hạn ngạch ngày (RPD) thì chờ cũng vô ích.
    """
    s = str(err)
    per_day = bool(re.search(r"per\s*day|perday|daily", s, re.I))
    m = re.search(r"retry[_ ]?delay['\"]?\s*[:=]\s*['\"]?(\d+(?:\.\d+)?)s", s, re.I) \
        or re.search(r"retry in (\d+(?:\.\d+)?)\s*s", s, re.I)
    return per_day, (float(m.group(1)) if m else None)


def _sleep_interruptible(seconds: float) -> bool:
    """Ngủ theo nhịp nhỏ để nút dừng khẩn cấp vẫn có tác dụng. Trả về False nếu bị dừng."""
    end = time.time() + max(0.0, seconds)
    while time.time() < end:
        if safety.is_stopped():
            return False
        time.sleep(min(0.25, end - time.time()) if end > time.time() else 0)
    return True


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
        self._exhausted: dict[str, float] = {}   # mô hình -> thời điểm bị đánh dấu hết hạn ngạch ngày
        self.begin_task()

    def begin_task(self):
        """Đặt lại ngân sách dùng chung cho MỘT nhiệm vụ của người dùng (mọi nhiệm vụ con cộng dồn vào đây)."""
        self.calls_used = 0
        self.tokens_used = 0

    def _budget_error(self) -> str:
        if config.gemini_max_calls and self.calls_used >= config.gemini_max_calls:
            return (f"Đã dùng hết ngân sách {config.gemini_max_calls} lượt gọi Gemini cho nhiệm vụ này "
                    "(GEMINI_MAX_CALLS). Dừng để giữ hạn ngạch API.")
        if config.gemini_max_tokens and self.tokens_used >= config.gemini_max_tokens:
            return (f"Đã dùng hết ngân sách {config.gemini_max_tokens} token Gemini cho nhiệm vụ này "
                    "(GEMINI_MAX_TOKENS). Dừng để giữ hạn ngạch API.")
        return ""

    def _is_exhausted(self, model: str) -> bool:
        t = self._exhausted.get(model)
        if t is None:
            return False
        if time.time() - t > EXHAUSTED_TTL_S:
            self._exhausted.pop(model, None)
            return False
        return True

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
            max_output_tokens=config.gemini_max_output_tokens,
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
        Gọi API với chiến lược dự phòng (ngắt mạch, không quét mù mọi key × mọi mô hình):
        - 429 theo phút (có retryDelay ngắn): CHỜ đúng retryDelay rồi thử lại cùng mô hình (tối đa 2 lần).
        - 429 hạn ngạch ngày: xoay API key; hết key -> đánh dấu mô hình đã cạn (bỏ qua ở các bước/nhiệm vụ
          con sau) rồi mới chuyển mô hình dự phòng (nếu GEMINI_MODEL_FALLBACK=true).
        - 503/quá tải: thử lại cùng mô hình 1 lần sau 1.5s, rồi chuyển mô hình.
        - 404 mô hình không tồn tại: chuyển mô hình. Lỗi 400 khác: dừng ngay (đổi mô hình cũng hỏng y hệt).
        - Lỗi xác thực (401/403): dừng ngay, không phí request.
        """
        n_keys = max(1, len(config.gemini_api_keys))
        last_err = ""
        # Tắt dự phòng -> chỉ đúng mô hình chính (chọn TRƯỚC khi lọc, để không trượt sang mô hình khác)
        pool = models if config.gemini_model_fallback else models[:1]
        candidates = [m for m in pool if not self._is_exhausted(m)]
        if not candidates:
            return None, None, "Mô hình Gemini đã hết hạn ngạch ngày (thử lại sau hoặc thêm API key khác)."
        for model in candidates:
            rotations = 0
            retried = False
            waits = 0
            while True:
                if safety.is_stopped():
                    return None, None, safety.get_stop_reason()
                budget_err = self._budget_error()   # tính cả lần thử lại / xoay key, không chỉ lần thành công
                if budget_err:
                    return None, None, budget_err
                self.calls_used += 1
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
                    if kind == "quota":
                        per_day, delay = quota_info(last_err)
                        if not per_day and waits < 2 and (delay is None or delay <= MAX_RATE_WAIT_S):
                            waits += 1
                            wait_s = (delay if delay is not None else 5.0 * waits) + 0.5
                            self.log("WARN", f"Gemini giới hạn tốc độ (429/phút) → chờ {wait_s:.0f}s rồi thử lại {model}...")
                            self.set_status(f"Chờ hạn ngạch Gemini {wait_s:.0f}s...")
                            if not _sleep_interruptible(wait_s):
                                return None, None, safety.get_stop_reason()
                            continue
                        if rotations < n_keys - 1 and self.rotate_key():
                            rotations += 1
                            continue
                        if per_day:   # chỉ ghi nhớ khi chắc chắn hết hạn ngạch NGÀY (giới hạn phút tự hồi)
                            self._exhausted[model] = time.time()
                    elif kind == "unavailable" and not retried:
                        retried = True
                        time.sleep(1.5)
                        continue
                    elif kind == "other":
                        self.log("ERROR", f"Mô hình {model} từ chối yêu cầu: {one_line(last_err, 200)}")
                        return None, None, last_err
                    label = {"quota": "Hết hạn ngạch 429", "unavailable": "Bận 503", "notfound": "Không có mô hình"}.get(kind, "Lỗi")
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
        self.begin_task()
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
        preferred = config.gemini_model or FALLBACK_MODELS[0]
        fallback_models = [preferred] + [m for m in FALLBACK_MODELS if m != preferred]
        # Bỏ qua ngay các mô hình đã biết là hết hạn ngạch ngày (không gõ lại ở mỗi nhiệm vụ con)
        current_model = preferred if not config.gemini_model_fallback else \
            next((m for m in fallback_models if not self._is_exhausted(m)), preferred)
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
        idle_turns = 0
        while step < max_steps:
            step += 1
            if safety.is_stopped():
                return stopped_result(step)
            budget_err = self._budget_error()
            if budget_err:
                self.log("WARN", budget_err)
                self.set_status("Hết ngân sách Gemini")
                return result(False, error=budget_err, steps=step, api_error=True)

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
                self.tokens_used += p_in + p_out
                self.log("INFO", f"📊 Token: vào {p_in} (cache {p_cached}) · ra {p_out}")

            candidate = response.candidates[0] if response.candidates else None
            model_content = getattr(candidate, "content", None)
            if model_content is None or not model_content.parts:
                reason = getattr(candidate, "finish_reason", None) if candidate else "không có candidate"
                idle_turns += 1
                if idle_turns > MAX_IDLE_TURNS:
                    return result(False, error=f"Mô hình trả về rỗng {idle_turns} lần liên tiếp ({reason}).", steps=step)
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
                idle_turns += 1
                if idle_turns > MAX_IDLE_TURNS:
                    return result(False, summary=thought_text,
                                  error=f"Mô hình {idle_turns} lượt liên tiếp không gọi công cụ.", steps=step)
                contents.append(types.Content(role="user", parts=[types.Part.from_text(text=NUDGE_TEXT)]))
                continue
            idle_turns = 0

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
