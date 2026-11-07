"""Play against the engine in a pygame window.

Click a piece, then click where it should go. Keys: U = undo your last move,
R = new game, F = flip the board, Esc = quit. Pawns promote to a queen.
"""

from __future__ import annotations

import threading
from typing import Optional

from .board import (BLACK, EMPTY, KING, PIECE_LETTERS, WHITE, Board, Move, file_of, rank_of,
                    square)
from .search import Searcher

SQ = 80
SIZE = SQ * 8
LIGHT, DARK = (238, 238, 210), (118, 150, 86)
SELECTED, TARGET, LAST_MOVE, CHECK = (246, 246, 105), (186, 202, 68), (205, 210, 106), (235, 97, 80)
GLYPHS = {"k": "♚", "q": "♛", "r": "♜", "b": "♝", "n": "♞", "p": "♟"}
SYMBOL_FONTS = ["segoeuisymbol", "dejavusans", "applesymbols", "arialunicodems",
                "notosanssymbols2", "freeserif"]


def _find_chess_font(pygame, size: int):
    """Return a font that really contains the chess symbols, or None.

    match_font() silently substitutes another font when the one asked for is
    missing, and a font without the glyphs draws the same empty box for every
    piece - so render a king and a pawn and make sure they differ.
    """
    to_bytes = getattr(pygame.image, "tobytes", None) or pygame.image.tostring
    for name in SYMBOL_FONTS:
        path = pygame.font.match_font(name)
        if not path:
            continue
        font = pygame.font.Font(path, size)
        king = font.render(GLYPHS["k"], True, (0, 0, 0))
        pawn = font.render(GLYPHS["p"], True, (0, 0, 0))
        if king.get_size() != pawn.get_size() or to_bytes(king, "RGBA") != to_bytes(pawn, "RGBA"):
            return font
    return None


def run(human: int = WHITE, think_time: float = 2.0) -> None:
    import pygame  # optional dependency, only needed for the GUI

    pygame.init()
    screen = pygame.display.set_mode((SIZE, SIZE + 30))
    pygame.display.set_caption("python-chess-engine")
    piece_font = _find_chess_font(pygame, int(SQ * 0.8))
    letter_font = pygame.font.SysFont(None, int(SQ * 0.6))
    status_font = pygame.font.SysFont(None, 24)

    board = Board()
    searcher = Searcher()
    flipped = human == BLACK
    selected: Optional[int] = None
    targets: list[Move] = []
    last: Optional[Move] = None
    engine_move: list[Optional[Move]] = []
    thinking: Optional[threading.Thread] = None

    def to_screen(sq: int) -> tuple[int, int]:
        f, r = file_of(sq), rank_of(sq)
        if flipped:
            return (7 - f) * SQ, r * SQ
        return f * SQ, (7 - r) * SQ

    def from_screen(x: int, y: int) -> int:
        f, r = x // SQ, 7 - y // SQ
        return square(7 - f, 7 - r) if flipped else square(f, r)

    def draw_piece(p: int, x: int, y: int) -> None:
        letter = PIECE_LETTERS[abs(p)]
        colour = (255, 255, 255) if p > 0 else (20, 20, 20)
        if piece_font:
            outline = piece_font.render(GLYPHS[letter], True, (0, 0, 0) if p > 0 else (90, 90, 90))
            glyph = piece_font.render(GLYPHS[letter], True, colour)
            rect = glyph.get_rect(center=(x + SQ // 2, y + SQ // 2))
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                screen.blit(outline, rect.move(dx, dy))
            screen.blit(glyph, rect)
        else:
            pygame.draw.circle(screen, colour, (x + SQ // 2, y + SQ // 2), SQ // 3)
            text = letter_font.render(letter.upper(), True, (20, 20, 20) if p > 0 else (240, 240, 240))
            screen.blit(text, text.get_rect(center=(x + SQ // 2, y + SQ // 2)))

    def draw(status: str) -> None:
        for r in range(8):
            for f in range(8):
                sq = square(f, r)
                x, y = to_screen(sq)
                colour = LIGHT if (f + r) % 2 else DARK
                if last and sq in (last.frm, last.to):
                    colour = LAST_MOVE
                if sq == selected:
                    colour = SELECTED
                if board.squares[sq] == KING * board.side and board.in_check():
                    colour = CHECK
                pygame.draw.rect(screen, colour, (x, y, SQ, SQ))
                if any(m.to == sq for m in targets):
                    pygame.draw.circle(screen, TARGET, (x + SQ // 2, y + SQ // 2), SQ // 7)
                p = board.squares[sq]
                if p != EMPTY:
                    draw_piece(p, x, y)
        pygame.draw.rect(screen, (40, 40, 40), (0, SIZE, SIZE, 30))
        screen.blit(status_font.render(status, True, (230, 230, 230)), (8, SIZE + 7))
        pygame.display.flip()

    def start_engine() -> None:
        nonlocal thinking
        snapshot = board.copy()

        def work():
            move, _ = searcher.search(snapshot, time_limit=think_time)
            engine_move.append(move)

        thinking = threading.Thread(target=work, daemon=True)
        thinking.start()

    clock = pygame.time.Clock()
    running = True
    while running:
        outcome = board.outcome()
        engine_busy = thinking is not None and thinking.is_alive()
        if outcome:
            status = f"Game over: {outcome}. R = new game"
        elif engine_busy:
            status = "Engine is thinking..."
        else:
            status = "Your move" if board.side == human else ""

        if not outcome and board.side != human and thinking is None:
            start_engine()
        if engine_move:
            move = engine_move.pop()
            thinking = None
            if move:
                board.make_move(move)
                last = move

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_f:
                    flipped = not flipped
                elif event.key in (pygame.K_r, pygame.K_u) and not engine_busy:
                    if event.key == pygame.K_r:
                        board, last = Board(), None
                    else:
                        # undo the engine's reply and our move
                        for _ in range(2 if board.side == human else 1):
                            if board.history:
                                board.unmake_move()
                        last = board.history[-1][0] if board.history else None
                    selected, targets = None, []
            elif (event.type == pygame.MOUSEBUTTONDOWN and event.button == 1
                  and board.side == human and not outcome and event.pos[1] < SIZE):
                sq = from_screen(*event.pos)
                chosen = [m for m in targets if m.to == sq]
                if chosen:
                    move = next((m for m in chosen if m.promo in (0, 5)), chosen[0])
                    board.make_move(move)
                    last, selected, targets = move, None, []
                elif board.squares[sq] * board.side > 0:
                    selected = sq
                    targets = [m for m in board.legal_moves() if m.frm == sq]
                else:
                    selected, targets = None, []

        draw(status)
        clock.tick(30)
    pygame.quit()
