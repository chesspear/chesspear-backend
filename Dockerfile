FROM python:3.12-slim-trixie

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    STOCKFISH_PATH=/usr/local/bin/stockfish

WORKDIR /app

# Stockfish is installed from Debian Trixie repositories; the exact package build can change.
# See THIRD_PARTY_LICENSES.md before distributing this image.
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends stockfish ca-certificates; \
    STOCKFISH_BIN="$(command -v stockfish || find /usr/games /usr/bin -type f -name stockfish -perm -111 -print -quit)"; \
    test -n "$STOCKFISH_BIN"; \
    ln -sf "$STOCKFISH_BIN" /usr/local/bin/stockfish; \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY tests ./tests
COPY licenses ./licenses
COPY README.md THIRD_PARTY_LICENSES.md ./

EXPOSE 10000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-10000} --workers ${WEB_CONCURRENCY:-1}"]
