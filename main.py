"""
Điểm khởi chạy chính của Gemini AutoPilot
Hỗ trợ cả chế độ Giao diện đồ họa (GUI) và dòng lệnh (CLI).
Các module nặng (GUI, SDK Gemini/Claude) chỉ được import khi thật sự cần.
"""

import argparse
from config import config

CLI_ICONS = {
    "INFO": "ℹ️ ",
    "THOUGHT": "🧠 ",
    "ACTION": "⚡ ",
    "OBSERVATION": "👁️ ",
    "STEP": "📌 ",
    "SUCCESS": "🎉 ",
    "WARN": "⚠️ ",
    "ERROR": "❌ ",
    "STOP": "🛑 "
}


def _make_brain(provider: str, logger):
    if provider == "hybrid":
        from core.hybrid_brain import HybridBrain
        return HybridBrain(log_callback=logger), f"Claude {config.claude_model} + Gemini {config.gemini_model}"
    if provider == "claude":
        from core.claude_brain import ClaudeBrain
        return ClaudeBrain(log_callback=logger), config.claude_model
    from core.brain import GeminiBrain
    return GeminiBrain(log_callback=logger), config.gemini_model


def run_cli(goal: str, provider: str):
    from core.context import truncate_text

    def cli_logger(tag, msg):
        print(f"{CLI_ICONS.get(tag, '• ')}[{tag}] {truncate_text(msg, 1500)}")

    brain, model = _make_brain(provider, cli_logger)

    print("=" * 60)
    print("🤖 AUTOPILOT - CHẾ ĐỘ DÒNG LỆNH (CLI)")
    print("=" * 60)
    print(f"Nhiệm vụ: {goal}")
    print(f"Provider: {provider} · Mô hình: {model}")
    print("Nhấn F8 hoặc Ctrl+Shift+Q bất cứ lúc nào để dừng khẩn cấp.")
    print("-" * 60)

    result = brain.run_task(goal)
    print("-" * 60)
    if result.get("success"):
        print(f"✅ KẾT QUẢ: {result.get('summary')}")
    else:
        print(f"❌ THẤT BẠI: {result.get('error')}")


def main():
    parser = argparse.ArgumentParser(description="Gemini AutoPilot - Trợ lý Tự động hóa Máy tính Thông minh")
    parser.add_argument("--cli", type=str, help="Chạy nhiệm vụ trực tiếp qua dòng lệnh CLI mà không mở GUI")
    parser.add_argument(
        "--provider",
        choices=["gemini", "claude", "hybrid"],
        default=None,
        help="Chọn AI provider cho chế độ CLI (mặc định theo AI_PROVIDER trong .env)",
    )
    args = parser.parse_args()

    if args.cli:
        run_cli(args.cli, args.provider or config.ai_provider)
    else:
        from gui.app import run_gui
        run_gui()


if __name__ == "__main__":
    main()
