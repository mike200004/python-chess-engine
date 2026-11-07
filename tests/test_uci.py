"""Drive the engine over the UCI protocol in a real subprocess."""

import subprocess
import sys

from chess_engine.board import Board


def run_uci(commands, timeout=30):
    """Send commands one at a time, like a GUI would: after a finite 'go',
    wait for 'bestmove' before sending the next command."""
    proc = subprocess.Popen(
        [sys.executable, "-m", "chess_engine", "uci"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
    out = []
    try:
        for cmd in commands:
            proc.stdin.write(cmd + "\n")
            proc.stdin.flush()
            if cmd.startswith("go") and "infinite" not in cmd:
                while True:
                    line = proc.stdout.readline()
                    assert line, "engine exited before bestmove"
                    out.append(line.strip())
                    if line.startswith("bestmove"):
                        break
        rest, _ = proc.communicate(timeout=timeout)  # also closes stdin
        out += rest.splitlines()
    finally:
        proc.kill()
    return out


def test_handshake():
    out = run_uci(["uci", "isready", "quit"])
    assert any(line.startswith("id name") for line in out)
    assert "uciok" in out
    assert "readyok" in out


def test_go_depth_returns_legal_move():
    out = run_uci(["position startpos moves e2e4 e7e5", "go depth 3", "isready", "quit"])
    best = [line for line in out if line.startswith("bestmove")]
    assert len(best) == 1
    board = Board()
    for m in ("e2e4", "e7e5"):
        board.make_move(board.parse_move(m))
    board.parse_move(best[0].split()[1])  # raises if illegal
    assert any(line.startswith("info depth 3") for line in out)


def test_position_fen_and_mate_score():
    out = run_uci(["position fen 6k1/5ppp/8/8/8/8/8/R5K1 w - - 0 1", "go depth 2", "quit"])
    assert "bestmove a1a8" in out
    assert any("score mate 1" in line for line in out)


def test_go_infinite_then_stop():
    out = run_uci(["position startpos", "go infinite", "stop", "quit"], timeout=30)
    assert any(line.startswith("bestmove") for line in out)
