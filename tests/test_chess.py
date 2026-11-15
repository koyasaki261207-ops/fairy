"""
Kiểm thử cờ vua cục bộ bằng màn hình giả lập (không cần màn hình/chuột thật):
vẽ bàn cờ kiểu chess.com/lichess bằng PIL, giả lập click-click và một đối thủ máy.
"""
import os
import random
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
chess = pytest.importorskip("chess")
from PIL import Image, ImageDraw  # noqa: E402

from core import chess_play as cp  # noqa: E402

THEMES = {
    "chesscom": ((235, 236, 208), (119, 149, 86), (246, 246, 105), (186, 202, 43), (49, 46, 43)),
    "lichess": ((240, 217, 181), (181, 136, 99), (205, 210, 106), (170, 162, 58), (22, 21, 18)),
}


def render(board, white_bottom=True, x0=300, y0=110, s=80, theme="chesscom", size=(1600, 900),
           last=None, selected=None):
    light, dark, hl_light, hl_dark, bg = THEMES[theme]
    img = Image.new("RGB", size, bg)
    d = ImageDraw.Draw(img)
    for r in range(8):
        for c in range(8):
            sq = cp.screen_to_square(r, c, white_bottom)
            is_light = (r + c) % 2 == 0
            col = light if is_light else dark
            if last and sq in last:
                col = hl_light if is_light else hl_dark
            xa, ya = x0 + c * s, y0 + r * s
            d.rectangle((xa, ya, xa + s - 1, ya + s - 1), fill=col)
            if c == 0:   # số hàng ở góc trên-trái (giống chess.com)
                d.text((xa + 3, ya + 2), str(chess.square_rank(sq) + 1), fill=dark if is_light else light)
            if r == 7:   # chữ cột ở góc dưới-phải
                d.text((xa + s - 10, ya + s - 14), chess.FILE_NAMES[chess.square_file(sq)],
                       fill=dark if is_light else light)
            if selected is not None and sq in selected:  # chấm gợi ý nước đi
                d.ellipse((xa + s * 0.4, ya + s * 0.4, xa + s * 0.6, ya + s * 0.6), fill=(100, 110, 80))
            pc = board.piece_at(sq)
            if pc:
                m = s * (0.28 if pc.piece_type == chess.PAWN else 0.16)
                fill = (248, 248, 248) if pc.color == chess.WHITE else (70, 66, 62)
                d.ellipse((xa + m, ya + m, xa + s - m, ya + s - m), fill=fill, outline=(25, 25, 25), width=3)
    return np.asarray(img)


class FakeSite:
    """Trang cờ giả: nhận click-click / kéo thả, đối thủ máy trả lời sau vài khung hình."""

    def __init__(self, board=None, white_bottom=True, theme="chesscom", reply_delay=2, opp_seed=1,
                 drag_only=False, geom=(300, 110, 80)):
        self.board = board or chess.Board()
        self.white_bottom = white_bottom
        self.theme = theme
        self.sel = None
        self.last = None
        self.pending = None
        self.reply_delay = reply_delay
        self.rng = random.Random(opp_seed)
        self.drag_only = drag_only
        self.x0, self.y0, self.s = geom
        self.my_color = chess.WHITE if white_bottom else chess.BLACK
        self.clicks = 0
        self.frames = 0

    def _sq(self, x, y):
        c, r = int((x - self.x0) // self.s), int((y - self.y0) // self.s)
        if not (0 <= c < 8 and 0 <= r < 8):
            return None
        return cp.screen_to_square(r, c, self.white_bottom)

    def _try(self, a, b):
        for mv in self.board.legal_moves:
            if mv.from_square == a and mv.to_square == b and mv.promotion in (None, chess.QUEEN):
                self.board.push(mv)
                self.last = {a, b}
                self.pending = self.reply_delay
                return True
        return False

    def grab(self):
        self.frames += 1
        if self.pending is not None and not self.board.is_game_over() and self.board.turn != self.my_color:
            self.pending -= 1
            if self.pending <= 0:
                mv = self.rng.choice(list(self.board.legal_moves))
                self.board.push(mv)
                self.last = {mv.from_square, mv.to_square}
                self.pending = None
        dots = None
        if self.sel is not None:
            dots = {m.to_square for m in self.board.legal_moves if m.from_square == self.sel}
        return render(self.board, self.white_bottom, self.x0, self.y0, self.s, self.theme,
                      last=self.last, selected=dots)

    def click(self, x, y):
        self.clicks += 1
        sq = self._sq(x, y)
        if self.drag_only or sq is None:
            self.sel = None
            return
        pc = self.board.piece_at(sq)
        if self.sel is not None and self._try(self.sel, sq):
            self.sel = None
        elif pc and pc.color == self.board.turn:
            self.sel = sq
        else:
            self.sel = None

    def drag(self, x1, y1, x2, y2):
        a, b = self._sq(x1, y1), self._sq(x2, y2)
        self.sel = None
        if a is not None and b is not None:
            self._try(a, b)

    def park(self, x, y):
        pass


def session(site):
    return cp.ChessSession(grab=site.grab, click=site.click, drag=site.drag, park=site.park,
                           poll=0, sleep=lambda t: None)


@pytest.mark.parametrize("theme", ["chesscom", "lichess"])
@pytest.mark.parametrize("geom", [(300, 110, 80), (517, 63, 97), (40, 300, 64)])
def test_find_board(theme, geom):
    x0, y0, s = geom
    img = render(chess.Board(), x0=x0, y0=y0, s=s, theme=theme, size=(1920, 1080), last={chess.E2, chess.E4})
    g = cp.find_board(img)
    assert g is not None
    assert abs(g["x"] - x0) <= 2 and abs(g["y"] - y0) <= 2 and abs(g["s"] - s) <= 1


def test_no_board_on_plain_screen():
    img = np.full((900, 1600, 3), 40, dtype=np.uint8)
    assert cp.find_board(img) is None


def test_infer_opponent_move_and_orientation():
    b = chess.Board()
    b.push_san("e4")
    img = render(b, white_bottom=False, last={chess.E2, chess.E4})
    s = cp.ChessSession(grab=lambda: img, poll=0, sleep=lambda t: None)
    assert s.sync() == ""
    assert s.white_bottom is False and s.board.fen() == b.fen() and s.played == ["e4"]


def test_builtin_engine_finds_mate_in_one():
    b = chess.Board("6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1")
    assert cp.builtin_best_move(b, 1.0) == chess.Move.from_uci("a1a8")
    assert len(b.move_stack) == 0


def test_builtin_engine_takes_free_queen():
    b = chess.Board("4k3/8/8/3q4/4P3/8/8/4K3 w - - 0 1")
    assert cp.builtin_best_move(b, 0.5) == chess.Move.from_uci("e4d5")


@pytest.mark.parametrize("white_bottom,theme", [(True, "chesscom"), (False, "lichess")])
def test_plays_moves_against_simulated_site(white_bottom, theme, monkeypatch):
    monkeypatch.setattr(cp, "find_stockfish", lambda: None)
    site = FakeSite(white_bottom=white_bottom, theme=theme)
    if not white_bottom:  # mình cầm Đen: máy đi trước
        site.board.push_san("d4")
        site.last = {chess.D2, chess.D4}
    sess = session(site)
    out = sess.play(max_moves=8, think_seconds=0.05, opponent_timeout=5)
    assert "Đã đi 8 nước" in out, out
    # Thế cờ theo dõi được phải trùng với thế cờ thật của "trang"
    assert sess.board.board_fen() == site.board.board_fen(), out


def test_falls_back_to_drag_when_clicks_ignored(monkeypatch):
    monkeypatch.setattr(cp, "find_stockfish", lambda: None)
    site = FakeSite(drag_only=True)
    sess = session(site)
    out = sess.play(max_moves=2, think_seconds=0.05, opponent_timeout=5)
    assert "Đã đi 2 nước" in out, out
    assert sess.board.board_fen() == site.board.board_fen()


def test_plays_full_game_to_the_end(monkeypatch):
    monkeypatch.setattr(cp, "find_stockfish", lambda: None)
    site = FakeSite(reply_delay=1)
    sess = session(site)
    out = sess.play(max_moves=300, think_seconds=0.03, opponent_timeout=5)
    assert "VÁN CỜ KẾT THÚC" in out, out
    assert site.board.is_game_over()


def test_mismatched_board_asks_for_fen():
    b = chess.Board("8/8/4k3/8/8/3K4/8/8 w - - 0 1")
    img = render(b)
    s = cp.ChessSession(grab=lambda: img, poll=0, sleep=lambda t: None)
    assert "fen=" in s.sync()
    assert s.sync(fen=b.fen()) == ""


def test_underpromotion_from_engine_is_played_as_queen(monkeypatch):
    monkeypatch.setattr(cp, "find_stockfish", lambda: None)
    b = chess.Board("8/P6k/8/8/8/8/8/K7 w - - 0 1")
    site = FakeSite(board=b)
    monkeypatch.setattr(cp.Engine, "best", lambda self, board, t: chess.Move.from_uci("a7a8n"))
    sess = session(site)
    sess.play(max_moves=1, fen=b.fen(), think_seconds=0.05, opponent_timeout=1)
    assert sess.board.piece_at(chess.A8) == chess.Piece(chess.QUEEN, chess.WHITE)
    assert site.board.piece_at(chess.A8) == chess.Piece(chess.QUEEN, chess.WHITE)
