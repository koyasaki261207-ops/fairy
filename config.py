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
        self.claude_model = os.getenv("CLAUDE_MODEL", "claude-3-5-sonnet-20241022").strip()

        self.execution_mode = os.getenv("EXECUTION_MODE", "hybrid").strip()
        self.max_steps = int(os.getenv("MAX_STEPS", "30"))
        self.action_delay = float(os.getenv("ACTION_DELAY", "0.4"))
        self.safe_mode = os.getenv("SAFE_MODE", "true").lower() in ("true", "1", "yes")

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
