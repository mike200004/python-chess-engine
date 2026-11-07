"""Static evaluation: material + piece-square tables.

Tables are Tomasz Michniewski's "Simplified Evaluation Function" from the
Chess Programming Wiki, written from white's point of view with rank 8 at
the top (so they read like a board diagram).
"""

from __future__ import annotations

from .board import (BISHOP, BLACK, EMPTY, KING, KNIGHT, ON_BOARD, PAWN, QUEEN, ROOK,
                    WHITE, Board, file_of, rank_of)

PIECE_VALUES = {PAWN: 100, KNIGHT: 320, BISHOP: 330, ROOK: 500, QUEEN: 900, KING: 0}

_PAWN = [
    0, 0, 0, 0, 0, 0, 0, 0,
    50, 50, 50, 50, 50, 50, 50, 50,
    10, 10, 20, 30, 30, 20, 10, 10,
    5, 5, 10, 25, 25, 10, 5, 5,
    0, 0, 0, 20, 20, 0, 0, 0,
    5, -5, -10, 0, 0, -10, -5, 5,
    5, 10, 10, -20, -20, 10, 10, 5,
    0, 0, 0, 0, 0, 0, 0, 0,
]
_KNIGHT = [
    -50, -40, -30, -30, -30, -30, -40, -50,
    -40, -20, 0, 0, 0, 0, -20, -40,
    -30, 0, 10, 15, 15, 10, 0, -30,
    -30, 5, 15, 20, 20, 15, 5, -30,
    -30, 0, 15, 20, 20, 15, 0, -30,
    -30, 5, 10, 15, 15, 10, 5, -30,
    -40, -20, 0, 5, 5, 0, -20, -40,
    -50, -40, -30, -30, -30, -30, -40, -50,
]
_BISHOP = [
    -20, -10, -10, -10, -10, -10, -10, -20,
    -10, 0, 0, 0, 0, 0, 0, -10,
    -10, 0, 5, 10, 10, 5, 0, -10,
    -10, 5, 5, 10, 10, 5, 5, -10,
    -10, 0, 10, 10, 10, 10, 0, -10,
    -10, 10, 10, 10, 10, 10, 10, -10,
    -10, 5, 0, 0, 0, 0, 5, -10,
    -20, -10, -10, -10, -10, -10, -10, -20,
]
_ROOK = [
    0, 0, 0, 0, 0, 0, 0, 0,
    5, 10, 10, 10, 10, 10, 10, 5,
    -5, 0, 0, 0, 0, 0, 0, -5,
    -5, 0, 0, 0, 0, 0, 0, -5,
    -5, 0, 0, 0, 0, 0, 0, -5,
    -5, 0, 0, 0, 0, 0, 0, -5,
    -5, 0, 0, 0, 0, 0, 0, -5,
    0, 0, 0, 5, 5, 0, 0, 0,
]
_QUEEN = [
    -20, -10, -10, -5, -5, -10, -10, -20,
    -10, 0, 0, 0, 0, 0, 0, -10,
    -10, 0, 5, 5, 5, 5, 0, -10,
    -5, 0, 5, 5, 5, 5, 0, -5,
    0, 0, 5, 5, 5, 5, 0, -5,
    -10, 5, 5, 5, 5, 5, 0, -10,
    -10, 0, 5, 0, 0, 0, 0, -10,
    -20, -10, -10, -5, -5, -10, -10, -20,
]
_KING_MIDDLE = [
    -30, -40, -40, -50, -50, -40, -40, -30,
    -30, -40, -40, -50, -50, -40, -40, -30,
    -30, -40, -40, -50, -50, -40, -40, -30,
    -30, -40, -40, -50, -50, -40, -40, -30,
    -20, -30, -30, -40, -40, -30, -30, -20,
    -10, -20, -20, -20, -20, -20, -20, -10,
    20, 20, 0, 0, 0, 0, 20, 20,
    20, 30, 10, 0, 0, 10, 30, 20,
]
_KING_END = [
    -50, -40, -30, -20, -20, -30, -40, -50,
    -30, -20, -10, 0, 0, -10, -20, -30,
    -30, -10, 20, 30, 30, 20, -10, -30,
    -30, -10, 30, 40, 40, 30, -10, -30,
    -30, -10, 30, 40, 40, 30, -10, -30,
    -30, -10, 20, 30, 30, 20, -10, -30,
    -30, -30, 0, 0, 0, 0, -30, -30,
    -50, -30, -30, -30, -30, -30, -30, -50,
]

# Below this much non-pawn material (both sides together) the king should
# come to the centre instead of hiding.
ENDGAME_MATERIAL = 2600
BISHOP_PAIR = 30


def _build(table: list[int], value: int) -> dict[int, list[int]]:
    """Expand a 64-entry table into 120-square lookups for both colours,
    including the piece value, signed from white's point of view."""
    out = {WHITE: [0] * 120, BLACK: [0] * 120}
    for sq in ON_BOARD:
        f, r = file_of(sq), rank_of(sq)
        out[WHITE][sq] = value + table[(7 - r) * 8 + f]
        out[BLACK][sq] = -(value + table[r * 8 + f])  # mirrored vertically
    return out


PST = {
    PAWN: _build(_PAWN, PIECE_VALUES[PAWN]),
    KNIGHT: _build(_KNIGHT, PIECE_VALUES[KNIGHT]),
    BISHOP: _build(_BISHOP, PIECE_VALUES[BISHOP]),
    ROOK: _build(_ROOK, PIECE_VALUES[ROOK]),
    QUEEN: _build(_QUEEN, PIECE_VALUES[QUEEN]),
}
KING_PST_MIDDLE = _build(_KING_MIDDLE, 0)
KING_PST_END = _build(_KING_END, 0)


def evaluate(board: Board) -> int:
    """Score in centipawns from the point of view of the side to move."""
    s = board.squares
    score = 0
    non_pawn_material = 0
    bishops = {WHITE: 0, BLACK: 0}
    for sq in ON_BOARD:
        p = s[sq]
        if p == EMPTY:
            continue
        kind = abs(p)
        if kind == KING:
            continue
        colour = WHITE if p > 0 else BLACK
        score += PST[kind][colour][sq]
        if kind != PAWN:
            non_pawn_material += PIECE_VALUES[kind]
            if kind == BISHOP:
                bishops[colour] += 1

    kings = KING_PST_END if non_pawn_material <= ENDGAME_MATERIAL else KING_PST_MIDDLE
    score += kings[WHITE][board.king[WHITE]] + kings[BLACK][board.king[BLACK]]
    if bishops[WHITE] >= 2:
        score += BISHOP_PAIR
    if bishops[BLACK] >= 2:
        score -= BISHOP_PAIR
    return score * board.side
