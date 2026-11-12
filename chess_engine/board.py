"""Board representation, move generation and FEN handling.

The board is a 10x12 "mailbox": the 8x8 board sits inside a 120-square list
with a border of off-board sentinel squares. Knight and sliding moves can
step onto the border without any bounds checking, they just stop there.

    index = 21 + file + 10 * rank      (a1 = 21, h1 = 28, a8 = 91, h8 = 98)

Pieces are small ints, positive for white and negative for black.
"""

from __future__ import annotations

import random
from typing import NamedTuple

EMPTY, PAWN, KNIGHT, BISHOP, ROOK, QUEEN, KING = 0, 1, 2, 3, 4, 5, 6
OFF = 99  # off-board sentinel
WHITE, BLACK = 1, -1

PIECE_LETTERS = {PAWN: "p", KNIGHT: "n", BISHOP: "b", ROOK: "r", QUEEN: "q", KING: "k"}
LETTER_PIECES = {v: k for k, v in PIECE_LETTERS.items()}

KNIGHT_STEPS = (21, 19, 12, 8, -8, -12, -19, -21)
BISHOP_DIRS = (11, 9, -9, -11)
ROOK_DIRS = (10, -10, 1, -1)
KING_STEPS = BISHOP_DIRS + ROOK_DIRS
SLIDER_DIRS = {BISHOP: BISHOP_DIRS, ROOK: ROOK_DIRS, QUEEN: KING_STEPS}

# castling rights bits
WK, WQ, BK, BQ = 1, 2, 4, 8

START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


def square(file: int, rank: int) -> int:
    return 21 + file + 10 * rank


def file_of(sq: int) -> int:
    return sq % 10 - 1


def rank_of(sq: int) -> int:
    return sq // 10 - 2


def square_name(sq: int) -> str:
    return "abcdefgh"[file_of(sq)] + str(rank_of(sq) + 1)


def parse_square(name: str) -> int:
    if len(name) != 2 or name[0] not in "abcdefgh" or name[1] not in "12345678":
        raise ValueError(f"bad square: {name!r}")
    return square("abcdefgh".index(name[0]), int(name[1]) - 1)


A1, B1, C1, D1, E1, F1, G1, H1 = (square(f, 0) for f in range(8))
A8, B8, C8, D8, E8, F8, G8, H8 = (square(f, 7) for f in range(8))
ON_BOARD = [square(f, r) for r in range(8) for f in range(8)]

# rights that survive a move touching each square (king/rook moved or rook captured)
CASTLE_MASK = [15] * 120
CASTLE_MASK[A1] = 15 & ~WQ
CASTLE_MASK[H1] = 15 & ~WK
CASTLE_MASK[E1] = 15 & ~(WK | WQ)
CASTLE_MASK[A8] = 15 & ~BQ
CASTLE_MASK[H8] = 15 & ~BK
CASTLE_MASK[E8] = 15 & ~(BK | BQ)

# Zobrist keys (fixed seed so hashes are reproducible between runs)
_rng = random.Random(2024)
Z_PIECE = {p: [_rng.getrandbits(64) for _ in range(120)]
           for p in range(-KING, KING + 1) if p != 0}
Z_SIDE = _rng.getrandbits(64)
Z_CASTLE = [_rng.getrandbits(64) for _ in range(16)]
Z_EP = [_rng.getrandbits(64) for _ in range(8)]


class Move(NamedTuple):
    frm: int
    to: int
    promo: int = EMPTY  # piece type (no colour) for promotions

    def uci(self) -> str:
        s = square_name(self.frm) + square_name(self.to)
        return s + PIECE_LETTERS[self.promo] if self.promo else s

    def __str__(self) -> str:
        return self.uci()


class Board:
    def __init__(self, fen: str = START_FEN):
        self.set_fen(fen)

    # ------------------------------------------------------------------ FEN

    def set_fen(self, fen: str) -> None:
        parts = fen.split()
        if len(parts) < 4:
            raise ValueError(f"FEN needs at least 4 fields: {fen!r}")
        squares = [OFF] * 120
        for sq in ON_BOARD:
            squares[sq] = EMPTY
        rows = parts[0].split("/")
        if len(rows) != 8:
            raise ValueError(f"FEN needs 8 ranks: {fen!r}")
        for i, row in enumerate(rows):
            rank, file = 7 - i, 0
            for ch in row:
                if ch.isdigit():
                    file += int(ch)
                elif ch.lower() in LETTER_PIECES and file < 8:
                    piece = LETTER_PIECES[ch.lower()]
                    squares[square(file, rank)] = piece if ch.isupper() else -piece
                    file += 1
                else:
                    raise ValueError(f"bad FEN rank {row!r}")
            if file != 8:
                raise ValueError(f"FEN rank {row!r} does not have 8 files")
        if parts[1] not in ("w", "b"):
            raise ValueError(f"bad side to move {parts[1]!r}")

        self.squares = squares
        self.side = WHITE if parts[1] == "w" else BLACK
        self.castling = 0
        for ch, bit in (("K", WK), ("Q", WQ), ("k", BK), ("q", BQ)):
            if ch in parts[2]:
                self.castling |= bit
        self.ep = 0 if parts[3] == "-" else parse_square(parts[3])
        self.halfmove = int(parts[4]) if len(parts) > 4 else 0
        self.fullmove = int(parts[5]) if len(parts) > 5 else 1

        self.king = {}
        for colour in (WHITE, BLACK):
            kings = [sq for sq in ON_BOARD if squares[sq] == KING * colour]
            if len(kings) != 1:
                raise ValueError("each side needs exactly one king")
            self.king[colour] = kings[0]

        self.history = []  # undo records for unmake_move
        self.hash = self.compute_hash()
        self.hash_history = [self.hash]

    def fen(self) -> str:
        rows = []
        for rank in range(7, -1, -1):
            row, empty = "", 0
            for file in range(8):
                p = self.squares[square(file, rank)]
                if p == EMPTY:
                    empty += 1
                    continue
                if empty:
                    row += str(empty)
                    empty = 0
                letter = PIECE_LETTERS[abs(p)]
                row += letter.upper() if p > 0 else letter
            rows.append(row + (str(empty) if empty else ""))
        castling = "".join(ch for ch, bit in (("K", WK), ("Q", WQ), ("k", BK), ("q", BQ))
                           if self.castling & bit) or "-"
        ep = square_name(self.ep) if self.ep else "-"
        side = "w" if self.side == WHITE else "b"
        return f"{'/'.join(rows)} {side} {castling} {ep} {self.halfmove} {self.fullmove}"

    def compute_hash(self) -> int:
        h = 0
        for sq in ON_BOARD:
            p = self.squares[sq]
            if p != EMPTY:
                h ^= Z_PIECE[p][sq]
        if self.side == BLACK:
            h ^= Z_SIDE
        h ^= Z_CASTLE[self.castling]
        if self.ep:
            h ^= Z_EP[file_of(self.ep)]
        return h

    def copy(self) -> "Board":
        b = Board.__new__(Board)
        b.squares = self.squares[:]
        b.side, b.castling, b.ep = self.side, self.castling, self.ep
        b.halfmove, b.fullmove = self.halfmove, self.fullmove
        b.king = dict(self.king)
        b.history = list(self.history)
        b.hash = self.hash
        b.hash_history = list(self.hash_history)
        return b

    # ------------------------------------------------------------- attacks

    def is_attacked(self, sq: int, by: int) -> bool:
        """Is `sq` attacked by any piece of colour `by`?"""
        s = self.squares
        pawn = PAWN * by
        if by == WHITE:
            if s[sq - 9] == pawn or s[sq - 11] == pawn:
                return True
        elif s[sq + 9] == pawn or s[sq + 11] == pawn:
            return True
        knight, king = KNIGHT * by, KING * by
        for step in KNIGHT_STEPS:
            if s[sq + step] == knight:
                return True
        for step in KING_STEPS:
            if s[sq + step] == king:
                return True
        bishop, rook, queen = BISHOP * by, ROOK * by, QUEEN * by
        for d in BISHOP_DIRS:
            t = sq + d
            while s[t] == EMPTY:
                t += d
            if s[t] == bishop or s[t] == queen:
                return True
        for d in ROOK_DIRS:
            t = sq + d
            while s[t] == EMPTY:
                t += d
            if s[t] == rook or s[t] == queen:
                return True
        return False

    def in_check(self) -> bool:
        return self.is_attacked(self.king[self.side], -self.side)

    # ------------------------------------------------------ move generation

    def pseudo_legal_moves(self, captures_only: bool = False) -> list[Move]:
        """Moves that follow piece rules but may leave our own king in check.

        With captures_only, also includes queen promotions (used by the
        quiescence search).
        """
        s, side, moves = self.squares, self.side, []
        add = moves.append
        for frm in ON_BOARD:
            p = s[frm] * side
            if p <= 0:
                continue
            if p == PAWN:
                self._pawn_moves(frm, captures_only, add)
            elif p == KNIGHT or p == KING:
                for step in (KNIGHT_STEPS if p == KNIGHT else KING_STEPS):
                    t = frm + step
                    target = s[t]
                    if target == OFF:
                        continue
                    if target == EMPTY:
                        if not captures_only:
                            add(Move(frm, t))
                    elif target * side < 0:
                        add(Move(frm, t))
            else:
                for d in SLIDER_DIRS[p]:
                    t = frm + d
                    while True:
                        target = s[t]
                        if target == OFF:
                            break
                        if target == EMPTY:
                            if not captures_only:
                                add(Move(frm, t))
                        else:
                            if target * side < 0:
                                add(Move(frm, t))
                            break
                        t += d
        if not captures_only:
            self._castling_moves(add)
        return moves

    def _pawn_moves(self, frm: int, captures_only: bool, add) -> None:
        s, side = self.squares, self.side
        fwd = 10 * side
        start_rank, last_rank = (1, 7) if side == WHITE else (6, 0)
        t = frm + fwd
        if s[t] == EMPTY:
            if rank_of(t) == last_rank:
                add(Move(frm, t, QUEEN))
                if not captures_only:
                    for promo in (ROOK, BISHOP, KNIGHT):
                        add(Move(frm, t, promo))
            elif not captures_only:
                add(Move(frm, t))
                if rank_of(frm) == start_rank and s[t + fwd] == EMPTY:
                    add(Move(frm, t + fwd))
        for t in (frm + fwd - 1, frm + fwd + 1):
            target = s[t]
            if (target != OFF and target * side < 0) or (t == self.ep and self.ep):
                if rank_of(t) == last_rank:
                    for promo in (QUEEN, ROOK, BISHOP, KNIGHT):
                        add(Move(frm, t, promo))
                else:
                    add(Move(frm, t))

    def _castling_moves(self, add) -> None:
        s, side = self.squares, self.side
        if side == WHITE:
            king_sq, ks, qs, rook = E1, WK, WQ, ROOK
            f, g, d, c, b, h, a = F1, G1, D1, C1, B1, H1, A1
        else:
            king_sq, ks, qs, rook = E8, BK, BQ, -ROOK
            f, g, d, c, b, h, a = F8, G8, D8, C8, B8, H8, A8
        if self.king[side] != king_sq or not self.castling & (ks | qs):
            return
        enemy = -side
        if self.is_attacked(king_sq, enemy):
            return
        if (self.castling & ks and s[h] == rook and s[f] == EMPTY and s[g] == EMPTY
                and not self.is_attacked(f, enemy) and not self.is_attacked(g, enemy)):
            add(Move(king_sq, g))
        if (self.castling & qs and s[a] == rook and s[d] == EMPTY and s[c] == EMPTY
                and s[b] == EMPTY and not self.is_attacked(d, enemy)
                and not self.is_attacked(c, enemy)):
            add(Move(king_sq, c))

    def legal_moves(self, captures_only: bool = False) -> list[Move]:
        legal = []
        for m in self.pseudo_legal_moves(captures_only):
            self.make_move(m)
            mover = -self.side
            if not self.is_attacked(self.king[mover], self.side):
                legal.append(m)
            self.unmake_move()
        return legal

    def has_legal_move(self) -> bool:
        """Like `bool(self.legal_moves())`, but stops at the first legal move."""
        for m in self.pseudo_legal_moves():
            self.make_move(m)
            legal = not self.is_attacked(self.king[-self.side], self.side)
            self.unmake_move()
            if legal:
                return True
        return False

    # ------------------------------------------------------ make / unmake

    def make_move(self, m: Move) -> None:
        s, side = self.squares, self.side
        frm, to, promo = m
        piece, captured = s[frm], s[to]
        self.history.append((m, piece, captured, self.castling, self.ep, self.halfmove, self.hash))

        h = self.hash ^ Z_PIECE[piece][frm] ^ Z_CASTLE[self.castling] ^ Z_SIDE
        if captured:
            h ^= Z_PIECE[captured][to]
        if self.ep:
            h ^= Z_EP[file_of(self.ep)]

        s[frm] = EMPTY
        s[to] = piece
        kind = piece * side
        new_ep = 0
        self.halfmove += 1

        if kind == PAWN:
            self.halfmove = 0
            if to == self.ep and captured == EMPTY:  # en passant
                victim = to - 10 * side
                h ^= Z_PIECE[s[victim]][victim]
                s[victim] = EMPTY
            elif to - frm == 20 * side:
                new_ep = frm + 10 * side
            if promo:
                s[to] = promo * side
        elif kind == KING:
            self.king[side] = to
            if abs(to - frm) == 2:  # castling: move the rook too
                rook_from, rook_to = (frm + 3, frm + 1) if to > frm else (frm - 4, frm - 1)
                rook = s[rook_from]
                s[rook_to], s[rook_from] = rook, EMPTY
                h ^= Z_PIECE[rook][rook_from] ^ Z_PIECE[rook][rook_to]
        if captured:
            self.halfmove = 0

        h ^= Z_PIECE[s[to]][to]
        self.castling &= CASTLE_MASK[frm] & CASTLE_MASK[to]
        h ^= Z_CASTLE[self.castling]
        self.ep = new_ep
        if new_ep:
            h ^= Z_EP[file_of(new_ep)]
        if side == BLACK:
            self.fullmove += 1
        self.side = -side
        self.hash = h
        self.hash_history.append(h)

    def unmake_move(self) -> None:
        m, piece, captured, castling, ep, halfmove, h = self.history.pop()
        self.hash_history.pop()
        s = self.squares
        side = -self.side
        frm, to, _ = m
        s[frm] = piece
        s[to] = captured
        kind = piece * side
        if kind == PAWN and to == ep and captured == EMPTY:
            s[to - 10 * side] = -PAWN * side
        elif kind == KING:
            self.king[side] = frm
            if abs(to - frm) == 2:
                rook_from, rook_to = (frm + 3, frm + 1) if to > frm else (frm - 4, frm - 1)
                s[rook_from], s[rook_to] = s[rook_to], EMPTY
        self.side = side
        self.castling, self.ep, self.halfmove, self.hash = castling, ep, halfmove, h
        if side == BLACK:
            self.fullmove -= 1

    def make_null_move(self) -> None:
        """Pass the turn without moving (used by null-move pruning). Undo it
        with unmake_null_move, not unmake_move."""
        self.history.append((None, EMPTY, EMPTY, self.castling, self.ep, self.halfmove, self.hash))
        h = self.hash ^ Z_SIDE
        if self.ep:
            h ^= Z_EP[file_of(self.ep)]
        self.ep = 0
        self.halfmove = 0  # a repetition can't reach back across a null move
        self.side = -self.side
        self.hash = h
        self.hash_history.append(h)

    def unmake_null_move(self) -> None:
        _, _, _, _, ep, halfmove, h = self.history.pop()
        self.hash_history.pop()
        self.side = -self.side
        self.ep, self.halfmove, self.hash = ep, halfmove, h

    def has_non_pawn_material(self, side: int) -> bool:
        """Does `side` have anything besides its king and pawns?"""
        s = self.squares
        return any(KNIGHT <= s[sq] * side <= QUEEN for sq in ON_BOARD)

    # ------------------------------------------------------- game status

    def is_capture(self, m: Move) -> bool:
        return self.squares[m.to] != EMPTY or (
            m.to == self.ep and abs(self.squares[m.frm]) == PAWN)

    def is_repetition(self) -> bool:
        """Has the current position occurred before since the last capture
        or pawn move? (Twofold - good enough to stop the search from
        shuffling pieces into a draw.)"""
        recent = self.hash_history[-(self.halfmove + 1):-1]
        return self.hash in recent

    def is_threefold(self) -> bool:
        recent = self.hash_history[-(self.halfmove + 1):]
        return recent.count(self.hash) >= 3

    def insufficient_material(self) -> bool:
        pieces = [abs(self.squares[sq]) for sq in ON_BOARD
                  if self.squares[sq] not in (EMPTY, KING, -KING)]
        return not pieces or pieces in ([KNIGHT], [BISHOP])

    def outcome(self) -> str | None:
        """'checkmate', 'stalemate', 'fifty-move rule', 'threefold
        repetition', 'insufficient material', or None if the game goes on."""
        if not self.legal_moves():
            return "checkmate" if self.in_check() else "stalemate"
        if self.halfmove >= 100:
            return "fifty-move rule"
        if self.is_threefold():
            return "threefold repetition"
        if self.insufficient_material():
            return "insufficient material"
        return None

    def parse_move(self, text: str) -> Move:
        """Find the legal move written in UCI notation, e.g. 'e2e4', 'e7e8q'."""
        text = text.strip().lower()
        for m in self.legal_moves():
            if m.uci() == text:
                return m
        raise ValueError(f"illegal move: {text}")

    def __str__(self) -> str:
        lines = []
        for rank in range(7, -1, -1):
            row = []
            for file in range(8):
                p = self.squares[square(file, rank)]
                if p == EMPTY:
                    row.append(".")
                else:
                    letter = PIECE_LETTERS[abs(p)]
                    row.append(letter.upper() if p > 0 else letter)
            lines.append(f"{rank + 1}  {' '.join(row)}")
        lines.append("   a b c d e f g h")
        return "\n".join(lines)


def perft(board: Board, depth: int) -> int:
    """Count leaf nodes of the legal move tree - the standard way to check a
    move generator against known-correct numbers."""
    if depth == 0:
        return 1
    moves = board.legal_moves()
    if depth == 1:
        return len(moves)
    total = 0
    for m in moves:
        board.make_move(m)
        total += perft(board, depth - 1)
        board.unmake_move()
    return total
