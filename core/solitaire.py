"""
BỘ GIẢI SOLITAIRE KLONDIKE (CODE TÍNH NƯỚC ĐI, AI CHỈ ĐỌC TRẠNG THÁI)
AI đọc bàn bài MỘT lần thành JSON có cấu trúc; code duyệt các nước đi hợp lệ, chấm điểm theo heuristic
(đưa lên ô đích > lật bài úp > giải phóng cột > đặt K vào cột trống > bài lật > rút bài) và trả về nước tốt nhất
dưới dạng lệnh gọi công cụ sẵn có. Không dùng token cho việc "nghĩ" nước đi.

Định dạng trạng thái (JSON):
{
  "tableau": [{"down": 3, "up": ["K Cơ", "Q Bích"]}, ... 7 cột ...],   # up: từ lá ngửa đầu cột -> lá trên cùng
  "waste": "3 Cơ" | null,                                               # lá ngửa trên chồng bài lật
  "foundations": {"co": 0, "ro": 0, "bich": 0, "tep": 0},               # rank cao nhất đã lên mỗi chất (0 = chưa có)
  "stock": 24                                                            # số lá còn trong chồng úp
}
"""

import json
import re
import unicodedata

RANKS = {"a": 1, "at": 1, "ace": 1, "j": 11, "boi": 11, "jack": 11, "q": 12, "dam": 12, "queen": 12,
         "k": 13, "gia": 13, "king": 13}
SUITS = {
    "co": "co", "h": "co", "heart": "co", "♥": "co",
    "ro": "ro", "d": "ro", "diamond": "ro", "♦": "ro",
    "bich": "bich", "s": "bich", "spade": "bich", "♠": "bich",
    "tep": "tep", "chuon": "tep", "c": "tep", "club": "tep", "♣": "tep",
}
SUIT_LABEL = {"co": "Cơ", "ro": "Rô", "bich": "Bích", "tep": "Tép"}
RANK_LABEL = {1: "A", 11: "J", 12: "Q", 13: "K"}
RED = {"co", "ro"}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFD", str(s).lower().replace("đ", "d"))
    return "".join(c for c in s if unicodedata.category(c) != "Mn").strip()


def parse_card(text):
    """'7 Rô' / '7D' / '10♠' / 'Q Cơ' -> (rank, suit) hoặc None."""
    if not text:
        return None
    s = _norm(text)
    m = re.match(r"^(10|[2-9]|a|at|ace|j|boi|jack|q|dam|queen|k|gia|king|1[1-3])\s*(?:of\s+)?(.*)$", s)
    if not m:
        return None
    r, rest = m.group(1), m.group(2).strip()
    rank = int(r) if r.isdigit() else RANKS[r]
    if r == "1":
        rank = 1
    suit = SUITS.get(rest)
    if suit is None:
        return None
    return rank, suit


def label(card) -> str:
    rank, suit = card
    return f"{RANK_LABEL.get(rank, rank)} {SUIT_LABEL[suit]}"


def _foundation_ranks(f) -> dict:
    ranks = {"co": 0, "ro": 0, "bich": 0, "tep": 0}
    if isinstance(f, dict):
        for k, v in f.items():
            suit = SUITS.get(_norm(k))
            if suit:
                ranks[suit] = int(v) if str(v).isdigit() else (parse_card(v) or (0,))[0]
    elif isinstance(f, list):
        for c in f:
            pc = parse_card(c)
            if pc:
                ranks[pc[1]] = max(ranks[pc[1]], pc[0])
    return ranks


def best_moves(state: dict, limit: int = 3) -> list[dict]:
    cols = []
    for col in state.get("tableau", []):
        up = [parse_card(c) for c in col.get("up", [])]
        up = [c for c in up if c]
        cols.append({"down": int(col.get("down", 0)), "up": up})
    found = _foundation_ranks(state.get("foundations", {}))
    waste = parse_card(state.get("waste"))
    stock = int(state.get("stock", 0) or 0)

    moves = []

    def can_stack(card, target):
        return card[0] == target[0] - 1 and (card[1] in RED) != (target[1] in RED)

    def to_found(card):
        return card[0] == found[card[1]] + 1

    def found_target():
        return "empty"

    if waste and to_found(waste):
        moves.append((100, f"Đưa {label(waste)} từ chồng bài lật lên ô đích",
                      f"solitaire_move_by_column(from_col=0, to_col=8, source_card='{label(waste)}', target_card='empty')"))

    for i, col in enumerate(cols):
        if not col["up"]:
            continue
        top = col["up"][-1]
        if to_found(top):
            bonus = 5 if len(col["up"]) == 1 and col["down"] > 0 else 0
            moves.append((95 + bonus, f"Đưa {label(top)} ở Cột {i+1} lên ô đích",
                          f"solitaire_move_by_column(from_col={i+1}, to_col=8, source_card='{label(top)}', target_card='empty')"))

    for i, col in enumerate(cols):
        if not col["up"]:
            continue
        root = col["up"][0]
        for j, tgt in enumerate(cols):
            if i == j:
                continue
            if tgt["up"]:
                top = tgt["up"][-1]
                if can_stack(root, top):
                    if col["down"] > 0:
                        score, why = 85, "lật mở bài úp"
                    else:
                        score, why = 55, "giải phóng cột"
                    moves.append((score, f"Chuyển cụm từ {label(root)} (Cột {i+1}) sang {label(top)} (Cột {j+1}) để {why}",
                                  f"solitaire_move_by_column(from_col={i+1}, to_col={j+1}, source_card='{label(root)}', target_card='{label(top)}')"))
            elif tgt["down"] == 0 and root[0] == 13 and col["down"] > 0:
                moves.append((80, f"Chuyển cụm K {label(root)} (Cột {i+1}) vào cột trống {j+1} để lật bài úp",
                              f"solitaire_move_by_column(from_col={i+1}, to_col={j+1}, source_card='{label(root)}', target_card='empty')"))

    if waste:
        for j, tgt in enumerate(cols):
            if tgt["up"] and can_stack(waste, tgt["up"][-1]):
                top = tgt["up"][-1]
                moves.append((70, f"Đặt {label(waste)} từ chồng bài lật lên {label(top)} (Cột {j+1})",
                              f"solitaire_move_by_column(from_col=0, to_col={j+1}, source_card='{label(waste)}', target_card='{label(top)}')"))
            elif not tgt["up"] and tgt["down"] == 0 and waste[0] == 13:
                moves.append((72, f"Đặt K {label(waste)} từ chồng bài lật vào cột trống {j+1}",
                              f"solitaire_move_by_column(from_col=0, to_col={j+1}, source_card='{label(waste)}', target_card='empty')"))

    if stock > 0 or waste:
        moves.append((10, "Không còn nước đi tốt: rút bài mới" if stock > 0 else "Hết chồng úp: lật lại chồng bài (rút bài)",
                      "solitaire_draw_card()"))

    moves.sort(key=lambda m: -m[0])
    return [{"score": s, "description": d, "call": c} for s, d, c in moves[:limit]]


def best_move_text(state_json: str) -> str:
    """Nhận JSON trạng thái -> văn bản gọn: nước đi tốt nhất + 2 phương án thay thế."""
    try:
        state = json.loads(state_json) if isinstance(state_json, str) else dict(state_json)
    except Exception as e:
        return f"Lỗi: trạng thái không phải JSON hợp lệ ({e}). Xem định dạng trong skill solitaire_rules."
    if not isinstance(state.get("tableau"), list) or not state["tableau"]:
        return "Lỗi: thiếu khóa 'tableau' (danh sách 7 cột)."
    moves = best_moves(state)
    if not moves:
        return "Không còn nước đi hợp lệ và không còn bài để rút: ván bài bế tắc. Hãy báo cáo."
    best = moves[0]
    out = [f"NƯỚC TỐT NHẤT: {best['description']}\n→ Gọi: {best['call']}"]
    for alt in moves[1:]:
        out.append(f"Thay thế: {alt['description']} → {alt['call']}")
    return "\n".join(out)
