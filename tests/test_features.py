"""
Kiểm thử các tính năng tối ưu logic/tốc độ: shell giữ sống, bộ giải Solitaire, kiểm chứng bằng máy,
router, recipes, nhật ký chạy, snapshot gọn/diff, chọn công cụ động, run_actions, write_text_file.
Chạy: python tests/test_features.py   (cần Windows + PowerShell cho test shell)
"""
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _stubs
_stubs.install()

from core import checks, recipes, router, runlog, solitaire, tools_ext
from core.recorder import recorder
import core.tools as tools


# ---------------- Solitaire ----------------
def test_solitaire_parse_and_foundation_first():
    assert solitaire.parse_card("7 Rô") == (7, "ro")
    assert solitaire.parse_card("10♠") == (10, "bich")
    assert solitaire.parse_card("QH") == (12, "co")
    state = {
        "tableau": [{"down": 2, "up": ["A Cơ"]}] + [{"down": 0, "up": []}] * 6,
        "waste": None, "foundations": {"co": 0, "ro": 0, "bich": 0, "tep": 0}, "stock": 10,
    }
    best = solitaire.best_moves(state)[0]
    assert "ô đích" in best["description"] and "from_col=1, to_col=8" in best["call"]


def test_solitaire_reveals_facedown_and_respects_rules():
    state = {
        "tableau": [
            {"down": 2, "up": ["7 Rô"]},        # 7 đỏ: đặt được lên 8 đen
            {"down": 0, "up": ["8 Tép"]},
            {"down": 0, "up": ["9 Cơ"]},        # 8 đen lên 9 đỏ cũng hợp lệ nhưng không lật gì
        ] + [{"down": 0, "up": ["2 Bích"]}] * 4,
        "waste": None, "foundations": {}, "stock": 5,
    }
    best = solitaire.best_moves(state)[0]
    assert "lật mở bài úp" in best["description"]
    assert "source_card='7 Rô', target_card='8 Tép'" in best["call"]
    # Không bao giờ đề xuất đặt đen lên đen / sai thứ tự
    for m in solitaire.best_moves(state, limit=10):
        assert "'2 Bích', target_card='2 Bích'" not in m["call"]


def test_solitaire_king_to_empty_and_draw_fallback():
    state = {"tableau": [{"down": 1, "up": ["K Cơ"]}, {"down": 0, "up": []}] + [{"down": 0, "up": ["5 Bích"]}] * 5,
             "waste": None, "foundations": {}, "stock": 3}
    assert "cột trống" in solitaire.best_moves(state)[0]["description"]
    dead = {"tableau": [{"down": 0, "up": ["5 Bích"]}] * 7, "waste": None, "foundations": {}, "stock": 4}
    assert solitaire.best_moves(dead)[0]["call"] == "solitaire_draw_card()"
    assert "Lỗi" in solitaire.best_move_text("không phải json")


# ---------------- Checks ----------------
def test_checks_file_and_contains():
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "a.txt"
        f.write_text("Xin chào Việt Nam", encoding="utf-8")
        ok, rep = checks.run_checks([f"file_exists:{f}", f"file_contains:{f}::việt nam", f"dir_exists:{d}"])
        assert ok, rep
        ok, rep = checks.run_checks([f"file_exists:{f}", f"file_contains:{f}::không có"])
        assert not ok and "KHÔNG ĐẠT" in rep
        assert checks.run_checks(["file_not_exists:" + str(Path(d) / "x.txt")])[0]
    assert checks.run_checks([]) == (True, "")


def test_guard_uses_machine_checks_instead_of_screenshot_gate():
    from core.guard import RunGuard
    with tempfile.TemporaryDirectory() as d:
        target = Path(d) / "done.txt"
        g = RunGuard(checks=[f"file_exists:{target}"])
        g.observe("desktop_click", {"ref_id": "e1"}, "Thành công")      # sẽ là "chưa xác minh" nếu không có checks
        bounce = g.check_finish()
        assert bounce and "CHƯA ĐẠT TIÊU CHÍ" in bounce
        target.write_text("x")
        assert g.check_finish() is None                                   # máy đã kiểm chứng -> không bắt chụp lại
        g2 = RunGuard(checks=[f"file_exists:{target.parent / 'nope'}"])
        for _ in range(3):
            assert g2.check_finish()
        assert g2.check_finish() is None                                  # tối đa 3 lần rồi cho qua


# ---------------- Router ----------------
def test_router_patterns(monkeypatch=None):
    calls = []
    orig_run, orig_open = router._run, router._open_app
    router._run = lambda cmd: calls.append(cmd) or {"success": True, "stdout": "C:\\x\\bao cao.docx"}
    router._open_app = lambda exe, kw: calls.append(("app", exe, kw)) or {"success": True, "summary": "ok"}
    try:
        assert router.try_route("Mở Notepad")["success"] and calls[-1] == ("app", "notepad", "notepad")
        assert router.try_route("mở ứng dụng máy tính") and calls[-1][1] == "calc"
        assert router.try_route("mở youtube.com")["success"] and "https://youtube.com" in calls[-1]
        assert router.try_route("vào trang github")["success"] and "github.com" in calls[-1]
        r = router.try_route("tìm kiếm thời tiết Hà Nội trên google")
        assert r["success"] and "google.com/search?q=" in calls[-1] and "H%C3%A0" not in calls[-1]  # đã lower-case
        r = router.try_route("tìm file báo cáo")
        assert r["success"] and "Get-ChildItem" in calls[-1] and "*báo cáo*" in calls[-1] and "-File" in calls[-1]
        n = len(calls)
        # Câu phức tạp/không chắc chắn -> None, không chạy gì
        for goal in ["mở notepad và viết bài thơ", "viết báo cáo về AI", "mở thư mục KTMT",
                     "tìm kiếm file báo cáo trên google", "mở notepad rồi lưu ra desktop", ""]:
            assert router.try_route(goal) is None, goal
        assert len(calls) == n
    finally:
        router._run, router._open_app = orig_run, orig_open


# ---------------- Recipes + runlog ----------------
def test_recipes_save_find_replay():
    with tempfile.TemporaryDirectory() as d:
        recipes.STORE = Path(d) / "recipes.json"
        out = Path(d) / "ghi chu.txt"
        recorder.begin()
        res = tools.dispatch_tool("write_text_file", {"path": str(out), "content": "Xin chào"})
        recorder.record("desktop_snapshot", {}, "{}")                 # quan sát: không tính vào recipe
        assert not res.text.startswith("Thất bại")
        assert recipes.maybe_save("Tạo file ghi chú xin chào")
        rec = recipes.find("tạo file ghi chu xin chao")               # chuẩn hóa dấu/hoa thường
        assert rec and rec["checks"][0].startswith("file_exists:")
        out.unlink()
        ok, report = recipes.replay(rec)
        assert ok and out.read_text(encoding="utf-8") == "Xin chào"
        # Không lưu khi có bước không xác định (chuột) hoặc không có điều kiện kiểm chứng
        recorder.begin()
        recorder.record("mouse_click_coords", {"x": 1, "y": 2}, "Đã click")
        recorder.record("write_text_file", {"path": str(out), "content": "x"}, "Đã ghi")
        assert not recipes.maybe_save("goal khac")
        recorder.begin()
        recorder.record("keyboard_shortcut", {"keys": "ctrl+s"}, "Đã nhấn")
        assert not recipes.maybe_save("goal khong co check")
        # Hết hạn
        data = json.loads(recipes.STORE.read_text(encoding="utf-8"))
        for v in data.values():
            v["ts"] = 0
        recipes.STORE.write_text(json.dumps(data), encoding="utf-8")
        assert recipes.find("Tạo file ghi chú xin chào") is None


def test_runlog_append_and_summary():
    with tempfile.TemporaryDirectory() as d:
        runlog.LOG_PATH = Path(d) / "runs.jsonl"
        runlog.append("mục tiêu", "hybrid", "router", {"success": True, "steps": 1}, 0.4)
        runlog.append("mục tiêu 2", "hybrid", "ai", {"success": False, "error": "lỗi", "usage": {"in": 5}}, 9.0)
        s = runlog.summarize(runlog.LOG_PATH)
        assert s["router"]["success_rate"] == 1.0 and s["ai"]["success_rate"] == 0.0 and s["ai"]["avg_s"] == 9.0


# ---------------- Snapshot gọn + diff ----------------
def _fake_snapshot(items, snap="s1"):
    kids = [{"ref_id": f"@{snap}:e{i}", "role": r, "name": n, "value": v, "bounds": {"x": 10, "y": 10 + i * 30, "width": 80, "height": 24}}
            for i, (r, n, v) in enumerate(items, 1)]
    return {"ok": True, "data": {"app": "app.exe", "snapshot_id": snap, "window": {"title": "Win"},
                                 "tree": {"role": "window", "name": "Win", "children": kids}}}


def test_snapshot_compact_then_diff_then_unchanged():
    tools_ext.reset_state()
    base = [("button", "Lưu", ""), ("edit", "Tìm", ""), ("button", "Đóng", "")] + [("listitem", f"Mục {i}", "") for i in range(10)]
    seq = [_fake_snapshot(base, "s1"), _fake_snapshot(base, "s2"),
           _fake_snapshot(base + [("button", "OK", "")], "s3")]
    orig = tools_ext.agent_desktop.snapshot
    tools_ext.agent_desktop.snapshot = lambda **k: seq.pop(0)
    try:
        full = tools_ext.desktop_snapshot("app")
        assert full.splitlines()[1].startswith('e1 button "Lưu"') and "@s1" in full.splitlines()[0]
        assert len(full) < len(json.dumps(_fake_snapshot(base)))          # gọn hơn JSON thô
        assert "KHÔNG thay đổi" in tools_ext.desktop_snapshot("app")
        diff = tools_ext.desktop_snapshot("app")
        assert diff.startswith("# THAY ĐỔI") and '+ @s3:e14 button "OK"' in diff and "Lưu" not in diff
        assert tools_ext.resolve_ref("e3") == "@s1:e3" and tools_ext.resolve_ref("@s9:e1") == "@s9:e1"
    finally:
        tools_ext.agent_desktop.snapshot = orig


def test_capture_marks_filters_and_numbers():
    tools_ext.reset_state()
    snap = _fake_snapshot([("button", "A", ""), ("button", "B", ""), ("group", "", "")])
    snap["data"]["tree"]["children"][2]["bounds"] = {"x": 0, "y": 0, "width": 2, "height": 2}   # quá nhỏ
    orig = tools_ext.agent_desktop.snapshot
    tools_ext.agent_desktop.snapshot = lambda **k: snap
    try:
        marks = tools_ext.capture_marks()
        assert [m["n"] for m in marks] == [1, 2] and marks[0]["cx"] == 50
        assert "chưa có phần tử #9" in tools_ext.click_mark(9)
        assert "1=A" in tools_ext.marks_legend(marks)
    finally:
        tools_ext.agent_desktop.snapshot = orig


# ---------------- Công cụ động & gộp ----------------
def test_select_tools_dynamic_groups():
    base = {f.__name__ for f in tools.select_tools("mở notepad")}
    assert "run_powershell" in base and "write_text_file" in base and "take_screenshot_to_see" in base
    assert "solitaire_move_by_column" not in base
    sol = {f.__name__ for f in tools.select_tools("Chơi game bài Solitaire")}
    assert {"solitaire_best_move", "solitaire_move_by_column"} <= sol
    added = {f.__name__ for f in tools.select_tools("mở notepad", extra=tools.SKILL_TOOL_GROUPS["solitaire_rules"])}
    assert "solitaire_best_move" in added
    out = tools.dispatch_tool("load_skill", {"skill_name": "solitaire_rules"})
    assert "solitaire_best_move" in out.tools_added


def test_write_text_file_and_run_actions_stop_on_failure():
    with tempfile.TemporaryDirectory() as d:
        a = Path(d) / "sub" / "a.txt"
        r = tools.write_text_file(str(a), "nội dung")
        assert a.read_text(encoding="utf-8") == "nội dung" and "Đã ghi" in r
        assert "Safe Mode chặn" in tools.write_text_file("C:\\Windows\\x.txt", "x")
        b = Path(d) / "b.txt"
        actions = json.dumps([
            {"tool": "write_text_file", "args": {"path": str(b), "content": "1"}},
            {"tool": "run_powershell", "args": {"command": "Get-Item 'C:\\khong_ton_tai_xyz'"}},
            {"tool": "write_text_file", "args": {"path": str(Path(d) / "never.txt"), "content": "2"}},
        ])
        out = tools.run_actions(actions)
        assert b.exists() and not (Path(d) / "never.txt").exists()
        assert "đã dừng ở thao tác 2/3" in out and out.strip().splitlines()[-1].startswith("[Cửa sổ]")
        assert "không được phép" in tools.run_actions(json.dumps([{"tool": "run_python_code", "args": {"code": "1"}}]))
        assert "Lỗi" in tools.run_actions("không phải json")


def test_dispatch_appends_window_state_and_records():
    recorder.begin()
    out = tools.dispatch_tool("keyboard_shortcut", {"keys": "ctrl+s"})
    assert "[Cửa sổ]" in out.text
    assert recorder.steps[-1]["tool"] == "keyboard_shortcut"


# ---------------- Shell giữ sống (PowerShell thật) ----------------
def test_persistent_shell_fast_and_correct():
    import time
    from core.shell import shell
    r = shell.run("Write-Output 'xin chào'")
    assert r["success"] and r["stdout"] == "xin chào"
    t = time.time()
    r = shell.run("if ($true) {\n  'nhiều dòng'\n}")
    assert r["stdout"] == "nhiều dòng" and time.time() - t < 0.4          # không còn khởi động tiến trình mới
    bad = shell.run("Get-Item 'C:\\khong_ton_tai_xyz'")
    assert not bad["success"] and bad["stderr"]
    slow = shell.run("Start-Sleep 3", timeout=1)
    assert "timeout" in slow["error"]
    assert shell.run("'phục hồi'")["stdout"] == "phục hồi"                # tự khởi động lại sau timeout
    shell.close()


def test_run_skill_folder_digest():
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "a.txt").write_text("Chương 1: Kiến trúc máy tính", encoding="utf-8")
        out = tools.run_skill("folder_digest", json.dumps({"folder": d, "max_files": 3}))
        assert "Thành công" in out and "### a.txt" in out and "Kiến trúc" in out
        assert "Lỗi" in tools.run_skill("folder_digest", json.dumps({"folder": d + "_none"}))
        assert "Không có kỹ năng" in tools.run_skill("khong_co", "{}")


def test_smartbrain_routes_then_recipe_then_ai():
    from config import config
    from core.factory import SmartBrain

    class FakeInner:
        calls = 0

        def run_task(self, goal):
            FakeInner.calls += 1
            tools.dispatch_tool("write_text_file", {"path": TARGET, "content": "AI viết"})
            return {"success": True, "summary": "AI xong", "steps": 2}

    with tempfile.TemporaryDirectory() as d:
        global TARGET
        TARGET = str(Path(d) / "kq.txt")
        recipes.STORE = Path(d) / "recipes.json"
        runlog.LOG_PATH = Path(d) / "runs.jsonl"
        orig = router._open_app
        router._open_app = lambda exe, kw: {"success": True, "summary": f"mở {exe}"}
        try:
            brain = SmartBrain(FakeInner(), "gemini", lambda *a: None, lambda *a: None)
            r = brain.run_task("mở notepad")                      # 1) router: không gọi AI
            assert r["route"] == "router" and FakeInner.calls == 0
            r = brain.run_task("viết kết quả ra tệp")             # 3) AI lần đầu, sau đó lưu recipe
            assert r["route"] == "ai" and FakeInner.calls == 1 and Path(TARGET).exists()
            Path(TARGET).unlink()
            r = brain.run_task("viết kết quả ra tệp")             # 2) recipe: chạy lại, không gọi AI
            assert r["route"] == "recipe" and FakeInner.calls == 1 and Path(TARGET).exists()
            routes = [json.loads(l)["route"] for l in runlog.LOG_PATH.read_text(encoding="utf-8").splitlines()]
            assert routes == ["router", "ai", "recipe"]
            config.recipes_enabled = False
            Path(TARGET).unlink()
            assert brain.run_task("viết kết quả ra tệp")["route"] == "ai" and FakeInner.calls == 2
        finally:
            config.recipes_enabled = True
            router._open_app = orig


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"OK  {name}")
    print("Tất cả kiểm thử tính năng đều đạt.")
