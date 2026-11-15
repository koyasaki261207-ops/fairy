"""
GHI LẠI CÁC BƯỚC THAO TÁC CỦA MỘT LƯỢT CHẠY (cho recipes, nhật ký chạy và tóm tắt vết)
"""

# Công cụ quan sát/tra cứu: không thay đổi trạng thái, bỏ qua khi tạo recipe
OBSERVATION_TOOLS = {
    "desktop_snapshot", "desktop_find", "take_screenshot_to_see", "inspect_active_window", "read_file_content",
    "list_skills", "load_skill", "update_memory", "solitaire_best_move", "validate_card_move", "click_mark",
    "finish_task",
}


class Recorder:
    def __init__(self):
        self.steps: list[dict] = []

    def begin(self):
        self.steps = []

    def record(self, name: str, args: dict, text: str):
        self.steps.append({"tool": name, "args": dict(args or {}), "result": str(text)[:200]})

    def action_steps(self) -> list[dict]:
        return [s for s in self.steps if s["tool"] not in OBSERVATION_TOOLS]


recorder = Recorder()
