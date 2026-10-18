"""Run with: python -m app.worker"""
import logging

from rq import Worker

from app.queueing import analysis_queue, redis_connection
from app import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def main() -> None:
    connection = redis_connection()
    connection.ping()
    queue = analysis_queue(connection)
    logging.getLogger(__name__).info(
        "Starting worker for queue '%s' (Stockfish path: %s)",
        settings.REDIS_QUEUE_NAME,
        settings.STOCKFISH_PATH,
    )
    Worker([queue], connection=connection).work(with_scheduler=False)


if __name__ == "__main__":
    main()
