"""Tactical sanity checks for the search and evaluation."""

import pytest

from chess_engine.board import START_FEN, Board
from chess_engine.evaluate import evaluate
from chess_engine.search import Searcher


def best(fen, depth=4):
    move, info = Searcher().search(Board(fen), max_depth=depth)
    return move.uci(), info


@pytest.mark.parametrize("fen", [
    "6k1/5ppp/8/8/8/8/8/R5K1 w - - 0 1",                               # back-rank mate
    "rnbqkbnr/ppppp2p/5p2/6p1/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 3",   # fool's mate
    "k7/8/1K6/8/8/8/8/7Q w - - 0 1",                                   # queen + king
])
def test_finds_mate_in_one(fen):
    found, info = best(fen, depth=2)
    board = Board(fen)
    board.make_move(board.parse_move(found))
    assert board.outcome() == "checkmate"
    assert info.mate_in == 1


def test_finds_mate_in_two():
    # rook roller: 1. Ra7 (or Rb7) cuts off the 7th rank, 2. Rb8#
    fen = "6k1/8/8/8/8/8/R7/1R4K1 w - - 0 1"
    _, info = best(fen, depth=4)
    assert info.mate_in == 2


def test_wins_hanging_queen():
    fen = "4k3/8/8/3q4/8/8/3R4/4K3 w - - 0 1"
    found, _ = best(fen, depth=2)
    assert found == "d2d5"


def test_does_not_grab_poisoned_pawn():
    # Rxd5 loses the rook to cxd5
    fen = "4k3/8/2p5/3p4/8/8/8/3RK3 w - - 0 1"
    found, _ = best(fen, depth=3)
    assert found != "d1d5"


def test_avoids_stalemate_when_winning():
    # Qf7?? would stalemate; anything sensible keeps the win
    fen = "7k/8/5K2/8/8/8/8/6Q1 w - - 0 1"
    board = Board(fen)
    move, _ = Searcher().search(board, max_depth=3)
    board.make_move(move)
    assert board.outcome() != "stalemate"


def test_evaluation_is_symmetric():
    fen = "r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3"
    mirrored = "rnbqkb1r/pppp1ppp/5n2/4p3/4P3/2N5/PPPP1PPP/R1BQKBNR b KQkq - 2 3"
    assert evaluate(Board(fen)) == evaluate(Board(mirrored))
    assert evaluate(Board(START_FEN)) == 0


def test_time_limit_is_respected():
    _, info = Searcher().search(Board(), time_limit=0.3)
    assert info.seconds < 0.6


def test_search_leaves_board_unchanged():
    board = Board()
    Searcher().search(board, max_depth=3)
    assert board.fen() == START_FEN


def test_zero_time_limit_still_limits_search():
    # time_limit=0 means "move now", not "no limit"
    move, info = Searcher().search(Board(), max_depth=5, time_limit=0)
    assert move is not None
    assert info.depth == 1
