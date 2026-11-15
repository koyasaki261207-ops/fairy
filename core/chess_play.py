"""
CỜ VUA CHẠY CỤC BỘ - 0 TOKEN MỖI NƯỚC ĐI
AI chỉ cần mở ván cờ rồi gọi chess_play() MỘT lần; phần còn lại làm bằng code:

1. Dò bàn cờ 8x8 trên màn hình (không cần biết trang web/ứng dụng): tìm cặp màu ô sáng/tối
   có các đường kẻ trong (7 dọc + 7 ngang) cách đều nhau.
2. Đọc từng ô bằng so sánh màu: trống / quân trắng / quân đen (không cần nhận dạng loại quân).
3. Theo dõi ván bằng python-chess: nước của đối thủ được suy ra bằng cách thử mọi nước hợp lệ và
   chọn nước có ảnh "trống/trắng/đen" khớp với màn hình.
4. Tính nước đi: Stockfish nếu có (STOCKFISH_PATH, bin/stockfish*.exe hoặc PATH), ngược lại dùng
   engine alpha-beta tích hợp.
5. Đi quân bằng click ô nguồn -> ô đích (tự thử kéo thả nếu trang không nhận), phong cấp thành Hậu.

Các hàm chụp/click có thể thay thế (grab/click/drag) để kiểm thử không cần màn hình.
"""

from __future__ import annotations

import glob
import os
import shutil
import time
from pathlib import Path

import numpy as np

try:
    import chess
    HAS_CHESS = True
except ImportError:  # pragma: no cover - báo lỗi thân thiện khi gọi tool
    chess = None
    HAS_CHESS = False

ROOT = Path(__file__).resolve().parent.parent
EMPTY, WHITE, BLACK = 0, 1, 2


# =====================================================================
# 1. DÒ BÀN CỜ
# =====================================================================

def _top_colors(small: np.ndarray, k: int = 10) -> list[np.ndarray]:
    q = (small >> 3).astype(np.int32)
    codes = (q[..., 0] << 10) | (q[..., 1] << 5) | q[..., 2]
    vals, counts = np.unique(codes, return_counts=True)
    order = np.argsort(-counts)[:k]
    total = codes.size
    out = []
    for i in order:
        if counts[i] < total * 0.004:
            break
        c = int(vals[i])
        out.append(np.array([(c >> 10) & 31, (c >> 5) & 31, c & 31], dtype=np.int16) * 8 + 4)
    return out


def _mask(img: np.ndarray, color: np.ndarray, tol: int = 36) -> np.ndarray:
    return np.abs(img.astype(np.int16) - color).sum(axis=-1) <= tol


def _line_profile(la: np.ndarray, lb: np.ndarray, axis: int) -> np.ndarray:
    """Số điểm chuyển trực tiếp màu A<->B tại mỗi vị trí (axis=1: đường dọc, axis=0: đường ngang)."""
    if axis == 0:
        la, lb = la.T, lb.T
    n = la.shape[1]
    prof = np.zeros(n, dtype=np.int64)
    t1 = (la[:, 1:] & lb[:, :-1]) | (lb[:, 1:] & la[:, :-1])
    prof[1:] += t1.sum(axis=0)
    if n > 2:  # cho phép 1 điểm ảnh khử răng cưa giữa hai ô
        t2 = (la[:, 2:] & lb[:, :-2]) | (lb[:, 2:] & la[:, :-2])
        prof[1:-1] += t2.sum(axis=0)
    return prof


def _peaks(prof: np.ndarray, rel: float = 0.3) -> list[tuple[float, float]]:
    """Gom các vị trí vượt ngưỡng thành cụm -> [(tâm, trọng số)]."""
    if prof.max() <= 0:
        return []
    thr = prof.max() * rel
    idx = np.nonzero(prof >= thr)[0]
    out, start = [], None
    for j, i in enumerate(idx):
        if start is None:
            start = j
        if j == len(idx) - 1 or idx[j + 1] > i + 1:
            seg = idx[start:j + 1]
            w = prof[seg].astype(float)
            out.append((float((seg * w).sum() / w.sum()), float(w.sum())))
            start = None
    return out


def _fit_grid(peaks: list[tuple[float, float]], min_s: float) -> tuple[float, float, int] | None:
    """Tìm 7 đường trong cách đều nhau -> (gốc bàn cờ, cạnh ô, số đường khớp)."""
    if len(peaks) < 5:
        return None
    pos = [p for p, _ in peaks]
    best = None
    cands = {round(b - a, 1) for i, a in enumerate(pos) for b in pos[i + 1:i + 3] if b - a >= min_s}
    for s in cands:
        tol = max(1.5, 0.08 * s)
        for anchor in pos:
            ks = {}
            for p, w in peaks:
                k = round((p - anchor) / s)
                if abs(p - (anchor + k * s)) <= tol and -8 <= k <= 8:
                    ks[k] = max(ks.get(k, 0.0), w)
            for k0 in range(-8, 2):
                win = [ks[k] for k in range(k0 + 1, k0 + 8) if k in ks]
                if len(win) >= 5:
                    score = (len(win), sum(win))
                    if best is None or score > best[0]:
                        best = (score, anchor + k0 * s, s, k0)
    if best is None:
        return None
    (n, _), origin, s, k0 = best
    # Tinh chỉnh cạnh ô bằng bình phương tối thiểu trên các đường đã khớp
    pts = []
    for p, _ in peaks:
        k = round((p - origin) / s)
        if 1 <= k <= 7 and abs(p - (origin + k * s)) <= max(1.5, 0.08 * s):
            pts.append((k, p))
    if len(pts) >= 2:
        ks_ = np.array([k for k, _ in pts], float)
        ps_ = np.array([p for _, p in pts], float)
        s, origin = np.polyfit(ks_, ps_, 1)
    return float(origin), float(s), n


def _detect(img: np.ndarray, colors=None, min_s: float = 8) -> dict | None:
    pairs = []
    cols = colors if colors is not None else _top_colors(img)
    masks = [_mask(img, c) for c in cols]
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            if np.abs(cols[i] - cols[j]).sum() < 60:
                continue
            ci, cj = masks[i].sum(), masks[j].sum()
            if not ci or not cj or not (0.25 <= ci / cj <= 4):
                continue
            pairs.append((i, j))
    best = None
    for i, j in pairs:
        la, lb = masks[i], masks[j]
        gx = _fit_grid(_peaks(_line_profile(la, lb, axis=1)), min_s)
        if not gx:
            continue
        gy = _fit_grid(_peaks(_line_profile(la, lb, axis=0)), min_s)
        if not gy or abs(gx[1] - gy[1]) > 0.1 * max(gx[1], gy[1]):
            continue
        score = gx[2] + gy[2]
        if best is None or score > best["score"]:
            best = {"x": gx[0], "y": gy[0], "s": (gx[1] + gy[1]) / 2, "score": score,
                    "colors": (cols[i], cols[j])}
    return best


def find_board(img: np.ndarray) -> dict | None:
    """
    Dò bàn cờ trong ảnh RGB (H, W, 3). Trả về {"x", "y", "s"} (gốc trên-trái và cạnh ô, pixel) hoặc None.
    Hai lượt: thô trên ảnh thu nhỏ, rồi tinh chỉnh trên ảnh gốc quanh vùng tìm được.
    """
    h, w = img.shape[:2]
    step = max(1, int(round(min(h, w) / 360)))
    small = img[::step, ::step]
    coarse = _detect(small)
    if not coarse:
        return None
    s = coarse["s"] * step
    x0, y0 = coarse["x"] * step, coarse["y"] * step
    if s * 8 < 120:
        return None
    m = int(s * 0.6)
    xa, ya = max(0, int(x0) - m), max(0, int(y0) - m)
    xb, yb = min(w, int(x0 + 8 * s) + m), min(h, int(y0 + 8 * s) + m)
    fine = _detect(img[ya:yb, xa:xb], colors=list(coarse["colors"]), min_s=s * 0.7) if step > 1 else None
    if fine and abs(fine["s"] - s) <= 0.1 * s:
        return {"x": xa + fine["x"], "y": ya + fine["y"], "s": fine["s"]}
    return {"x": x0, "y": y0, "s": s}


# =====================================================================
# 2. ĐỌC TỪNG Ô
# =====================================================================

def square_features(img: np.ndarray, geom: dict) -> np.ndarray:
    """Trả về mảng (8, 8, 2): [tỉ lệ điểm ảnh khác nền ở giữa ô, độ sáng TB của các điểm đó]."""
    x0, y0, s = geom["x"], geom["y"], geom["s"]
    out = np.zeros((8, 8, 2), dtype=float)
    p = max(2, int(s * 0.1))
    i = max(1, int(s * 0.04))
    c0, c1 = int(s * 0.18), int(s * 0.82)
    for r in range(8):
        ya = int(round(y0 + r * s))
        for c in range(8):
            xa = int(round(x0 + c * s))
            sq = img[ya:ya + int(s), xa:xa + int(s)].astype(np.int16)
            if sq.shape[0] < c1 or sq.shape[1] < c1:
                continue
            corners = np.concatenate([
                sq[i:i + p, i:i + p].reshape(-1, 3), sq[i:i + p, -i - p:-i].reshape(-1, 3),
                sq[-i - p:-i, i:i + p].reshape(-1, 3), sq[-i - p:-i, -i - p:-i].reshape(-1, 3),
            ])
            bg = np.median(corners, axis=0)
            center = sq[c0:c1, c0:c1]
            diff = np.abs(center - bg).sum(axis=-1) > 50
            frac = float(diff.mean())
            lum = 0.0
            if diff.any():
                px = center[diff]
                lum = float((0.299 * px[:, 0] + 0.587 * px[:, 1] + 0.114 * px[:, 2]).mean())
            out[r, c] = (frac, lum)
    return out


def _otsu(values: np.ndarray) -> float:
    v = np.sort(np.asarray(values, float).ravel())
    if len(v) < 2 or v[0] == v[-1]:
        return float(v[0]) if len(v) else 0.0
    best, thr = -1.0, float(v[0])
    for k in range(1, len(v)):
        a, b = v[:k], v[k:]
        score = len(a) * len(b) * (a.mean() - b.mean()) ** 2
        if score > best:
            best, thr = score, (v[k - 1] + v[k]) / 2
    return thr


def classify(feats: np.ndarray, thr: dict) -> np.ndarray:
    occ = feats[..., 0] > thr["occ"]
    white = feats[..., 1] > thr["lum"]
    return np.where(occ, np.where(white, WHITE, BLACK), EMPTY).astype(np.int8)


def auto_thresholds(feats: np.ndarray) -> dict:
    occ_thr = max(0.06, _otsu(feats[..., 0]))
    occ = feats[..., 0] > occ_thr
    lum_thr = _otsu(feats[..., 1][occ]) if occ.sum() >= 2 else 128.0
    return {"occ": occ_thr, "lum": lum_thr}


def calibrate(feats: np.ndarray, expected: np.ndarray, old: dict | None = None) -> dict:
    """Ngưỡng tốt nhất khi đã biết thế cờ thật (dùng sau mỗi lần khớp để thích nghi với giao diện)."""
    thr = dict(old or auto_thresholds(feats))
    f, l = feats[..., 0], feats[..., 1]
    empty, filled = f[expected == EMPTY], f[expected != EMPTY]
    if len(empty) and len(filled):
        lo, hi = np.percentile(empty, 95), np.percentile(filled, 5)
        thr["occ"] = float((lo + hi) / 2) if hi > lo else float((np.median(empty) + np.median(filled)) / 2)
        thr["occ"] = max(0.04, thr["occ"])
    wl, bl = l[expected == WHITE], l[expected == BLACK]
    if len(wl) and len(bl):
        lo, hi = np.percentile(bl, 90), np.percentile(wl, 10)
        thr["lum"] = float((lo + hi) / 2) if hi > lo else float((np.median(bl) + np.median(wl)) / 2)
    return thr


# =====================================================================
# 3. THEO DÕI VÁN CỜ
# =====================================================================

def screen_to_square(r: int, c: int, white_bottom: bool) -> int:
    return chess.square(c, 7 - r) if white_bottom else chess.square(7 - c, r)


def expected_grid(board, white_bottom: bool) -> np.ndarray:
    g = np.zeros((8, 8), dtype=np.int8)
    for r in range(8):
        for c in range(8):
            pc = board.piece_at(screen_to_square(r, c, white_bottom))
            if pc:
                g[r, c] = WHITE if pc.color == chess.WHITE else BLACK
    return g


def mismatch(obs: np.ndarray, board, white_bottom: bool) -> int:
    return int((obs != expected_grid(board, white_bottom)).sum())


def infer_move(board, obs: np.ndarray, white_bottom: bool):
    """Nước hợp lệ (của bên đang tới lượt) khớp ảnh nhất -> (move, số ô lệch, khoảng cách với nước thứ 2)."""
    scored = []
    for mv in board.legal_moves:
        if mv.promotion and mv.promotion != chess.QUEEN:
            # Ảnh trống/trắng/đen không phân biệt được loại quân phong -> giả định Hậu
            # (đối thủ phong cấp thấp rất hiếm; nếu có, thế cờ theo dõi sẽ lệch và cần gọi lại với fen=)
            continue
        board.push(mv)
        scored.append((mismatch(obs, board, white_bottom), mv))
        board.pop()
    if not scored:
        return None, 99, 0
    scored.sort(key=lambda t: t[0])
    gap = scored[1][0] - scored[0][0] if len(scored) > 1 else 99
    return scored[0][1], scored[0][0], gap


# =====================================================================
# 4. ENGINE
# =====================================================================

_VAL = {}
if HAS_CHESS:
    _VAL = {chess.PAWN: 100, chess.KNIGHT: 320, chess.BISHOP: 330, chess.ROOK: 500, chess.QUEEN: 900, chess.KING: 0}

_CENTER = [0, 1, 2, 3, 3, 2, 1, 0]
MATE = 100000


def _evaluate(board) -> int:
    """Điểm theo góc nhìn bên đang tới lượt: vật chất + kiểm soát trung tâm + tiến tốt."""
    score = 0
    for sq, pc in board.piece_map().items():
        f, r = chess.square_file(sq), chess.square_rank(sq)
        v = _VAL[pc.piece_type]
        if pc.piece_type in (chess.KNIGHT, chess.BISHOP):
            v += 6 * (_CENTER[f] + _CENTER[r])
        elif pc.piece_type == chess.PAWN:
            adv = r if pc.color == chess.WHITE else 7 - r
            v += 8 * adv + 4 * _CENTER[f]
        elif pc.piece_type == chess.KING and len(board.piece_map()) > 12:
            home = 0 if pc.color == chess.WHITE else 7
            v += 20 if r == home and f in (1, 2, 6) else (-15 if r != home else 0)
        score += v if pc.color == chess.WHITE else -v
    return score if board.turn == chess.WHITE else -score


def _ordered(board):
    def key(mv):
        if board.is_capture(mv):
            victim = board.piece_at(mv.to_square)
            attacker = board.piece_at(mv.from_square)
            return -(10 * (_VAL[victim.piece_type] if victim else 100) - (_VAL[attacker.piece_type] if attacker else 0))
        return 0 if not mv.promotion else -800
    return sorted(board.legal_moves, key=key)


class _Timeout(Exception):
    pass


def _search(board, depth, alpha, beta, deadline, ply=0):
    if time.time() > deadline:
        raise _Timeout()
    moves = _ordered(board)
    if not moves:
        return -MATE + ply if board.is_check() else 0
    if board.is_insufficient_material() or board.halfmove_clock >= 100 or (ply and board.is_repetition(2)):
        return 0
    if depth <= 0:
        return _quiesce(board, alpha, beta, deadline, 4)
    for mv in moves:
        board.push(mv)
        val = -_search(board, depth - 1, -beta, -alpha, deadline, ply + 1)
        board.pop()
        if val >= beta:
            return val
        alpha = max(alpha, val)
    return alpha


def _quiesce(board, alpha, beta, deadline, depth):
    stand = _evaluate(board)
    if stand >= beta or depth == 0:
        return stand
    alpha = max(alpha, stand)
    for mv in _ordered(board):
        if not board.is_capture(mv):
            continue
        board.push(mv)
        val = -_quiesce(board, -beta, -alpha, deadline, depth - 1)
        board.pop()
        if val >= beta:
            return val
        alpha = max(alpha, val)
    return alpha


def builtin_best_move(board, think_seconds: float = 0.6):
    """Alpha-beta tăng dần độ sâu tới hết thời gian; luôn trả về một nước hợp lệ."""
    moves = _ordered(board)
    if not moves:
        return None
    base_len = len(board.move_stack)
    best = moves[0]
    deadline = time.time() + max(0.05, think_seconds)
    depth = 1
    while depth <= 5:
        try:
            cur_best, alpha = None, -MATE * 2
            for mv in ([best] + [m for m in moves if m != best]):
                board.push(mv)
                val = -_search(board, depth - 1, -MATE * 2, -alpha, deadline, 1)
                board.pop()
                if val > alpha or cur_best is None:
                    alpha, cur_best = val, mv
            best = cur_best
            if alpha >= MATE - 100:
                break
        except _Timeout:
            # Lùi các nước đã push dở dang trong lần tìm bị cắt (độ sâu chưa xong -> giữ kết quả độ sâu trước)
            while len(board.move_stack) > base_len:
                board.pop()
            break
        depth += 1
    return best


def find_stockfish() -> str | None:
    env = os.getenv("STOCKFISH_PATH", "").strip().strip('"')
    if env and Path(env).is_file():
        return env
    for pat in ("stockfish*.exe", "stockfish*/stockfish*.exe", "stockfish"):
        hits = sorted(glob.glob(str(ROOT / "bin" / pat)))
        if hits:
            return hits[0]
    return shutil.which("stockfish")


class Engine:
    def __init__(self):
        self._sf = None
        self.name = "tích hợp"
        path = find_stockfish()
        if path:
            try:
                import chess.engine
                self._sf = chess.engine.SimpleEngine.popen_uci(path)
                self.name = "Stockfish"
            except Exception:
                self._sf = None

    def best(self, board, think_seconds: float):
        if self._sf is not None:
            try:
                import chess.engine
                return self._sf.play(board, chess.engine.Limit(time=max(0.05, think_seconds))).move
            except Exception:
                self.close()
        return builtin_best_move(board.copy(), think_seconds)

    def close(self):
        if self._sf is not None:
            try:
                self._sf.quit()
            except Exception:
                pass
            self._sf = None


# =====================================================================
# 5. VÒNG CHƠI
# =====================================================================

def _default_grab() -> np.ndarray:
    from core.vision import vision
    return np.asarray(vision._grab().convert("RGB"))


def _default_click(x: int, y: int):
    import pyautogui
    pyautogui.click(int(x), int(y))


def _default_drag(x1: int, y1: int, x2: int, y2: int):
    import pyautogui
    pyautogui.moveTo(int(x1), int(y1))
    pyautogui.mouseDown()
    pyautogui.moveTo(int(x2), int(y2), duration=0.15)
    pyautogui.mouseUp()


def _default_park(x: int, y: int):
    import pyautogui
    pyautogui.moveTo(int(x), int(y))


def _stopped() -> str:
    try:
        from core.safety import safety
        return safety.get_stop_reason() if safety.is_stopped() else ""
    except Exception:
        return ""


class ChessSession:
    """Trạng thái một ván (giữ giữa các lần gọi chess_play để có thể chơi tiếp)."""

    def __init__(self, grab=None, click=None, drag=None, park=None, poll: float = 0.15, sleep=time.sleep):
        self.grab = grab or _default_grab
        self.click = click or _default_click
        self.drag = drag or _default_drag
        self.park = park or _default_park
        self.poll = poll
        self.sleep = sleep
        self.geom = None
        self.board = None
        self.white_bottom = True
        self.thr = None
        self.played = []          # SAN của toàn ván (cả hai bên) kể từ khi đồng bộ

    # ---------- quan sát ----------
    def _feats(self):
        return square_features(self.grab(), self.geom)

    def observe(self) -> np.ndarray:
        return classify(self._feats(), self.thr)

    def observe_stable(self, timeout: float = 2.0) -> np.ndarray:
        """Chờ 2 lần quan sát liên tiếp giống nhau (hết hiệu ứng quân trượt)."""
        last = self.observe()
        end = time.time() + timeout
        while time.time() < end:
            self.sleep(self.poll)
            cur = self.observe()
            if np.array_equal(cur, last):
                return cur
            last = cur
        return last

    def center(self, sq: int) -> tuple[int, int]:
        f, rk = chess.square_file(sq), chess.square_rank(sq)
        c, r = (f, 7 - rk) if self.white_bottom else (7 - f, rk)
        g = self.geom
        return int(g["x"] + (c + 0.5) * g["s"]), int(g["y"] + (r + 0.5) * g["s"])

    def _park_mouse(self):
        g = self.geom
        self.park(int(g["x"] + 8 * g["s"] + g["s"] * 0.6), int(g["y"] + 4 * g["s"]))

    def _push(self, mv):
        self.played.append(self.board.san(mv))
        self.board.push(mv)

    # ---------- đồng bộ ----------
    def sync(self, fen: str = "") -> str:
        """Dò bàn cờ, xác định hướng bàn và thế cờ hiện tại. Trả về chuỗi lỗi ('' nếu ổn)."""
        img = self.grab()
        geom = find_board(img)
        if not geom:
            return ("Không tìm thấy bàn cờ trên màn hình. Hãy mở ván cờ, để bàn cờ hiển thị trọn vẹn "
                    "(không bị che/cuộn mất) rồi gọi lại chess_play.")
        self.geom = geom
        feats = square_features(img, geom)
        bases = []
        if fen:
            try:
                bases.append(chess.Board(fen))
            except ValueError as e:
                return f"FEN không hợp lệ: {e}"
        else:
            if self.board is not None:
                bases.append(self.board.copy())  # ván đang theo dõi từ lần gọi trước
            bases.append(chess.Board())
        best = None
        thr0 = self.thr or auto_thresholds(feats)
        for base in bases:
            # Thế cờ đã biết, hoặc đối thủ vừa đi thêm 1 nước (vd mình cầm Đen và Trắng đã đi)
            cands = [(base, None)] + [(self._after(base, m), m) for m in base.legal_moves]
            for b, extra in cands:
                for wb in (True, False):
                    exp = expected_grid(b, wb)
                    thr = calibrate(feats, exp, thr0)
                    mm = int((classify(feats, thr) != exp).sum())
                    if best is None or mm < best[0]:
                        best = (mm, base, extra, b, wb, thr)
        mm, base, extra, b, wb, thr = best
        if mm > 2:
            return (f"Bàn cờ trên màn hình không khớp thế cờ đã biết ({mm} ô lệch). Nếu ván đã đi dở, "
                    "hãy gọi chess_play với fen=<FEN thế cờ hiện tại>.")
        if extra is not None:
            self.played.append(base.san(extra))
        self.board, self.white_bottom, self.thr = b, wb, thr
        return ""

    @staticmethod
    def _after(board, mv):
        b = board.copy()
        b.push(mv)
        return b

    def _recalibrate(self, obs_feats=None):
        feats = obs_feats if obs_feats is not None else self._feats()
        self.thr = calibrate(feats, expected_grid(self.board, self.white_bottom), self.thr)

    # ---------- đối thủ ----------
    def wait_opponent(self, timeout: float) -> str:
        """Chờ đối thủ đi. '' khi đã ghi nhận nước; ngược lại là lý do dừng."""
        end = time.time() + timeout
        confused_since = None
        while time.time() < end:
            stop = _stopped()
            if stop:
                return stop
            obs = self.observe_stable()
            if mismatch(obs, self.board, self.white_bottom) <= 1:
                confused_since = None
                self.sleep(self.poll)
                continue
            mv, mm, gap = infer_move(self.board, obs, self.white_bottom)
            if mv is not None and mm <= 1 and gap >= 2:
                self._push(mv)
                self._recalibrate()
                return ""
            confused_since = confused_since or time.time()
            if time.time() - confused_since > 6:
                return ("Không nhận ra nước đi trên màn hình: bàn cờ bị hộp thoại che (thường là ván ĐÃ KẾT THÚC: "
                        "đầu hàng/hết giờ/hòa) hoặc đối thủ đi nhiều nước. Chụp màn hình 1 lần để kiểm tra; "
                        "ván đã xong -> finish_task, chưa xong -> đóng hộp thoại rồi gọi lại chess_play.")
            self.sleep(self.poll)
        return (f"Đối thủ chưa đi sau {timeout:.0f}s. Có thể ván đã kết thúc (đầu hàng/hết giờ/hòa) - chụp màn hình "
                "1 lần để kiểm tra; nếu đối thủ chỉ đang nghĩ, gọi lại chess_play để chơi tiếp.")

    # ---------- nước của mình ----------
    def make_move(self, mv) -> str:
        before = self.board.copy()
        after = self._after(before, mv)
        fx, fy = self.center(mv.from_square)
        tx, ty = self.center(mv.to_square)
        for attempt in range(3):
            if attempt == 1:
                self.drag(fx, fy, tx, ty)   # trang không nhận click-click -> kéo thả (bỏ qua trạng thái chọn quân)
            else:
                self.click(fx, fy)
                self.sleep(0.06)
                self.click(tx, ty)
            if mv.promotion:
                self.sleep(0.35)
                self.click(tx, ty)  # ô chọn quân phong: Hậu nằm ngay tại ô đích (lichess, chess.com)
            self._park_mouse()
            t_click = time.time()
            end = t_click + 2.5
            while time.time() < end:
                obs = self.observe_stable(1.0)
                if mismatch(obs, after, self.white_bottom) <= 1:
                    self._push(mv)
                    self._recalibrate()
                    return ""
                # Máy đối thủ đáp trả ngay lập tức -> nhận cả hai nước
                reply, mm, gap = infer_move(after, obs, self.white_bottom)
                if reply is not None and mm <= 1 and gap >= 2:
                    self._push(mv)
                    self._push(reply)
                    self._recalibrate()
                    return ""
                if mismatch(obs, before, self.white_bottom) <= 1 and time.time() - t_click >= 0.8:
                    break  # trang vẫn chưa nhận nước sau 0.8s -> thử lại (lần 2 dùng kéo thả)
                self.sleep(self.poll)
            if _stopped():
                return _stopped()
        return f"Trang không nhận nước {before.san(mv)} sau 3 lần thử (click-click và kéo thả)."

    # ---------- chơi ----------
    def play(self, my_color: str = "auto", max_moves: int = 200, fen: str = "", think_seconds: float = 0.6,
             opponent_timeout: float = 120.0) -> str:
        err = self.sync(fen)
        if err:
            return err
        mine = {"white": chess.WHITE, "trang": chess.WHITE, "trắng": chess.WHITE,
                "black": chess.BLACK, "den": chess.BLACK, "đen": chess.BLACK}.get(str(my_color).strip().lower())
        if mine is None:
            mine = chess.WHITE if self.white_bottom else chess.BLACK
        engine = Engine()
        start_len = len(self.played)
        made, reason = 0, ""
        try:
            while made < max_moves:
                stop = _stopped()
                if stop:
                    reason = stop
                    break
                if self.board.is_game_over():
                    break
                if self.board.turn != mine:
                    reason = self.wait_opponent(opponent_timeout)
                    if reason:
                        break
                    continue
                mv = engine.best(self.board, think_seconds)
                if mv is None:
                    break
                if mv.promotion and mv.promotion != chess.QUEEN:
                    # Giao diện luôn chọn Hậu (và ảnh trống/trắng/đen không phân biệt được loại quân phong)
                    mv = chess.Move(mv.from_square, mv.to_square, chess.QUEEN)
                reason = self.make_move(mv)
                if reason:
                    break
                made += 1
        finally:
            engine.close()
        side = "Trắng" if mine == chess.WHITE else "Đen"
        moves = " ".join(self.played[start_len:])
        if len(moves) > 400:
            moves = "…" + moves[-400:]
        lines = [f"Cầm quân {side} (engine {engine.name}). Đã đi {made} nước trong lượt này."]
        if self.board.is_game_over():
            outcome = self.board.outcome()
            how = outcome.termination.name.lower() if outcome else ""
            lines.append(f"VÁN CỜ KẾT THÚC: {self.board.result()} ({how}).")
        elif reason:
            lines.append(f"Tạm dừng: {reason}")
        elif made >= max_moves:
            lines.append(f"Đã đủ {max_moves} nước theo yêu cầu.")
        if moves:
            lines.append(f"Các nước: {moves}")
        lines.append(f"FEN hiện tại: {self.board.fen()}")
        return "\n".join(lines)


_session: ChessSession | None = None


def chess_play(my_color: str = "auto", max_moves: int = 200, fen: str = "", think_seconds: float = 0.6) -> str:
    """
    Tự chơi cờ vua trên bàn cờ đang hiện trên màn hình (lichess, chess.com, app...) bằng code cục bộ:
    tự dò bàn cờ, nhận nước của đối thủ, tính nước (Stockfish nếu có) và click. KHÔNG cần chụp ảnh hay đoán tọa độ.
    Gọi MỘT lần sau khi ván đã bắt đầu; chạy tới hết ván hoặc max_moves. my_color: auto/white/black
    (auto = màu quân ở phía dưới). fen: chỉ khi ván đã đi dở mà không theo dõi từ đầu.
    """
    if not HAS_CHESS:
        return "Lỗi: thiếu thư viện python-chess. Chạy: pip install chess"
    global _session
    if _session is None:
        _session = ChessSession()
    try:
        max_moves = int(max_moves or 200)
        think = float(think_seconds or 0.6)
    except (TypeError, ValueError):
        max_moves, think = 200, 0.6
    try:
        return _session.play(my_color=my_color, max_moves=max(1, max_moves), fen=fen or "",
                             think_seconds=min(max(think, 0.05), 10.0))
    except Exception as e:
        try:
            import pyautogui
            if isinstance(e, pyautogui.FailSafeException):
                from core.safety import safety
                safety.stop("Kích hoạt FailSafe do di chuột vào góc màn hình!")
                return "Đã dừng: FailSafe."
        except Exception:
            pass
        return f"Lỗi khi chơi cờ: {e}"
