# Chesspear analysis accuracy test plan

Before public launch, build a versioned regression suite containing:

- Initial position with equal-material evaluation.
- A winning position where the engine reports a forced mate.
- A position that is checkmate, stalemate, or insufficient material.
- Castling, en passant, and promotion PGNs.
- White makes an obvious blunder and Black makes an equivalent blunder (sign perspective must mirror).
- A PGN ending in checkmate.
- Invalid FEN, impossible king/check states, malformed PGN, multiple PGNs, and a PGN over the plies cap.
- Mate found then lost; drawn endgame; repeated positions.

For each fixture, record expected legal behavior, expected score perspective, best-move legality, and classification-policy expectation. Do not hard-code an exact centipawn evaluation for every position unless engine version, depth, hash, and time limit are pinned. Compare scores within a tolerance where appropriate. Update the fixture version when the Stockfish binary changes.

Classification thresholds in `app/classification.py` are initial product policy, not ground truth. Audit false blunder/inaccuracy labels manually before tuning them.
