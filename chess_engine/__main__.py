"""Command line entry point.

    python -m chess_engine            UCI mode (for chess GUIs)
    python -m chess_engine gui        play in a pygame window
    python -m chess_engine play       play in the terminal
    python -m chess_engine perft 4    count move-tree leaves (move generator check)
    python -m chess_engine bench      search a few positions and report speed
"""

from __future__ import annotations

import argparse
import time

from .board import BLACK, START_FEN, WHITE, Board, perft
from .search import Searcher

BENCH_FENS = [
    START_FEN,
    "r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3",
    "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1",
    "8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1",
]


def play_terminal(human: int, think_time: float) -> None:
    board, searcher = Board(), Searcher()
    while (outcome := board.outcome()) is None:
        print(f"\n{board}\n")
        if board.side == human:
            text = input("your move (e.g. e2e4, 'quit'): ").strip()
            if text in ("quit", "exit"):
                return
            try:
                board.make_move(board.parse_move(text))
            except ValueError as e:
                print(e)
        else:
            move, info = searcher.search(board, time_limit=think_time)
            print(f"engine plays {move}  (depth {info.depth}, score {info.score} cp)")
            board.make_move(move)
    print(f"\n{board}\n\nGame over: {outcome}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="chess_engine")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("uci", help="run the UCI protocol on stdin/stdout (default)")
    for name in ("gui", "play"):
        p = sub.add_parser(name, help=f"play against the engine ({name})")
        p.add_argument("--black", action="store_true", help="you play black")
        p.add_argument("--time", type=float, default=2.0, help="engine seconds per move")
    p = sub.add_parser("perft", help="count leaf nodes to a given depth")
    p.add_argument("depth", type=int)
    p.add_argument("--fen", default=START_FEN)
    p = sub.add_parser("bench", help="search a few positions to a fixed depth")
    p.add_argument("--depth", type=int, default=4)
    args = parser.parse_args()

    if args.cmd in (None, "uci"):
        from .uci import main as uci_main
        uci_main()
    elif args.cmd == "gui":
        from .gui import run
        run(human=BLACK if args.black else WHITE, think_time=args.time)
    elif args.cmd == "play":
        play_terminal(BLACK if args.black else WHITE, args.time)
    elif args.cmd == "perft":
        board = Board(args.fen)
        start = time.perf_counter()
        nodes = perft(board, args.depth)
        secs = time.perf_counter() - start
        print(f"perft({args.depth}) = {nodes}  [{secs:.2f} s, {nodes / secs:,.0f} nodes/s]")
    elif args.cmd == "bench":
        total_nodes, total_time = 0, 0.0
        for fen in BENCH_FENS:
            searcher = Searcher()
            move, info = searcher.search(Board(fen), max_depth=args.depth)
            total_nodes += info.nodes
            total_time += info.seconds
            print(f"{move}  depth {info.depth}  {info.nodes:>8} nodes  {info.seconds:6.2f} s  {fen}")
        print(f"total {total_nodes} nodes in {total_time:.2f} s = "
              f"{total_nodes / total_time:,.0f} nodes/s")


if __name__ == "__main__":
    main()
