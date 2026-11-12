"""UCI (Universal Chess Interface) front end, so the engine can be loaded
into GUIs such as Arena, Cute Chess or En Croissant.

Spec: https://backscattering.de/chess/uci/
"""

from __future__ import annotations

import sys
import threading
from typing import Optional, TextIO

from . import __version__
from .board import START_FEN, WHITE, Board
from .search import MAX_PLY, Searcher, SearchInfo

ENGINE_NAME = f"python-chess-engine {__version__}"


def format_info(info: SearchInfo) -> str:
    mate = info.mate_in
    score = f"mate {mate}" if mate is not None else f"cp {info.score}"
    ms = int(info.seconds * 1000)
    nps = int(info.nodes / info.seconds) if info.seconds > 0 else 0
    pv = " ".join(m.uci() for m in info.pv)
    return (f"info depth {info.depth} score {score} nodes {info.nodes} "
            f"nps {nps} time {ms} pv {pv}")


def time_for_move(board: Board, args: dict[str, int]) -> Optional[float]:
    """Pick a time budget in seconds from the 'go' arguments."""
    if "movetime" in args:
        return args["movetime"] / 1000
    our_time = args.get("wtime" if board.side == WHITE else "btime")
    if our_time is None:
        return None
    increment = args.get("winc" if board.side == WHITE else "binc", 0)
    moves_to_go = args.get("movestogo", 30)
    budget_ms = our_time / max(moves_to_go, 1) + increment * 0.75
    budget_ms = min(budget_ms, our_time * 0.5)  # never plan to use more than half the clock
    return max(budget_ms - 50, 20) / 1000  # 50 ms safety margin for Python overhead


class UciEngine:
    def __init__(self, out: TextIO = sys.stdout):
        self.out = out
        self.board = Board()
        self.searcher = Searcher()
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._lock = threading.Lock()

    def send(self, line: str) -> None:
        with self._lock:
            self.out.write(line + "\n")
            self.out.flush()

    def handle(self, line: str) -> bool:
        """Process one command. Returns False when the engine should quit."""
        tokens = line.split()
        if not tokens:
            return True
        cmd, args = tokens[0], tokens[1:]
        if cmd == "uci":
            self.send(f"id name {ENGINE_NAME}")
            self.send("id author Michael")
            self.send("uciok")
        elif cmd == "isready":
            self.send("readyok")  # must answer even while a search is running
        elif cmd == "ucinewgame":
            self.wait()
            self.board = Board()
            self.searcher.clear()
        elif cmd == "position":
            self.wait()
            self.position(args)
        elif cmd == "go":
            self.wait()
            self.go(args)
        elif cmd == "stop":
            self._stop.set()
            self.wait()
        elif cmd == "quit":
            self._stop.set()
            self.wait()
            return False
        elif cmd == "d":  # debugging aid, not part of UCI
            self.send(str(self.board))
            self.send(f"fen {self.board.fen()}")
        return True

    def position(self, args: list[str]) -> None:
        if not args:
            return
        if args[0] == "startpos":
            fen, rest = START_FEN, args[1:]
        elif args[0] == "fen":
            if "moves" in args:
                i = args.index("moves")
                fen, rest = " ".join(args[1:i]), args[i:]
            else:
                fen, rest = " ".join(args[1:]), []
        else:
            return
        try:
            board = Board(fen)
            if rest and rest[0] == "moves":
                for text in rest[1:]:
                    board.make_move(board.parse_move(text))
        except ValueError as e:
            self.send(f"info string error: {e}")
            return
        self.board = board

    def go(self, args: list[str]) -> None:
        params: dict[str, int] = {}
        numeric = {"wtime", "btime", "winc", "binc", "movestogo", "depth", "movetime"}
        i = 0
        while i < len(args):
            if args[i] in numeric and i + 1 < len(args):
                try:
                    params[args[i]] = int(args[i + 1])
                except ValueError:
                    self.send(f"info string ignoring bad value for {args[i]}: {args[i + 1]}")
                i += 2
            else:
                i += 1  # 'infinite', 'ponder' and unknown tokens are ignored
        depth = params.get("depth", MAX_PLY)
        infinite = "infinite" in args
        limit = None if infinite else time_for_move(self.board, params)
        if limit is None and "depth" not in params and not infinite:
            limit = 5.0  # bare 'go': don't think forever

        self._stop.clear()
        board = self.board.copy()

        def run():
            move, _ = self.searcher.search(
                board, max_depth=depth, time_limit=limit, stop_event=self._stop,
                on_info=lambda info: self.send(format_info(info)))
            if infinite:
                # The search can end on its own (forced mate, max depth), but
                # in infinite mode UCI forbids bestmove before "stop".
                self._stop.wait()
            self.send(f"bestmove {move.uci() if move else '0000'}")

        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()

    def wait(self) -> None:
        if self._thread is not None:
            self._thread.join()
            self._thread = None


def main(stdin: TextIO = sys.stdin, stdout: TextIO = sys.stdout) -> None:
    engine = UciEngine(stdout)
    for line in stdin:
        if not engine.handle(line.strip()):
            break
    engine._stop.set()
    engine.wait()
