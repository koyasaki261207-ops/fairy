"""
RUN GUARD - LỚP "TỰ PHẢN TƯ" CHO VÒNG LẶP AGENT (thuần Python, không gọi API thêm)

Tổng hợp các kỹ thuật từ các dự án tham khảo, thực hiện bằng luật cục bộ (0 token thêm):
- Phát hiện lặp / thất bại liên tiếp (Agent-S reflection, Cradle self-reflection)
  -> chèn gợi ý buộc AI đổi chiến thuật thay vì lặp lại.
- Cổng xác minh trước khi kết thúc (Cua: "kiểm tra trạng thái thật", Browser Use judge)
  -> nếu hành động giao diện cuối cùng chưa được quan sát lại, bật lại 1 lần để AI tự kiểm tra.
- Sổ nhớ làm việc (Cradle task inference/memory)
  -> AI ghi kế hoạch/tiến độ ngắn; sổ luôn được đính vào lượt mới nhất, không bị nén/lược ảnh làm mất.
- Gợi ý kỹ năng (Cradle skill curation) -> chọn skills/*.md liên quan tới mục tiêu.
"""

import json
import re
import unicodedata
from collections import deque
from pathlib import Path

SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"

# Công cụ thao tác giao diện (cần xác minh lại bằng quan sát)
UI_ACTION_TOOLS = {
    "desktop_click", "desktop_type", "desktop_focus_window", "ui_click", "ui_type",
    "mouse_click_coords", "mouse_double_click", "mouse_right_click", "mouse_drag_and_drop",
    "mouse_scroll_page", "keyboard_shortcut", "type_vietnamese_text",
    "solitaire_move_by_column", "solitaire_draw_card",
}
# Công cụ quan sát trạng thái
OBSERVE_TOOLS = {
    "desktop_snapshot", "desktop_find", "take_screenshot_to_see", "inspect_active_window",
}
# Công cụ không tính vào phát hiện lặp (chờ/đọc/tra cứu hợp lệ lặp lại)
NEUTRAL_TOOLS = {"wait_seconds", "update_memory", "list_skills", "load_skill"}

FAILURE_PREFIXES = (
    "thất bại", "lỗi", "từ chối", "snapshot thất bại", "không thể", "không tìm thấy",
    "không thấy", "[lỗi", "không được gọi",
)
MAX_NOTES_CHARS = 800


def is_failure(text: str) -> bool:
    return str(text or "").strip().lower().startswith(FAILURE_PREFIXES)


def _signature(name: str, args: dict) -> str:
    try:
        return name + json.dumps(args or {}, sort_keys=True, ensure_ascii=False, default=str)
    except Exception:
        return name + str(args)


class RunGuard:
    def __init__(self, window: int = 8):
        self.recent = deque(maxlen=window)      # (signature, failed)
        self.consec_fail = 0
        self.unverified = False                 # có hành động giao diện chưa quan sát lại
        self.finish_bounced = False
        self.notes = ""
        self._notes_injected = ""
        self.warnings = 0

    # ---------------- Phát hiện lặp / thất bại ----------------
    def observe(self, name: str, args: dict, text: str) -> str:
        """Ghi nhận 1 lần gọi công cụ; trả về gợi ý phản tư (rỗng nếu mọi thứ ổn)."""
        if name in OBSERVE_TOOLS:
            self.unverified = False
        elif name in UI_ACTION_TOOLS:
            self.unverified = True

        if name in NEUTRAL_TOOLS or name == "finish_task":
            return ""

        failed = is_failure(text)
        self.consec_fail = self.consec_fail + 1 if failed else 0
        sig = _signature(name, args)
        self.recent.append((sig, failed))
        repeats = sum(1 for s, _ in self.recent if s == sig)

        hint = ""
        if repeats >= 3 and (failed or name in UI_ACTION_TOOLS or name in OBSERVE_TOOLS):
            hint = (
                f"Bạn đã gọi '{name}' với cùng tham số {repeats} lần gần đây mà chưa tiến triển. "
                "DỪNG lặp lại. Hãy phản tư: điều gì khiến nó không hiệu quả? Đổi chiến thuật "
                "(công cụ khác/tầng khác: PowerShell → Accessibility → ảnh chụp, hoặc tham số khác, "
                "hoặc focus cửa sổ trước)."
            )
        elif self.consec_fail >= 3:
            hint = (
                f"{self.consec_fail} lệnh liên tiếp thất bại. Hãy xem lại thông báo lỗi, kiểm tra "
                "trạng thái thật (desktop_snapshot / take_screenshot_to_see) rồi đổi cách tiếp cận; "
                "nếu thật sự bế tắc, gọi finish_task(is_success=False) nêu rõ lý do."
            )
        if hint:
            self.warnings += 1
            if self.warnings >= 3:
                hint += " (Đã cảnh báo nhiều lần: nếu vẫn không có hướng mới, hãy kết thúc và báo cáo.)"
            return "[CẢNH BÁO VÒNG LẶP] " + hint
        return ""

    # ---------------- Cổng xác minh trước khi kết thúc ----------------
    def check_finish(self) -> str | None:
        """Trả về thông điệp từ chối (1 lần duy nhất) nếu chưa xác minh kết quả; None nếu cho phép."""
        if self.unverified and not self.finish_bounced:
            self.finish_bounced = True
            return (
                "CHƯA KẾT THÚC: hành động giao diện cuối cùng của bạn chưa được kiểm chứng. "
                "Hãy quan sát trạng thái thật (desktop_snapshot hoặc take_screenshot_to_see) để xác nhận "
                "kết quả đúng như mục tiêu, rồi gọi lại finish_task. Nếu kết quả sai, hãy sửa."
            )
        return None

    # ---------------- Sổ nhớ làm việc ----------------
    def set_notes(self, notes: str) -> str:
        notes = (notes or "").strip()
        if len(notes) > MAX_NOTES_CHARS:
            notes = notes[:MAX_NOTES_CHARS] + "…"
        self.notes = notes
        return f"Đã cập nhật sổ nhớ ({len(notes)} ký tự)."

    def pending_notes_text(self) -> str | None:
        """Văn bản sổ nhớ cần đính vào lượt mới nhất (chỉ khi đã thay đổi từ lần đính trước)."""
        if self.notes and self.notes != self._notes_injected:
            self._notes_injected = self.notes
            return f"[SỔ NHỚ LÀM VIỆC - trạng thái hiện tại bạn đã ghi]\n{self.notes}"
        return None


# =====================================================================
# Gợi ý kỹ năng theo mục tiêu (skill curation)
# =====================================================================

def _norm(text: str) -> str:
    text = unicodedata.normalize("NFD", text.lower().replace("đ", "d"))
    return "".join(c for c in text if unicodedata.category(c) != "Mn")


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", _norm(text)) if len(t) >= 3}


def suggest_skills(goal: str, skills_dir: Path = SKILLS_DIR, limit: int = 2) -> list[str]:
    """Chọn kỹ năng liên quan nhất dựa trên dòng 'Từ khóa:' trong file (hoặc tên file) khớp với mục tiêu."""
    if not goal or not Path(skills_dir).exists():
        return []
    goal_tokens = _tokens(goal)
    scored = []
    for f in Path(skills_dir).glob("*.md"):
        try:
            head = f.read_text(encoding="utf-8", errors="replace")[:1500]
        except Exception:
            continue
        kw_line = next((ln for ln in head.splitlines() if _norm(ln).lstrip("*-# ").startswith("tu khoa")), "")
        keywords = _tokens(kw_line) | _tokens(f.stem.replace("_", " "))
        score = len(goal_tokens & keywords)
        if score:
            scored.append((score, f.stem))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [name for _, name in scored[:limit]]


def skill_hint(goal: str) -> str:
    names = suggest_skills(goal)
    if not names:
        return ""
    joined = ", ".join(f"'{n}'" for n in names)
    return f"- Kỹ năng liên quan có sẵn: {joined}. Hãy gọi load_skill trước khi bắt đầu.\n"
