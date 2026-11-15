"""
Kiểm thử RunGuard: phát hiện lặp, cổng xác minh, sổ nhớ, gợi ý kỹ năng.
Chạy: python tests/test_guard.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.guard import RunGuard, suggest_skills, is_failure
from core.prompts import SYSTEM_INSTRUCTION


def test_is_failure():
    assert is_failure("Thất bại khi click")
    assert is_failure("Lỗi: không có")
    assert not is_failure("Thành công: đã click")


def test_repeat_detection_warns_on_third_identical_failure():
    g = RunGuard()
    args = {"ref_id": "@a:e1"}
    assert g.observe("desktop_click", args, "Thất bại") == ""
    assert g.observe("desktop_click", args, "Thất bại") == ""
    hint = g.observe("desktop_click", args, "Thất bại")
    assert "CẢNH BÁO VÒNG LẶP" in hint


def test_consecutive_failures_with_different_args():
    g = RunGuard()
    hints = [g.observe("run_powershell", {"command": f"c{i}"}, "Thất bại: x") for i in range(3)]
    assert hints[:2] == ["", ""] and "liên tiếp" in hints[2]
    # Một lần thành công reset bộ đếm
    g.observe("run_powershell", {"command": "ok"}, "Thành công")
    assert g.consec_fail == 0


def test_neutral_tools_never_trigger_loop():
    g = RunGuard()
    for _ in range(6):
        assert g.observe("wait_seconds", {"seconds": 1}, "Đã chờ") == ""


def test_finish_gate_bounces_once_until_observed():
    g = RunGuard()
    g.observe("desktop_click", {"ref_id": "@a:e1"}, "Thành công")
    msg = g.check_finish()
    assert msg and "CHƯA KẾT THÚC" in msg
    assert g.check_finish() is None            # chỉ bật lại 1 lần
    g2 = RunGuard()
    g2.observe("keyboard_shortcut", {"keys": "ctrl+s"}, "Đã nhấn")
    g2.observe("desktop_snapshot", {}, "{...}")  # đã quan sát lại
    assert g2.check_finish() is None


def test_notes_injected_only_when_changed():
    g = RunGuard()
    assert g.pending_notes_text() is None
    g.set_notes("bước 1 xong")
    assert "bước 1 xong" in g.pending_notes_text()
    assert g.pending_notes_text() is None
    g.set_notes("bước 2 xong")
    assert "bước 2" in g.pending_notes_text()
    assert len(RunGuard().set_notes("x" * 5000)) < 60


def test_suggest_skills_matches_goal():
    assert suggest_skills("Chơi game bài Solitaire giúp tôi")[:1] == ["solitaire_rules"]
    assert suggest_skills("tóm tắt tài liệu pdf trong thư mục KTMT")[:1] == ["document_batch_processor"]
    assert suggest_skills("mở notepad") == []


def test_prompt_still_lean():
    assert len(SYSTEM_INSTRUCTION) < 4000 and "update_memory" in SYSTEM_INSTRUCTION


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"OK  {name}")
    print("Tất cả kiểm thử guard đều đạt.")


def test_chess_goal_gets_chess_skill_and_lean_toolset():
    from core.guard import skill_hint
    from core.tools import select_tools
    assert suggest_skills("chơi cờ vua với máy trên lichess") == ["chess_play"]
    hint = skill_hint("chơi cờ vua với máy trên lichess")
    assert "chess_play()" in hint  # gợi ý nhanh được chèn thẳng, khỏi tốn 1 lượt load_skill
    names = {f.__name__ for f in select_tools("chơi cờ vua với máy trên lichess")}
    assert "chess_play" in names and "run_python_code" not in names and len(names) <= 16
    assert "chess_play" not in {f.__name__ for f in select_tools("mở notepad")}


def test_chess_file_task_keeps_file_tools():
    from core.tools import select_tools
    names = {f.__name__ for f in select_tools("đọc file PGN ván cờ vua và giải thích")}
    assert "read_file_content" in names and "chess_play" in names
    assert "load_skill" in {f.__name__ for f in select_tools("chơi cờ vua trên lichess")}
