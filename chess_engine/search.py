"""Search: iterative-deepening negamax with alpha-beta pruning.

Extras on top of plain alpha-beta:
  * quiescence search (keep searching captures at the leaves, so the engine
    doesn't stop right before losing its queen - the "horizon effect")
  * move ordering: best move from the previous iteration / hash table first,
    then captures by MVV-LVA (most valuable victim, least valuable attacker),
    then killer moves
  * transposition table keyed by Zobrist hash
  * check extension
  * time control, checked every 2048 nodes
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from .board import EMPTY, PAWN, Board, Move
from .evaluate import PIECE_VALUES, evaluate

MATE = 100_000
INF = 1_000_000
MAX_PLY = 64

EXACT, LOWER, UPPER = 0, 1, 2


class _Stop(Exception):
    pass


@dataclass
class SearchInfo:
    depth: int
    score: int
    nodes: int
    seconds: float
    pv: list[Move] = field(default_factory=list)

    @property
    def mate_in(self) -> Optional[int]:
        """Moves to mate (negative if we are being mated), or None."""
        if abs(self.score) < MATE - MAX_PLY:
            return None
        plies = MATE - abs(self.score)
        moves = (plies + 1) // 2
        return moves if self.score > 0 else -moves


class Searcher:
    def __init__(self, tt_entries: int = 1_000_000):
        self.tt: dict[int, tuple[int, int, int, Optional[Move]]] = {}
        self.tt_entries = tt_entries
        self.killers: list[list[Optional[Move]]] = [[None, None] for _ in range(MAX_PLY + 1)]
        self.nodes = 0
        self._deadline: Optional[float] = None
        self._stop_event: Optional[threading.Event] = None

    def clear(self) -> None:
        self.tt.clear()

    # ------------------------------------------------------------------ API

    def search(
        self,
        board: Board,
        max_depth: int = MAX_PLY,
        time_limit: Optional[float] = None,
        stop_event: Optional[threading.Event] = None,
        on_info: Optional[Callable[[SearchInfo], None]] = None,
    ) -> tuple[Optional[Move], SearchInfo]:
        """Search `board` and return (best move, info about the last finished
        iteration). The board is left unchanged."""
        board = board.copy()
        start = time.monotonic()
        self._deadline = start + time_limit if time_limit is not None else None
        self._stop_event = stop_event
        self.nodes = 0
        self.killers = [[None, None] for _ in range(MAX_PLY + 1)]

        moves = board.legal_moves()
        info = SearchInfo(0, 0, 0, 0.0)
        if not moves:
            return None, info
        best = moves[0]

        for depth in range(1, max_depth + 1):
            try:
                move, score = self._root(board, moves, depth, best)
            except _Stop:
                break
            best = move
            info = SearchInfo(depth, score, self.nodes, time.monotonic() - start,
                              self._pv(board, best, depth))
            if on_info:
                on_info(info)
            if abs(score) >= MATE - MAX_PLY:
                break  # found a forced mate, deeper search won't change that
            if (self._deadline is not None
                    and time.monotonic() - start > 0.5 * (self._deadline - start)):
                break  # the next iteration would almost certainly not finish
        return best, info

    # ------------------------------------------------------------ internals

    def _check_stop(self) -> None:
        if self._stop_event is not None and self._stop_event.is_set():
            raise _Stop
        if self._deadline is not None and time.monotonic() >= self._deadline:
            raise _Stop

    def _root(self, board: Board, moves: list[Move], depth: int, prev_best: Move):
        alpha, beta = -INF, INF
        best_move, best_score = prev_best, -INF
        for m in self._order(board, moves, prev_best, 0):
            board.make_move(m)
            try:
                score = -self._negamax(board, depth - 1, -beta, -alpha, 1)
            finally:
                board.unmake_move()
            if score > best_score:
                best_score, best_move = score, m
            alpha = max(alpha, score)
        return best_move, best_score

    def _negamax(self, board: Board, depth: int, alpha: int, beta: int, ply: int) -> int:
        self.nodes += 1
        if self.nodes & 2047 == 0:
            self._check_stop()
        if board.halfmove >= 100 or board.is_repetition():
            return 0

        in_check = board.in_check()
        if in_check:
            depth += 1  # don't stop searching in the middle of a check sequence
        if depth <= 0 or ply >= MAX_PLY:
            return self._quiesce(board, alpha, beta, ply)

        alpha_orig = alpha
        tt_move = None
        entry = self.tt.get(board.hash)
        if entry is not None:
            e_depth, e_score, e_flag, tt_move = entry
            if e_depth >= depth:
                e_score = _score_from_tt(e_score, ply)
                if e_flag == EXACT:
                    return e_score
                if e_flag == LOWER:
                    alpha = max(alpha, e_score)
                else:
                    beta = min(beta, e_score)
                if alpha >= beta:
                    return e_score

        moves = board.legal_moves()
        if not moves:
            return -MATE + ply if in_check else 0

        best_score, best_move = -INF, None
        for m in self._order(board, moves, tt_move, ply):
            capture = board.is_capture(m)
            board.make_move(m)
            try:
                score = -self._negamax(board, depth - 1, -beta, -alpha, ply + 1)
            finally:
                board.unmake_move()
            if score > best_score:
                best_score, best_move = score, m
            if score > alpha:
                alpha = score
            if alpha >= beta:
                if not capture and m != self.killers[ply][0]:
                    self.killers[ply][1] = self.killers[ply][0]
                    self.killers[ply][0] = m
                break

        if best_score <= alpha_orig:
            flag = UPPER
        elif best_score >= beta:
            flag = LOWER
        else:
            flag = EXACT
        if len(self.tt) >= self.tt_entries:
            self.tt.clear()  # crude, but keeps memory bounded
        self.tt[board.hash] = (depth, _score_to_tt(best_score, ply), flag, best_move)
        return best_score

    def _quiesce(self, board: Board, alpha: int, beta: int, ply: int) -> int:
        self.nodes += 1
        if self.nodes & 2047 == 0:
            self._check_stop()
        stand_pat = evaluate(board)
        if stand_pat >= beta:
            return stand_pat
        alpha = max(alpha, stand_pat)
        for m in self._order(board, board.legal_moves(captures_only=True), None, ply):
            board.make_move(m)
            try:
                score = -self._quiesce(board, -beta, -alpha, ply + 1)
            finally:
                board.unmake_move()
            if score >= beta:
                return score
            alpha = max(alpha, score)
        return alpha

    def _order(self, board: Board, moves: list[Move], first: Optional[Move], ply: int):
        s = board.squares
        killers = self.killers[min(ply, MAX_PLY)]

        def key(m: Move) -> int:
            if m == first:
                return 10_000_000
            victim = s[m.to]
            if victim != EMPTY:
                return 1_000_000 + 10 * PIECE_VALUES[abs(victim)] - PIECE_VALUES[abs(s[m.frm])]
            if m.to == board.ep and abs(s[m.frm]) == PAWN:
                return 1_000_000 + 10 * PIECE_VALUES[PAWN] - PIECE_VALUES[PAWN]
            if m.promo:
                return 900_000 + PIECE_VALUES[m.promo]
            if m == killers[0]:
                return 800_000
            if m == killers[1]:
                return 700_000
            return 0

        return sorted(moves, key=key, reverse=True)

    def _pv(self, board: Board, first: Move, depth: int) -> list[Move]:
        """Principal variation, recovered by following best moves in the TT."""
        pv = [first]
        b = board.copy()
        b.make_move(first)
        seen = {b.hash}
        while len(pv) < depth:
            entry = self.tt.get(b.hash)
            if not entry or entry[3] is None or entry[3] not in b.legal_moves():
                break
            b.make_move(entry[3])
            if b.hash in seen:
                break
            seen.add(b.hash)
            pv.append(entry[3])
        return pv


def _score_to_tt(score: int, ply: int) -> int:
    # Mate scores are stored relative to this node, not the root, so they
    # stay correct when the same position is reached at a different depth.
    if score >= MATE - MAX_PLY:
        return score + ply
    if score <= -MATE + MAX_PLY:
        return score - ply
    return score


def _score_from_tt(score: int, ply: int) -> int:
    if score >= MATE - MAX_PLY:
        return score - ply
    if score <= -MATE + MAX_PLY:
        return score + ply
    return score
