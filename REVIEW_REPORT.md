# Chesspear Backend — Second Audit Report

Audit date: 2026-10-17

## Summary

The ZIP was extracted into a clean directory and reviewed again. Python syntax compilation passed, ZIP integrity passed, and five tests that do not require the missing chess dependencies passed. The full test suite and live integration stack could not be run in this environment.

## Additional correction in this pass

- **PGN enqueue validation:** the API now checks the PGN's starting board is a valid standard-chess position before adding a job to Redis. Invalid custom-FEN positions are rejected before consuming worker capacity.
- **Stockfish version documentation:** README and Dockerfile comments no longer imply that the Debian repository package remains fixed at one engine version. The package version can change between image builds; pinning remains necessary if reproducibility is required.

## Checks executed

| Check | Result | Notes |
|---|---|---|
| ZIP archive integrity | PASS | `unzip -t chesspear-backend-reviewed.zip` reported no errors |
| Python AST/syntax | PASS | All 14 Python source/test files parsed; `python -m compileall -q app tests` passed |
| Classification and settings tests | PASS | `pytest -q tests/test_classification.py tests/test_settings.py` — 5 passed |
| Full pytest suite | BLOCKED | Collection fails because `python-chess` (`chess`) is not installed in the environment |
| Dependency installation | BLOCKED | `pip install -r requirements.txt` attempted; PyPI could not be resolved due to environment DNS/network restrictions |
| FastAPI API tests | BLOCKED | Import path requires `python-chess`, Redis and RQ dependencies not available in the current Python environment |
| Stockfish UCI | NOT RUN | No Stockfish executable is installed in the environment |
| Redis/RQ queue integration | NOT RUN | No Redis server or RQ package is available in the environment |
| Docker build / Compose end-to-end | NOT RUN | Docker/Podman is unavailable in the environment |

## Current limitations and risks

- This audit does not prove the Docker image builds or that a live Stockfish/Redis/RQ workflow works. These must be tested in Docker or CI before deployment.
- Move-classification thresholds remain heuristics and are not calibrated against a labeled regression suite.
- Tactical motif detection and natural-language coaching are not implemented.
- Job results are kept in Redis for a limited TTL; durable analysis history is not yet stored in Supabase.
- Rate limiting, per-user quotas, monitoring, and public-traffic cost controls remain to be added before launch.
- Review the Stockfish GPL-3.0 obligations for the exact binary/image distributed.

## Recommended next verification

On a machine or CI runner with Docker and network access, run:

```bash
cp .env.example .env
docker compose up --build -d
python -m pytest -q
curl -fsS http://localhost:10000/health
curl -fsS http://localhost:10000/ready
docker compose logs --tail=100 api worker
```

For a queue test, submit a valid PGN with `AUTH_REQUIRED=false` only in local development, poll the returned `status_url`, and confirm it reaches `finished`. Never use the local auth bypass in a deployed service.
