"""RQ task entry points. Workers import this module by dotted path."""
from app.engine import analyze_pgn


def analyze_pgn_job(
    pgn: str,
    user_id: str,
    *,
    depth: int = 12,
    time_limit: float = 0.2,
    max_plies: int = 100,
) -> dict:
    # Keep the user ID in job args for ownership checks in the API. The analysis itself
    # intentionally does not write to Supabase in this first backend milestone.
    if not user_id:
        raise ValueError("A job owner is required.")
    return analyze_pgn(pgn, depth=depth, time_limit=time_limit, max_plies=max_plies)
