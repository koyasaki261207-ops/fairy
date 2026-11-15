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

from google import genai
from google.genai import types

from config import config
from core.safety import safety
from core.controller import controller
from core.vision import vision
from core.tools import ALL_TOOLS, dispatch_tool
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

    def _init_client(self):
        """Khởi tạo Google GenAI Client với API Key hiện tại"""
        keys = config.gemini_api_keys
        if not keys:
            raise ValueError(
                "Chưa cấu hình GEMINI_API_KEY! Hãy nhập API Key trong phần Cài Đặt hoặc file .env."
            )
        active_key = keys[self.key_index % len(keys)]
        self.client = genai.Client(api_key=active_key)
        return active_key

    def rotate_key(self) -> bool:
        """Tự động chuyển sang API Key tiếp theo nếu có nhiều key được cấu hình"""
        keys = config.gemini_api_keys
        if len(keys) > 1:
            self.key_index = (self.key_index + 1) % len(keys)
            self.client = genai.Client(api_key=keys[self.key_index])
            self.log("INFO", f"🔄 Tự động chuyển sang API Key dự phòng #{self.key_index + 1}...")
            return True
        return False

    def log(self, tag: str, msg: str):
        if self.log_callback:
            self.log_callback(tag, msg)

    def set_status(self, status: str):
        if self.status_callback:
            self.status_callback(status)

    def _build_config(self) -> types.GenerateContentConfig:
        kwargs = dict(
            system_instruction=SYSTEM_INSTRUCTION,
            temperature=0.2,
            tools=ALL_TOOLS,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )
        media_res = _MEDIA_RESOLUTION.get(config.gemini_media_resolution)
        if media_res:
            kwargs["media_resolution"] = media_res
        return types.GenerateContentConfig(**kwargs)

    def _generate(self, contents, gen_config, models):
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
                    resp = self.client.models.generate_content(model=model, contents=contents, config=gen_config)
                    return model, resp, ""
                except Exception as e:
                    kind = _classify_error(e)
                    last_err = str(e)
                    if kind == "fatal":
                        raise
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

    def run_task(self, goal: str) -> dict:
        """
        Khởi chạy vòng lặp ReAct giải quyết nhiệm vụ của người dùng.
        """
        safety.reset()
        safety.start_hotkey_listener()

        try:
            self._init_client()
        except Exception as e:
            self.log("ERROR", str(e))
            self.set_status("Lỗi API Key")
            return {"success": False, "error": str(e)}

        self.set_status("Đang khởi động...")
        self.log("INFO", f"Bắt đầu nhiệm vụ: '{goal}'")

        fg_win = controller.get_foreground_window()
        screen_w, screen_h = vision.get_screen_size()
        initial_context = (
            f"MỤC TIÊU CỦA NGƯỜI DÙNG: {goal}\n\n"
            f"Thông tin hệ thống:\n"
            f"- Cửa sổ đang mở: {fg_win.get('title', 'Không xác định')}\n"
            f"- Kích thước màn hình: {screen_w} x {screen_h} pixels.\n"
            f"Hãy bắt đầu suy nghĩ và gọi các công cụ phù hợp nhất để hoàn thành mục tiêu."
        )

        gen_config = self._build_config()

        # Mô hình người dùng chọn luôn được ưu tiên đầu tiên (kể cả khi không nằm trong danh sách dự phòng)
        current_model = config.gemini_model or FALLBACK_MODELS[0]
        fallback_models = [current_model] + [m for m in FALLBACK_MODELS if m != current_model]
        self.log("INFO", f"Mô hình khởi động: {current_model}")

        contents: list[types.Content] = [
            types.Content(role="user", parts=[types.Part.from_text(text=initial_context)])
        ]

        step = 0
        max_steps = config.max_steps
        task_finished = False
        final_summary = ""
        usage_total = {"in": 0, "cached": 0, "out": 0}

        def stopped_result():
            reason = safety.get_stop_reason()
            self.log("STOP", f"ĐÃ DỪNG KHẨN CẤP: {reason}")
            self.set_status("Đã dừng")
            return {"success": False, "error": reason}

        while step < max_steps and not task_finished:
            step += 1
            if safety.is_stopped():
                return stopped_result()

            self.set_status(f"Bước {step}/{max_steps}: Đang suy luận ({current_model})...")
            self.log("STEP", f"=== BƯỚC {step} ===")

            # Giữ ngữ cảnh gọn trước mỗi request
            prune_gemini_images(contents, config.keep_screenshots)
            if compact_gemini_history(contents, config.history_compact_chars):
                self.log("INFO", "🗜️ Đã nén các kết quả công cụ cũ để tiết kiệm token.")

            candidate_list = [current_model] + [m for m in fallback_models if m != current_model]
            try:
                used_model, response, err = self._generate(contents, gen_config, candidate_list)
            except Exception as e:
                self.log("ERROR", f"Lỗi xác thực Gemini API: {e}")
                self.set_status("Lỗi API Key")
                return {"success": False, "error": str(e)}

            if safety.is_stopped():
                return stopped_result()
            if response is None:
                self.log("ERROR", f"Tất cả các mô hình Gemini đều không phản hồi. Lỗi cuối: {one_line(err, 200)}")
                self.set_status("Lỗi API/Hết Quota")
                return {"success": False, "error": "Không thể nhận phản hồi từ Gemini API."}
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
                    task_finished = True
                    final_summary = thought_text
                    break
                contents.append(types.Content(role="user", parts=[types.Part.from_text(text=NUDGE_TEXT)]))
                continue

            function_response_parts = []
            image_parts = []
            for fc in function_calls:
                if safety.is_stopped():
                    return stopped_result()

                fn_name = fc.name
                fn_args = dict(fc.args or {})
                self.log("ACTION", f"⚡ {fn_name}({format_args(fn_args)})")
                self.set_status(f"Đang thực thi: {fn_name}")

                outcome = dispatch_tool(fn_name, fn_args, config.max_tool_result_chars)
                if outcome.finished:
                    task_finished = True
                    final_summary = outcome.summary
                if outcome.image:
                    image_parts.append(types.Part.from_bytes(data=outcome.image, mime_type="image/jpeg"))

                self.log("OBSERVATION", f"👁️ Kết quả: {outcome.text}")
                function_response_parts.append(
                    types.Part.from_function_response(name=fn_name, response={"result": outcome.text})
                )

            if task_finished:
                break

            contents.append(types.Content(role="user", parts=function_response_parts + image_parts))

        self.log(
            "INFO",
            f"📊 Tổng token: vào {usage_total['in']} (cache {usage_total['cached']}) · ra {usage_total['out']} · {step} bước",
        )
        if task_finished:
            self.set_status("Hoàn thành xuất sắc!")
            self.log("SUCCESS", f"🎉 {final_summary}")
            return {"success": True, "summary": final_summary}

        self.set_status("Hết số bước tối đa")
        msg = f"Đã đạt giới hạn {max_steps} bước nhưng chưa hoàn thành toàn bộ."
        self.log("WARN", msg)
        return {"success": False, "error": msg}
