"""Move generator correctness: perft against published node counts.

Reference numbers: https://www.chessprogramming.org/Perft_Results
"""

import os

import pytest

from chess_engine.board import START_FEN, Board, perft

SLOW = os.environ.get("SLOW_TESTS") == "1"

KIWIPETE = "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1"
POS3 = "8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1"
POS4 = "r3k2r/Pppp1ppp/1b3nbN/nP6/BBP1P3/q4N2/Pp1P2PP/R2Q1RK1 w kq - 0 1"
POS5 = "rnbq1k1r/pp1Pbppp/2p5/8/2B5/8/PPP1NnPP/RNBQK2R w KQ - 1 8"
POS6 = "r4rk1/1pp1qppp/p1np1n2/2b1p1B1/2B1P1b1/P1NP1N2/1PP1QPPP/R4RK1 w - - 0 10"

CASES = [
    (START_FEN, 1, 20), (START_FEN, 2, 400), (START_FEN, 3, 8_902),
    (KIWIPETE, 1, 48), (KIWIPETE, 2, 2_039),
    (POS3, 1, 14), (POS3, 2, 191), (POS3, 3, 2_812),
    (POS4, 1, 6), (POS4, 2, 264), (POS4, 3, 9_467),
    (POS5, 1, 44), (POS5, 2, 1_486),
    (POS6, 1, 46), (POS6, 2, 2_079),
]
SLOW_CASES = [
    (START_FEN, 4, 197_281),
    (KIWIPETE, 3, 97_862),
    (POS3, 4, 43_238),
    (POS5, 3, 62_379),
]


@pytest.mark.parametrize("fen,depth,expected", CASES)
def test_perft(fen, depth, expected):
    assert perft(Board(fen), depth) == expected


@pytest.mark.skipif(not SLOW, reason="set SLOW_TESTS=1 to run deeper perft")
@pytest.mark.parametrize("fen,depth,expected", SLOW_CASES)
def test_perft_deep(fen, depth, expected):
    assert perft(Board(fen), depth) == expected


@pytest.mark.parametrize("fen", [START_FEN, KIWIPETE, POS3, POS4, POS5, POS6,
                                 "8/8/8/3k4/8/8/8/4K3 b - - 12 40"])
def test_fen_round_trip(fen):
    assert Board(fen).fen() == fen


def _walk(board, depth, seen):
    """Make/unmake every move to `depth`, checking state is fully restored and
    the incrementally updated hash always equals a from-scratch hash."""
    if depth == 0:
        return
    for m in board.legal_moves():
        fen_before, hash_before = board.fen(), board.hash
        board.make_move(m)
        assert board.hash == board.compute_hash(), f"hash drift after {m} from {fen_before}"
        seen.add(board.hash)
        _walk(board, depth - 1, seen)
        board.unmake_move()
        assert board.fen() == fen_before, f"unmake {m} did not restore {fen_before}"
        assert board.hash == hash_before


@pytest.mark.parametrize("fen", [START_FEN, KIWIPETE, POS3, POS4, POS5])
def test_make_unmake_and_incremental_hash(fen):
    seen = set()
    _walk(Board(fen), 2, seen)
    assert len(seen) > 10


def test_castling_through_check_is_illegal():
    # black bishop on c4 covers f1, so white cannot castle kingside
    board = Board("4k3/8/8/8/2b5/8/8/4K2R w K - 0 1")
    assert "e1g1" not in [m.uci() for m in board.legal_moves()]


def test_en_passant_capture_removes_pawn():
    board = Board("4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 1")
    board.make_move(board.parse_move("e5d6"))
    assert board.fen().startswith("4k3/8/3P4/8/8/8/8/4K3")


def test_en_passant_that_exposes_king_is_illegal():
    # capturing on d6 would open the rank between the white king and black rook
    board = Board("8/8/8/KPp4r/8/8/8/4k3 w - c6 0 1")
    assert "b5c6" not in [m.uci() for m in board.legal_moves()]


def test_promotion_offers_all_four_pieces():
    board = Board("4k3/P7/8/8/8/8/8/4K3 w - - 0 1")
    promos = sorted(m.uci() for m in board.legal_moves() if m.uci().startswith("a7a8"))
    assert promos == ["a7a8b", "a7a8n", "a7a8q", "a7a8r"]


def test_outcomes():
    assert Board("7k/6Q1/6K1/8/8/8/8/8 b - - 0 1").outcome() == "checkmate"
    assert Board("7k/8/6QK/8/8/8/8/8 b - - 0 1").outcome() == "stalemate"
    assert Board("8/8/4k3/8/8/3NK3/8/8 w - - 0 1").outcome() == "insufficient material"
    assert Board("4k3/8/8/8/8/8/8/R3K3 w - - 100 80").outcome() == "fifty-move rule"
    assert Board().outcome() is None


def test_threefold_repetition():
    board = Board()
    for _ in range(2):
        for text in ("g1f3", "g8f6", "f3g1", "f6g8"):
            board.make_move(board.parse_move(text))
    assert board.outcome() == "threefold repetition"


def test_rejects_bad_fen():
    with pytest.raises(ValueError):
        Board("not a fen")
    with pytest.raises(ValueError):
        Board("8/8/8/8/8/8/8/8 w - - 0 1")  # no kings


@pytest.mark.parametrize("fen", [
    START_FEN, KIWIPETE,
    "7k/6Q1/6K1/8/8/8/8/8 b - - 0 1",    # checkmate
    "7k/8/6QK/8/8/8/8/8 b - - 0 1",      # stalemate
])
def test_has_legal_move(fen):
    board = Board(fen)
    assert board.has_legal_move() == bool(board.legal_moves())
    assert board.fen() == fen
