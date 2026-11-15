"""
QUẢN LÝ NGỮ CẢNH HỘI THOẠI (CONTEXT BUDGET)
Giữ cho lượng token gửi lên API ở mức tối thiểu:
- Cắt gọn kết quả công cụ quá dài (giữ phần đầu + phần cuối).
- Lược bỏ ảnh chụp màn hình cũ (chỉ giữ N ảnh gần nhất).
- Nén các kết quả công cụ cũ khi lịch sử vượt ngưỡng (theo đợt, để không phá prompt cache mỗi bước).
- Đặt điểm cache (cache_control) cho Claude.

Module này thuần Python, không phụ thuộc SDK, để dễ kiểm thử.
"""

import json

IMAGE_PLACEHOLDER = "[Ảnh màn hình cũ đã lược bỏ để tiết kiệm token]"
COMPACTED_RESULT_CHARS = 300
KEEP_RECENT_MESSAGES = 6


def truncate_text(text: str, limit: int) -> str:
    """Cắt chuỗi về tối đa ~limit ký tự, giữ 70% phần đầu và 30% phần cuối (nơi thường chứa lỗi/kết quả)."""
    if text is None:
        return ""
    text = str(text)
    if limit <= 0 or len(text) <= limit:
        return text
    head = int(limit * 0.7)
    tail = max(0, limit - head)
    omitted = len(text) - head - tail
    tail_part = text[-tail:] if tail else ""
    return f"{text[:head]}\n...[đã lược {omitted} ký tự]...\n{tail_part}"


def one_line(text: str, limit: int = 300) -> str:
    """Rút gọn chuỗi thành 1 dòng ngắn để hiển thị log."""
    s = " ".join(str(text).split())
    return s if len(s) <= limit else s[: limit - 1] + "…"


def compact_json(data) -> str:
    """JSON không thụt lề/khoảng trắng thừa: tiết kiệm ~30-40% token so với indent=2."""
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def format_args(args: dict, limit: int = 80) -> str:
    """Định dạng tham số công cụ cho log, mỗi giá trị chuỗi bị rút gọn."""
    parts = []
    for k, v in (args or {}).items():
        if isinstance(v, str):
            parts.append(f"{k}='{one_line(v, limit)}'")
        else:
            parts.append(f"{k}={v}")
    return ", ".join(parts)


# =====================================================================
# Lịch sử định dạng Anthropic (messages là list[dict]; content của assistant
# có thể là object SDK nên chỉ đọc, không sửa)
# =====================================================================

def _iter_user_blocks(messages):
    """Duyệt các block dạng dict trong các lượt 'user' (bao gồm block con trong tool_result)."""
    for msg in messages:
        if msg.get("role") != "user" or not isinstance(msg.get("content"), list):
            continue
        for block in msg["content"]:
            if isinstance(block, dict):
                yield msg, block


def prune_claude_images(messages: list, keep: int) -> int:
    """Thay các ảnh cũ (ngoài `keep` ảnh gần nhất) bằng ghi chú chữ. Trả về số ảnh đã lược."""
    seen = 0
    pruned = 0
    for msg in reversed(messages):
        content = msg.get("content")
        if msg.get("role") != "user" or not isinstance(content, list):
            continue
        for block in reversed(content):
            if not isinstance(block, dict):
                continue
            containers = []
            if block.get("type") == "image":
                containers.append((content, block))
            elif block.get("type") == "tool_result" and isinstance(block.get("content"), list):
                for sub in reversed(block["content"]):
                    if isinstance(sub, dict) and sub.get("type") == "image":
                        containers.append((block["content"], sub))
            for parent, img in containers:
                seen += 1
                if seen > keep:
                    idx = next(i for i, b in enumerate(parent) if b is img)
                    parent[idx] = {"type": "text", "text": IMAGE_PLACEHOLDER}
                    pruned += 1
    return pruned


def _block_chars(block) -> int:
    if isinstance(block, dict):
        t = block.get("type")
        if t == "text":
            return len(block.get("text", ""))
        if t == "tool_result":
            c = block.get("content")
            if isinstance(c, str):
                return len(c)
            if isinstance(c, list):
                return sum(_block_chars(b) for b in c)
        if t == "image":
            return 4000  # ước lượng thô ~1k token
        return len(str(block))
    # Object SDK (assistant)
    text = getattr(block, "text", None)
    if text:
        return len(text)
    inp = getattr(block, "input", None)
    if inp is not None:
        return len(str(inp))
    return len(getattr(block, "thinking", "") or "")


def claude_history_chars(messages: list) -> int:
    total = 0
    for msg in messages:
        c = msg.get("content")
        if isinstance(c, str):
            total += len(c)
        elif isinstance(c, list):
            total += sum(_block_chars(b) for b in c)
    return total


def compact_claude_history(messages: list, max_chars: int,
                           keep_recent: int = KEEP_RECENT_MESSAGES,
                           short_limit: int = COMPACTED_RESULT_CHARS) -> int:
    """
    Khi lịch sử vượt `max_chars`, nén mọi kết quả công cụ cũ (ngoài `keep_recent` lượt cuối)
    về `short_limit` ký tự. Chỉ chạy khi vượt ngưỡng -> prompt cache chỉ bị phá 1 lần mỗi đợt nén.
    Trả về số block đã nén.
    """
    if claude_history_chars(messages) <= max_chars:
        return 0
    old = messages[:-keep_recent] if keep_recent > 0 else messages
    compacted = 0
    for _, block in _iter_user_blocks(old):
        if block.get("type") != "tool_result":
            continue
        c = block.get("content")
        if isinstance(c, str) and len(c) > short_limit:
            block["content"] = truncate_text(c, short_limit)
            compacted += 1
        elif isinstance(c, list):
            for sub in c:
                if isinstance(sub, dict) and sub.get("type") == "text" and len(sub.get("text", "")) > short_limit:
                    sub["text"] = truncate_text(sub["text"], short_limit)
                    compacted += 1
    return compacted


def set_claude_cache_breakpoint(messages: list) -> None:
    """
    Đặt đúng 1 điểm cache_control ở block cuối của lượt cuối (cache tăng dần theo hội thoại),
    gỡ các điểm cũ để không vượt giới hạn 4 breakpoint của API.
    """
    for _, block in _iter_user_blocks(messages):
        block.pop("cache_control", None)
    if not messages:
        return
    last = messages[-1]
    if last.get("role") != "user":
        return
    content = last.get("content")
    if isinstance(content, str):
        last["content"] = [{"type": "text", "text": content}]
        content = last["content"]
    if isinstance(content, list) and content and isinstance(content[-1], dict):
        content[-1]["cache_control"] = {"type": "ephemeral"}
