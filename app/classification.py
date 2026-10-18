"""Initial Chesspear classification policy.

These are transparent heuristics, not official Chess.com/Chessigma thresholds. Tune only
against a fixed regression set and keep the policy versioned as the product evolves.
"""
from __future__ import annotations


def classify_move(loss_cp: int, best_move_played: bool) -> str:
    """Classify the played move from engine-estimated loss in the mover's perspective."""
    if best_move_played:
        return "best"
    loss = max(0, loss_cp)
    if loss <= 20:
        return "excellent"
    if loss <= 50:
        return "good"
    if loss <= 100:
        return "inaccuracy"
    if loss <= 200:
        return "mistake"
    return "blunder"


def move_tags(*, is_capture: bool, is_en_passant: bool, is_castling: bool,
              promotion: int | None, gives_check: bool, is_checkmate: bool) -> list[str]:
    tags: list[str] = []
    if is_capture:
        tags.append("capture")
    if is_en_passant:
        tags.append("en_passant")
    if is_castling:
        tags.append("castling")
    if promotion is not None:
        tags.append("promotion")
    if gives_check:
        tags.append("check")
    if is_checkmate:
        tags.append("checkmate")
    return tags
