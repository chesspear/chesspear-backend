"""Chesspear REST API."""
from __future__ import annotations

import logging
import threading

import chess
import chess.engine
from fastapi import Depends, FastAPI, HTTPException, Path, status
from fastapi.middleware.cors import CORSMiddleware
from redis.exceptions import RedisError
from rq import Queue
from rq.exceptions import InvalidJobOperation, NoSuchJobError
from rq.job import Job

from app import settings
from app.engine import (
    EngineUnavailable,
    InvalidPosition,
    analyze_position,
    open_engine,
)
from app.queueing import analysis_queue, redis_connection
from app.schemas import GameAnalysisRequest, PositionAnalysisRequest
from app.security import CurrentUser, require_user

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

# The first readiness probe performs one UCI handshake per API process. Cache it so
# public health probes cannot repeatedly spawn Stockfish processes. The immutable
# container binary is not expected to change while the process is alive.
_ready_lock = threading.Lock()
_ready_engine_info: dict[str, str] | None = None

app = FastAPI(
    title="Chesspear Backend API",
    description=(
        "Stockfish-backed chess analysis for Chesspear. Position analysis is synchronous; "
        "full PGN analysis is queued and processed by an RQ worker."
    ),
    version=settings.SERVICE_VERSION,
    contact={"name": "Chesspear"},
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "apikey"],
)


@app.get("/", tags=["system"])
def root() -> dict:
    return {"service": settings.SERVICE_NAME, "version": settings.SERVICE_VERSION, "docs": "/docs"}


@app.get("/health", tags=["system"])
def health() -> dict:
    """Liveness check; intentionally does not spawn an engine or require Redis."""
    return {"status": "ok", "service": settings.SERVICE_NAME, "version": settings.SERVICE_VERSION}


@app.get("/ready", tags=["system"])
def ready() -> dict:
    """Perform and cache one Stockfish UCI handshake per API process."""
    global _ready_engine_info
    if _ready_engine_info is None:
        with _ready_lock:
            if _ready_engine_info is None:
                try:
                    with open_engine() as engine:
                        _ready_engine_info = {"name": engine.id.get("name", "Stockfish")}
                except EngineUnavailable as exc:
                    raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {
        "status": "ready",
        "engine": _ready_engine_info["name"],
        "engine_handshake": "verified",
        "queue_url_configured": bool(settings.REDIS_URL),
    }


@app.get(f"{settings.API_PREFIX}/queue/health", tags=["system"])
def queue_health(user: CurrentUser = Depends(require_user)) -> dict:
    """Check queue health for an authenticated caller without exposing load publicly."""
    del user
    connection = None
    try:
        connection = redis_connection()
        connection.ping()
        queue = analysis_queue(connection)
        count = len(queue)
        return {"status": "ok", "queue": settings.REDIS_QUEUE_NAME, "queued_jobs": count}
    except RedisError as exc:
        logger.warning("Redis queue health check failed: %s", exc)
        raise HTTPException(status_code=503, detail="The analysis queue is unavailable.") from exc
    finally:
        if connection is not None:
            connection.close()


@app.post(f"{settings.API_PREFIX}/analyze/position", tags=["analysis"])
def analyze_position_endpoint(
    request: PositionAnalysisRequest,
    user: CurrentUser = Depends(require_user),
) -> dict:
    del user  # Token validation is the access-control boundary for this endpoint.
    try:
        return analyze_position(
            request.fen,
            depth=request.depth,
            time_limit=request.time_limit,
            multipv=request.multipv,
        )
    except InvalidPosition as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except EngineUnavailable as exc:
        message = str(exc)
        status_code = 429 if "slots are busy" in message.lower() else 503
        raise HTTPException(status_code=status_code, detail=message) from exc
    except (chess.engine.EngineError, chess.engine.EngineTerminatedError) as exc:
        logger.exception("Unhandled Stockfish failure")
        raise HTTPException(status_code=503, detail="Stockfish analysis failed.") from exc


@app.post(f"{settings.API_PREFIX}/analyze/game", status_code=status.HTTP_202_ACCEPTED, tags=["analysis"])
def submit_game_analysis(
    request: GameAnalysisRequest,
    user: CurrentUser = Depends(require_user),
) -> dict:
    try:
        # Fail fast on malformed PGN before placing a job in the queue. Deep evaluation
        # is done by the worker; this first pass only checks the game's basic structure.
        import io
        import chess.pgn

        stream = io.StringIO(request.pgn)
        game = chess.pgn.read_game(stream)
        if game is None:
            raise InvalidPosition("No PGN game was found in the request.")
        if game.errors:
            raise InvalidPosition("PGN contains parsing errors; correct the PGN and retry.")
        if game.headers.get("Variant", "Standard") not in {"Standard", "Chess"}:
            raise InvalidPosition("Only standard-chess PGNs are supported in this version.")
        start_board = game.board()
        if not isinstance(start_board, chess.Board) or not start_board.is_valid():
            raise InvalidPosition("The PGN starting position is not a valid standard-chess position.")
        if chess.pgn.read_game(stream) is not None:
            raise InvalidPosition("Submit one PGN game per request.")
        plies = sum(1 for _ in game.mainline_moves())
        if plies == 0:
            raise InvalidPosition("The PGN does not contain any moves.")
        if plies > request.max_plies:
            raise InvalidPosition(f"This game has {plies} plies; max_plies is {request.max_plies}.")
    except InvalidPosition as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (ValueError, IndexError) as exc:
        logger.info("Rejected malformed PGN request: %s", exc)
        raise HTTPException(status_code=422, detail="PGN could not be parsed as one standard-chess game.") from exc

    connection = None
    try:
        connection = redis_connection()
        connection.ping()
        queue: Queue = analysis_queue(connection)
        job = queue.enqueue_call(
            func="app.tasks.analyze_pgn_job",
            args=(request.pgn, user.id),
            kwargs={
                "depth": request.depth,
                "time_limit": request.time_limit,
                "max_plies": request.max_plies,
            },
            timeout=settings.JOB_TIMEOUT_SECONDS,
            result_ttl=settings.JOB_RESULT_TTL_SECONDS,
            failure_ttl=settings.JOB_RESULT_TTL_SECONDS,
        )
        return {
            "job_id": job.id,
            "status": "queued",
            "status_url": f"{settings.API_PREFIX}/jobs/{job.id}",
            "message": "Analysis queued. Poll status_url for progress and the final result.",
        }
    except RedisError as exc:
        logger.warning("Unable to enqueue game analysis: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="The analysis queue is unavailable. Check REDIS_URL and the worker deployment.",
        ) from exc
    except (OSError, ValueError) as exc:
        logger.exception("Unable to create analysis job")
        raise HTTPException(status_code=503, detail="Could not create the analysis job.") from exc
    finally:
        if connection is not None:
            connection.close()


@app.get(f"{settings.API_PREFIX}/jobs/{{job_id}}", tags=["analysis"])
def get_analysis_job(
    job_id: str = Path(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$"),
    user: CurrentUser = Depends(require_user),
) -> dict:
    connection = None
    try:
        connection = redis_connection()
        job = Job.fetch(job_id, connection=connection)

        # The PGN and owner ID are stored in the private Redis job record. Do not reveal a
        # job's status, input, or output to other authenticated users.
        args = job.args or ()
        owner_id = str(args[1]) if len(args) >= 2 else ""
        if owner_id != user.id:
            raise HTTPException(status_code=404, detail="Analysis job not found.")

        # Keep the Redis connection open until status/result reads are complete. Closing it
        # immediately after Job.fetch can break later refresh/result reads on some clients.
        raw_status = job.get_status(refresh=True)
        if raw_status is None:
            raise HTTPException(status_code=404, detail="Analysis job not found or its result expired.")
        job_status = raw_status.value if hasattr(raw_status, "value") else str(raw_status)
        result: dict = {
            "job_id": job.id,
            "status": job_status,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "ended_at": job.ended_at.isoformat() if job.ended_at else None,
        }
        if job_status == "finished":
            result["result"] = job.result
        elif job_status == "failed":
            result["error"] = "Analysis failed. Check the worker logs; sensitive traceback details are not exposed by the API."
        elif job_status in {"queued", "started", "deferred", "scheduled"}:
            result["message"] = "Analysis is still processing. Poll again shortly."
        return result
    except (NoSuchJobError, InvalidJobOperation) as exc:
        raise HTTPException(status_code=404, detail="Analysis job not found or its result expired.") from exc
    except RedisError as exc:
        raise HTTPException(status_code=503, detail="The analysis queue is unavailable.") from exc
    finally:
        if connection is not None:
            connection.close()
