"""
Điểm khởi chạy chính của Gemini AutoPilot
Hỗ trợ cả chế độ Giao diện đồ họa (GUI) và dòng lệnh (CLI).
"""

import sys
import argparse
from config import config
from gui.app import run_gui
from core.brain import GeminiBrain


def run_cli(goal: str):
    print("=" * 60)
    print("🤖 GEMINI AUTOPILOT - CHẾ ĐỘ DÒNG LỆNH (CLI)")
    print("=" * 60)
    print(f"Nhiệm vụ: {goal}")
    print(f"Mô hình: {config.gemini_model}")
    print("Nhấn F8 hoặc Ctrl+Shift+Q bất cứ lúc nào để dừng khẩn cấp.")
    print("-" * 60)

    def cli_logger(tag, msg):
        icons = {
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
        print(f"{icons.get(tag, '• ')}[{tag}] {msg}")

    brain = GeminiBrain(log_callback=cli_logger)
    result = brain.run_task(goal)
    print("-" * 60)
    if result.get("success"):
        print(f"✅ KẾT QUẢ: {result.get('summary')}")
    else:
        print(f"❌ THẤT BẠI: {result.get('error')}")


def main():
    parser = argparse.ArgumentParser(description="Gemini AutoPilot - Trợ lý Tự động hóa Máy tính Thông minh")
    parser.add_argument("--cli", type=str, help="Chạy nhiệm vụ trực tiếp qua dòng lệnh CLI mà không mở GUI")
    args = parser.parse_args()

    if args.cli:
        run_cli(args.cli)
    else:
        run_gui()


if __name__ == "__main__":
    main()
