"""Stockfish UCI integration and position/game analysis."""
from __future__ import annotations

import io
import logging
import threading
from contextlib import contextmanager
from typing import Any, Iterator

import chess
import chess.engine
import chess.pgn

from app.classification import classify_move, move_tags
from app import settings

logger = logging.getLogger(__name__)
_engine_slots = threading.BoundedSemaphore(settings.MAX_ENGINE_CONCURRENCY)
MATE_SCORE = 100_000


class EngineUnavailable(RuntimeError):
    """Stockfish could not be started or used."""


class InvalidPosition(ValueError):
    """The supplied FEN or PGN does not describe a supported valid game."""


@contextmanager
def open_engine() -> Iterator[chess.engine.SimpleEngine]:
    """Open one Stockfish process while respecting this process's concurrency cap."""
    acquired = _engine_slots.acquire(blocking=False)
    if not acquired:
        raise EngineUnavailable("All analysis slots are busy. Retry shortly.")
    engine = None
    try:
        try:
            engine = chess.engine.SimpleEngine.popen_uci(settings.STOCKFISH_PATH, timeout=10.0)
            engine.configure({"Threads": settings.STOCKFISH_THREADS, "Hash": settings.STOCKFISH_HASH_MB})
        except (OSError, chess.engine.EngineError, chess.engine.EngineTerminatedError) as exc:
            if engine is not None:
                try:
                    engine.quit()
                except Exception:
                    pass
            raise EngineUnavailable(
                "Stockfish could not start. Check STOCKFISH_PATH and the container build logs."
            ) from exc
        yield engine
    finally:
        if engine is not None:
            try:
                engine.quit()
            except Exception as exc:  # pragma: no cover - depends on process shutdown timing
                logger.warning("Stockfish shutdown issue: %s", exc)
        _engine_slots.release()


def stockfish_identity() -> dict[str, str]:
    with open_engine() as engine:
        name = engine.id.get("name", "Stockfish")
        author = engine.id.get("author", "")
        return {"name": name, "author": author}


def _score_display(score: chess.engine.Score) -> str:
    mate = score.mate()
    if mate is not None:
        return f"+M{mate}" if mate > 0 else f"-M{abs(mate)}"
    cp = score.score()
    if cp is None:
        return "unknown"
    return f"{cp / 100:+.2f}"


def _score_details(score: chess.engine.PovScore, side_to_move: chess.Color) -> dict[str, Any]:
    white = score.pov(chess.WHITE)
    current = score.pov(side_to_move)
    white_cp = white.score()
    current_cp = current.score()
    return {
        "white": {
            "centipawns": white_cp,
            "pawns": round(white_cp / 100, 2) if white_cp is not None else None,
            "mate_in": white.mate(),
            "display": _score_display(white),
        },
        "side_to_move": {
            "centipawns": current_cp,
            "pawns": round(current_cp / 100, 2) if current_cp is not None else None,
            "mate_in": current.mate(),
            "display": _score_display(current),
        },
        "_white_numeric": white.score(mate_score=MATE_SCORE),
    }


def _terminal_status(board: chess.Board) -> str | None:
    if board.is_checkmate():
        return "checkmate"
    if board.is_stalemate():
        return "stalemate"
    if board.is_insufficient_material():
        return "insufficient_material"
    if board.is_seventyfive_moves():
        return "seventyfive_move_draw"
    if board.is_fivefold_repetition():
        return "fivefold_repetition_draw"
    return None


def _terminal_evaluation(board: chess.Board, status: str) -> dict[str, Any]:
    if status == "checkmate":
        white_won = board.turn == chess.BLACK
        white_numeric = MATE_SCORE if white_won else -MATE_SCORE
        white_display = "+M0" if white_won else "-M0"
        side_display = "-M0"
        white_mate = 0 if white_won else 0
        side_mate = 0
        white_cp = current_cp = None
        white_pawns = current_pawns = None
    else:
        white_numeric = 0
        white_display = side_display = "+0.00"
        white_mate = side_mate = None
        white_cp = current_cp = 0
        white_pawns = current_pawns = 0.0
    return {
        "white": {"centipawns": white_cp, "pawns": white_pawns, "mate_in": white_mate, "display": white_display},
        "side_to_move": {"centipawns": current_cp, "pawns": current_pawns, "mate_in": side_mate, "display": side_display},
        "_white_numeric": white_numeric,
    }


def _line_payload(board: chess.Board, info: dict[str, Any], rank: int) -> dict[str, Any]:
    score = info.get("score")
    if score is None:
        raise EngineUnavailable("Stockfish returned no evaluation for a non-terminal position.")
    pv = info.get("pv", [])
    pv_board = board.copy(stack=False)
    pv_uci: list[str] = []
    pv_san: list[str] = []
    first_move: dict[str, str] | None = None
    for move in pv:
        if move not in pv_board.legal_moves:
            break
        san = pv_board.san(move)
        if first_move is None:
            first_move = {"uci": move.uci(), "san": san}
        pv_uci.append(move.uci())
        pv_san.append(san)
        pv_board.push(move)
    score_obj = _score_details(score, board.turn)
    return {
        "rank": rank,
        "evaluation": {k: v for k, v in score_obj.items() if not k.startswith("_")},
        "best_move": first_move,
        "principal_variation_uci": pv_uci,
        "principal_variation_san": pv_san,
        "depth": info.get("depth"),
        "seldepth": info.get("seldepth"),
        "nodes": info.get("nodes"),
        "time_seconds": info.get("time"),
    }


def evaluate_board(
    engine: chess.engine.SimpleEngine,
    board: chess.Board,
    *,
    depth: int,
    time_limit: float,
    multipv: int = 1,
) -> dict[str, Any]:
    terminal = _terminal_status(board)
    if terminal:
        return {"terminal_status": terminal, "evaluation": _terminal_evaluation(board, terminal), "lines": []}

    try:
        raw = engine.analyse(
            board,
            chess.engine.Limit(depth=depth, time=time_limit),
            multipv=multipv,
        )
    except (chess.engine.EngineError, chess.engine.EngineTerminatedError, TimeoutError) as exc:
        raise EngineUnavailable("Stockfish analysis failed. Retry with lower depth or time limit.") from exc

    infos = raw if isinstance(raw, list) else [raw]
    if not infos:
        raise EngineUnavailable("Stockfish returned an empty analysis result.")
    lines = [_line_payload(board, info, rank + 1) for rank, info in enumerate(infos)]
    score = infos[0].get("score")
    if score is None:
        raise EngineUnavailable("Stockfish returned no evaluation.")
    score_obj = _score_details(score, board.turn)
    return {
        "terminal_status": None,
        "evaluation": score_obj,
        "lines": lines,
    }


def _validate_fen(fen: str) -> chess.Board:
    try:
        board = chess.Board(fen)
    except ValueError as exc:
        raise InvalidPosition(f"Invalid FEN: {exc}") from exc
    if not board.is_valid():
        raise InvalidPosition("The FEN is syntactically readable but describes an invalid chess position.")
    return board


def analyze_position(fen: str, *, depth: int, time_limit: float, multipv: int) -> dict[str, Any]:
    board = _validate_fen(fen)
    if _terminal_status(board):
        result = evaluate_board_without_engine(board)
        return {
            "fen": board.fen(),
            "turn": "white" if board.turn == chess.WHITE else "black",
            "is_check": board.is_check(),
            "legal_moves_count": board.legal_moves.count(),
            "engine": {"name": "Stockfish"},
            "depth_requested": depth,
            "multipv_requested": multipv,
            "terminal_status": result["terminal_status"],
            "evaluation": {k: v for k, v in result["evaluation"].items() if not k.startswith("_")},
            "lines": [],
        }
    with open_engine() as engine:
        result = evaluate_board(engine, board, depth=depth, time_limit=time_limit, multipv=multipv)
        name = engine.id.get("name", "Stockfish")
    return {
        "fen": board.fen(),
        "turn": "white" if board.turn == chess.WHITE else "black",
        "is_check": board.is_check(),
        "legal_moves_count": board.legal_moves.count(),
        "engine": {"name": name},
        "depth_requested": depth,
        "time_limit_seconds": time_limit,
        "multipv_requested": multipv,
        "terminal_status": result["terminal_status"],
        "evaluation": {k: v for k, v in result["evaluation"].items() if not k.startswith("_")},
        "lines": result["lines"],
    }


def evaluate_board_without_engine(board: chess.Board) -> dict[str, Any]:
    terminal = _terminal_status(board)
    if not terminal:
        raise ValueError("This helper is only for terminal positions.")
    return {"terminal_status": terminal, "evaluation": _terminal_evaluation(board, terminal), "lines": []}


def analyze_pgn(
    pgn_text: str,
    *,
    depth: int,
    time_limit: float,
    max_plies: int,
) -> dict[str, Any]:
    stream = io.StringIO(pgn_text)
    try:
        game = chess.pgn.read_game(stream)
    except (ValueError, IndexError) as exc:
        raise InvalidPosition(f"Could not parse PGN: {exc}") from exc
    if game is None:
        raise InvalidPosition("No PGN game was found in the request.")
    if game.errors:
        messages = "; ".join(str(err) for err in game.errors[:3])
        raise InvalidPosition(f"PGN contains parsing errors: {messages}")
    # This endpoint intentionally accepts one game per job so each result has a clear owner and lifecycle.
    second_game = chess.pgn.read_game(stream)
    if second_game is not None:
        raise InvalidPosition("Submit one PGN game per request.")

    variant = game.headers.get("Variant", "Standard")
    if variant not in {"Standard", "Chess"}:
        raise InvalidPosition("Only standard-chess PGNs are supported in this version.")
    board = game.board()
    if not isinstance(board, chess.Board) or not board.is_valid():
        raise InvalidPosition("Only valid standard-chess PGNs are supported in this version.")
    moves = list(game.mainline_moves())
    if not moves:
        raise InvalidPosition("The PGN does not contain any moves.")
    if len(moves) > max_plies:
        raise InvalidPosition(f"This game has {len(moves)} plies; max_plies is {max_plies}.")

    headers = {
        key: game.headers.get(key)
        for key in ("Event", "Site", "Date", "Round", "White", "Black", "Result")
        if game.headers.get(key) not in (None, "", "?")
    }

    move_records: list[dict[str, Any]] = []
    with open_engine() as engine:
        engine_name = engine.id.get("name", "Stockfish")
        current = evaluate_board(engine, board, depth=depth, time_limit=time_limit, multipv=1)
        initial_eval = {k: v for k, v in current["evaluation"].items() if not k.startswith("_")}
        for ply_index, move in enumerate(moves, start=1):
            if move not in board.legal_moves:
                # python-chess PGN parsing generally catches this first; retain a defensive check.
                raise InvalidPosition(f"Illegal move at ply {ply_index}.")
            mover = board.turn
            san = board.san(move)
            fen_before = board.fen()
            is_capture = board.is_capture(move)
            is_en_passant = board.is_en_passant(move)
            is_castling = board.is_castling(move)
            promotion = move.promotion
            gives_check = board.gives_check(move)
            best_line = current["lines"][0] if current["lines"] else None
            best_move = best_line["best_move"] if best_line else None
            before_eval = current["evaluation"]
            before_numeric = int(before_eval["_white_numeric"])

            board.push(move)
            after = evaluate_board(engine, board, depth=depth, time_limit=time_limit, multipv=1)
            after_eval = after["evaluation"]
            after_numeric = int(after_eval["_white_numeric"])
            mover_sign = 1 if mover == chess.WHITE else -1
            raw_loss = round((before_numeric - after_numeric) * mover_sign)
            loss_cp = max(0, raw_loss)
            best_played = bool(best_move and best_move["uci"] == move.uci())
            classification = classify_move(loss_cp, best_played)
            tags = move_tags(
                is_capture=is_capture,
                is_en_passant=is_en_passant,
                is_castling=is_castling,
                promotion=promotion,
                gives_check=gives_check,
                is_checkmate=board.is_checkmate(),
            )
            move_records.append({
                "ply": ply_index,
                "fullmove_number": (ply_index + 1) // 2,
                "color": "white" if mover == chess.WHITE else "black",
                "san": san,
                "uci": move.uci(),
                "fen_before": fen_before,
                "fen_after": board.fen(),
                "best_move": best_move,
                "best_move_played": best_played,
                "classification": classification,
                "estimated_loss_cp": loss_cp,
                "raw_loss_cp": raw_loss,
                "evaluation_before": {k: v for k, v in before_eval.items() if not k.startswith("_")},
                "evaluation_after": {k: v for k, v in after_eval.items() if not k.startswith("_")},
                "tags": tags,
            })
            current = after

    counts: dict[str, int] = {}
    for record in move_records:
        counts[record["classification"]] = counts.get(record["classification"], 0) + 1
    final_eval = {k: v for k, v in current["evaluation"].items() if not k.startswith("_")}
    return {
        "engine": {"name": engine_name},
        "analysis_settings": {"depth": depth, "time_limit_seconds": time_limit, "max_plies": max_plies},
        "headers": headers,
        "start_fen": moves and game.board().fen(),
        "final_fen": board.fen(),
        "plies_analyzed": len(move_records),
        "initial_evaluation": initial_eval,
        "final_evaluation": final_eval,
        "classification_counts": counts,
        "move_classification_policy": "chesspear-heuristic-v1",
        "moves": move_records,
        "limitations": [
            "Move labels use Chesspear's initial centipawn-loss heuristic and are not official Chess.com/Chessigma labels.",
            "Tactical motif detection is not yet implemented; tags currently cover checks, checkmates, captures, en passant, castling and promotions.",
            "Engine analysis depends on requested depth and time limits; higher settings cost more CPU time.",
        ],
    }
