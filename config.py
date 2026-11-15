"""
Quản lý cấu hình cho Gemini AutoPilot
Hỗ trợ đọc/ghi trực tiếp từ file .env
"""

import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"

# Nạp file .env nếu có
load_dotenv(dotenv_path=ENV_PATH, override=True)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)).strip())
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)).strip())
    except (TypeError, ValueError):
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in ("true", "1", "yes")


class Config:
    def __init__(self):
        self.reload()

    def reload(self):
        load_dotenv(dotenv_path=ENV_PATH, override=True)
        self.gemini_api_key_raw = os.getenv("GEMINI_API_KEY", "").strip()
        # Hỗ trợ danh sách nhiều API Key (phân cách bằng dấu phẩy) để tự động xoay vòng khi hết hạn ngạch
        self.gemini_api_keys = [k.strip() for k in self.gemini_api_key_raw.split(",") if k.strip()]
        self.gemini_api_key = self.gemini_api_keys[0] if self.gemini_api_keys else ""
        self.gemini_model = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite").strip()
        
        # Cấu hình AI Provider (Gemini hoặc Claude)
        self.ai_provider = os.getenv("AI_PROVIDER", "gemini").strip().lower()
        self.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
        self.claude_model = os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5").strip() or "claude-sonnet-5-5"

        self.execution_mode = os.getenv("EXECUTION_MODE", "hybrid").strip()
        self.max_steps = _env_int("MAX_STEPS", 30)
        self.action_delay = _env_float("ACTION_DELAY", 0.4)
        self.safe_mode = _env_bool("SAFE_MODE", True)

        # ---- Tối ưu token & ngữ cảnh hội thoại ----
        # Số ảnh chụp màn hình gần nhất được giữ lại trong lịch sử (ảnh cũ hơn bị thay bằng ghi chú chữ)
        self.keep_screenshots = max(0, _env_int("KEEP_SCREENSHOTS", 1))
        # Độ dài tối đa (ký tự) của mỗi kết quả công cụ gửi lên API
        self.max_tool_result_chars = max(500, _env_int("MAX_TOOL_RESULT_CHARS", 4000))
        # Khi tổng lịch sử vượt ngưỡng này (ký tự), các kết quả công cụ cũ bị nén lại
        self.history_compact_chars = max(8000, _env_int("HISTORY_COMPACT_CHARS", 24000))
        # Giới hạn token đầu ra mỗi lượt suy luận
        self.max_output_tokens = max(256, _env_int("MAX_OUTPUT_TOKENS", 2048))
        # ---- Ngân sách & ngắt mạch Gemini (chống "đốt sạch" hạn ngạch) ----
        # Token đầu ra tối đa mỗi lượt Gemini (bao gồm phần suy nghĩ)
        self.gemini_max_output_tokens = max(512, _env_int("GEMINI_MAX_OUTPUT_TOKENS", 3072))
        # Tổng số lượt gọi / tổng token Gemini cho MỘT nhiệm vụ (cộng dồn mọi nhiệm vụ con). 0 = không giới hạn
        self.gemini_max_calls = max(0, _env_int("GEMINI_MAX_CALLS", 40))
        self.gemini_max_tokens = max(0, _env_int("GEMINI_MAX_TOKENS", 400000))
        # Hết hạn ngạch ngày ở mô hình chính -> có tự chuyển sang mô hình dự phòng không
        self.gemini_model_fallback = _env_bool("GEMINI_MODEL_FALLBACK", True)
        # Ảnh chụp màn hình: cạnh dài tối đa, chất lượng JPEG, có lưu ra đĩa hay không
        self.screenshot_max_dim = max(640, _env_int("SCREENSHOT_MAX_DIM", 1280))
        self.screenshot_quality = min(95, max(30, _env_int("SCREENSHOT_QUALITY", 70)))
        self.save_screenshots = _env_bool("SAVE_SCREENSHOTS", False)
        # ---- Chế độ kết hợp (AI_PROVIDER=hybrid): Claude lập kế hoạch, Gemini thực thi ----
        self.planner_max_rounds = max(1, _env_int("PLANNER_MAX_ROUNDS", 8))      # số lượt gọi Claude tối đa
        self.planner_max_tokens = max(256, _env_int("PLANNER_MAX_TOKENS", 1024))  # token đầu ra mỗi lượt Claude
        self.executor_max_steps = max(1, _env_int("EXECUTOR_MAX_STEPS", 15))     # bước tối đa mỗi nhiệm vụ con
        self.report_max_chars = max(300, _env_int("REPORT_MAX_CHARS", 1500))     # độ dài báo cáo gửi Claude
        # Chiến lược hybrid: "escalate" = Gemini thử trước, chỉ gọi Claude khi chưa đạt (rẻ nhất);
        # "plan" = luôn để Claude lập kế hoạch từ đầu.
        self.hybrid_strategy = os.getenv("HYBRID_STRATEGY", "escalate").strip().lower()
        self.escalation_steps = max(1, _env_int("ESCALATION_STEPS", 12))         # bước Gemini tự thử trước khi leo thang
        self.max_claude_tokens = max(0, _env_int("MAX_CLAUDE_TOKENS", 60000))     # ngân sách token Claude mỗi nhiệm vụ (0 = không giới hạn)

        # ---- Tốc độ & logic cục bộ ----
        self.persistent_shell = _env_bool("PERSISTENT_SHELL", True)   # giữ sống 1 phiên PowerShell
        self.adaptive_wait = _env_bool("ADAPTIVE_WAIT", True)         # chờ theo trạng thái cửa sổ thay vì sleep cố định
        self.router_enabled = _env_bool("ROUTER", True)               # xử lý lệnh quen thuộc không cần AI
        self.recipes_enabled = _env_bool("RECIPES", True)             # lưu & chạy lại cách làm đã thành công
        self.runlog_enabled = _env_bool("RUNLOG", True)               # ghi logs/runs.jsonl
        # Mức suy nghĩ của Gemini: "", minimal, low, medium, high (thấp = ít token đầu ra, nhanh hơn)
        self.gemini_thinking_level = os.getenv("GEMINI_THINKING_LEVEL", "low").strip().lower()
        # Độ phân giải ảnh Gemini: "" (mặc định API), "low", "medium", "high"
        self.gemini_media_resolution = os.getenv("GEMINI_MEDIA_RESOLUTION", "").strip().lower()

    def save(self, **kwargs):
        """Lưu các giá trị cập nhật vào file .env"""
        current_env = {}
        if ENV_PATH.exists():
            with open(ENV_PATH, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        current_env[k.strip()] = v.strip()

        # Cập nhật giá trị mới
        for k, v in kwargs.items():
            key_upper = k.upper()
            if isinstance(v, bool):
                current_env[key_upper] = "true" if v else "false"
            else:
                current_env[key_upper] = str(v)

        # Ghi lại file .env
        with open(ENV_PATH, "w", encoding="utf-8") as f:
            f.write("# ========================================================\n")
            f.write("# CẤU HÌNH GEMINI AUTOPILOT\n")
            f.write("# ========================================================\n\n")
            for k, v in current_env.items():
                f.write(f"{k}={v}\n")

        self.reload()


config = Config()
