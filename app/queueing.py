"""Redis/RQ queue helpers used by the API and the background worker."""
from __future__ import annotations

from redis import Redis
from rq import Queue

from app import settings


def redis_connection() -> Redis:
    return Redis.from_url(
        settings.REDIS_URL,
        socket_connect_timeout=3,
        socket_timeout=5,
        health_check_interval=30,
    )


def analysis_queue(connection: Redis | None = None) -> Queue:
    conn = connection or redis_connection()
    return Queue(
        settings.REDIS_QUEUE_NAME,
        connection=conn,
        default_timeout=settings.JOB_TIMEOUT_SECONDS,
    )
