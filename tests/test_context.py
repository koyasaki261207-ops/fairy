"""
Kiểm thử bộ quản lý ngữ cảnh (không cần cài SDK Gemini/Claude hay thư viện điều khiển chuột).
Chạy: python tests/test_context.py   (hoặc pytest tests/test_context.py)
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.context import (
    IMAGE_PLACEHOLDER,
    truncate_text,
    compact_json,
    format_args,
    prune_claude_images,
    compact_claude_history,
    claude_history_chars,
    set_claude_cache_breakpoint,
)
from core.prompts import SYSTEM_INSTRUCTION


def _img():
    return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": "xx"}}


def _shot_result(i):
    return {"role": "user", "content": [{
        "type": "tool_result", "tool_use_id": f"t{i}",
        "content": [{"type": "text", "text": f"shot {i}"}, _img()],
    }]}


def test_truncate_text_keeps_head_and_tail():
    s = "A" * 1000 + "B" * 1000
    out = truncate_text(s, 200)
    assert out.startswith("A" * 140)
    assert out.endswith("B" * 60)
    assert "đã lược" in out
    assert truncate_text("short", 200) == "short"


def test_compact_json_has_no_whitespace():
    assert compact_json({"a": [1, 2], "b": "ổn"}) == '{"a":[1,2],"b":"ổn"}'


def test_format_args_shortens_long_strings():
    out = format_args({"code": "x" * 500, "n": 3}, limit=20)
    assert len(out) < 60 and "n=3" in out


def test_prune_keeps_only_latest_images():
    msgs = [{"role": "user", "content": "goal"}]
    for i in range(4):
        msgs.append({"role": "assistant", "content": []})
        msgs.append(_shot_result(i))
    pruned = prune_claude_images(msgs, keep=1)
    assert pruned == 3
    images = [b for m in msgs if isinstance(m["content"], list)
              for tr in m["content"] if isinstance(tr, dict) and isinstance(tr.get("content"), list)
              for b in tr["content"] if b.get("type") == "image"]
    assert len(images) == 1
    # Ảnh còn lại phải là ảnh mới nhất
    assert msgs[-1]["content"][0]["content"][1]["type"] == "image"
    assert msgs[2]["content"][0]["content"][1] == {"type": "text", "text": IMAGE_PLACEHOLDER}
    # Gọi lại không thay đổi gì thêm (idempotent -> không phá cache)
    assert prune_claude_images(msgs, keep=1) == 0


def test_compact_only_when_over_budget():
    big = "R" * 5000
    msgs = [{"role": "user", "content": "goal"}]
    for i in range(10):
        msgs.append({"role": "assistant", "content": []})
        msgs.append({"role": "user", "content": [{"type": "tool_result", "tool_use_id": f"t{i}", "content": big}]})
    assert compact_claude_history(msgs, max_chars=10_000_000) == 0
    before = claude_history_chars(msgs)
    n = compact_claude_history(msgs, max_chars=10_000, keep_recent=6)
    assert n > 0
    assert claude_history_chars(msgs) < before
    # 6 message cuối không bị đụng tới
    assert msgs[-1]["content"][0]["content"] == big


def test_cache_breakpoint_single_and_on_last_block():
    msgs = [{"role": "user", "content": "goal"}]
    set_claude_cache_breakpoint(msgs)
    assert msgs[0]["content"][-1]["cache_control"] == {"type": "ephemeral"}
    msgs.append({"role": "assistant", "content": []})
    msgs.append({"role": "user", "content": [{"type": "tool_result", "tool_use_id": "a", "content": "ok"}]})
    set_claude_cache_breakpoint(msgs)
    marks = [b for m in msgs if isinstance(m["content"], list) for b in m["content"]
             if isinstance(b, dict) and "cache_control" in b]
    assert len(marks) == 1 and marks[0] is msgs[-1]["content"][-1]


def test_system_prompt_is_lean_and_points_to_skills():
    assert len(SYSTEM_INSTRUCTION) < 4000
    assert "load_skill('solitaire_rules')" in SYSTEM_INSTRUCTION
    assert "finish_task" in SYSTEM_INSTRUCTION


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"OK  {name}")
    print("Tất cả kiểm thử ngữ cảnh đều đạt.")
