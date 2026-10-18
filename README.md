# Chesspear Backend — Stockfish v0.1

A Docker-first Python backend starter for Chesspear. It includes a FastAPI service, Stockfish UCI analysis, PGN review jobs via Redis/RQ, Supabase access-token validation, tests, and Render setup notes.

> **Scope:** this is a runnable first backend milestone, not the complete production system. Maia is intentionally not included. Analysis results are retained in Redis for the configured TTL (default 24 hours), not yet written durably to Supabase. Existing `profiles` and `saved_games` tables are not modified. Full natural-language coaching and fork/pin/sacrifice motif detection are not implemented yet.

## Architecture

- **FastAPI web service:** health checks, authenticated position analysis, PGN job submission, job-status/result polling.
- **Stockfish:** installed from the Debian Trixie package repository in the Docker image. The exact engine build is determined at image-build time and can change as repositories update; pin the package/base image if reproducible engine versions are required.
- **python-chess:** FEN/PGN handling, legal moves, SAN/UCI conversion, and UCI engine integration.
- **Redis + RQ worker:** queues whole-game review jobs so the API request does not wait for the full review. Results are cached in Redis for 24 hours by default.
- **Supabase Auth:** API validates the supplied access token by asking the Supabase Auth `/auth/v1/user` endpoint. The backend does not require a service-role key.

## Features included

- `GET /health` liveness check.
- `GET /ready` performs one cached Stockfish UCI handshake per API process, rather than spawning an engine on every public probe.
- `GET /api/v1/queue/health` checks Redis (requires authentication when `AUTH_REQUIRED=true`).
- `POST /api/v1/analyze/position` returns an evaluation and up to three principal variations.
- `POST /api/v1/analyze/game` validates a single PGN and queues move-by-move analysis.
- `GET /api/v1/jobs/{job_id}` reports queued/running/finished/failed status and returns the result only to the user who submitted it.
- Initial move classifications: best, excellent, good, inaccuracy, mistake, blunder.
- Basic tags: capture, en passant, castling, promotion, check, checkmate.
- Input validation, bounded depth/time/multipv/game length, bounded engine concurrency, CORS allowlist, and generic public error messages.

### Accuracy limitations

Move labels use a documented, transparent heuristic based on estimated centipawn loss from the mover's point of view. It is **not** intended to reproduce the proprietary or evolving labels used by Chess.com, Chessigma, or other services. These thresholds must be calibrated against a fixed regression set before a public launch. Tactical motif detection, opening classification, accuracy percentages, and natural-language coach explanations are not included yet.

## Requirements

- Docker Desktop (recommended for local development) or Docker Engine + Compose.
- A Supabase project (already created in Chesspear's setup).
- GitHub and a Render account for deployment.

## Run locally

1. Copy `.env.example` to `.env`.
2. Keep `AUTH_REQUIRED=false` **only on your own local machine** for initial engine testing. The code's secure default is `AUTH_REQUIRED=true`; the example file explicitly documents its local-only override.
3. Start the app:

   ```bash
   docker compose up --build
   ```

4. Visit:

   - API docs: http://localhost:10000/docs
   - Liveness: http://localhost:10000/health
   - Stockfish readiness: http://localhost:10000/ready
   - Queue health: http://localhost:10000/api/v1/queue/health

5. Run tests:

   ```bash
   docker compose run --rm --no-deps api python -m pytest -q
   ```

If you do not use Compose, install the dependencies from `requirements.txt`, install a compatible Stockfish binary, set `STOCKFISH_PATH`, run Redis, and launch the API and worker separately. In this non-Compose setup, change `REDIS_URL` in `.env` to `redis://localhost:6379/0` (the example's `redis://redis:6379/0` address is the Docker Compose service hostname):

```bash
uvicorn app.main:app --host 127.0.0.1 --port 10000
python -m app.worker
```

## Example requests

These examples assume local `.env` has `AUTH_REQUIRED=false`. For a deployed environment, use a valid Supabase access token in the `Authorization` header.

### Analyze a position

```bash
curl -X POST http://localhost:10000/api/v1/analyze/position \
  -H 'Content-Type: application/json' \
  -d '{"fen":"rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1","depth":12,"time_limit":0.25,"multipv":2}'
```

### Queue a PGN review

```bash
curl -X POST http://localhost:10000/api/v1/analyze/game \
  -H 'Content-Type: application/json' \
  -d '{"pgn":"[Event \"Casual\"]\n[White \"Alice\"]\n[Black \"Bob\"]\n[Result \"1-0\"]\n\n1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 1-0","depth":12,"time_limit":0.2,"max_plies":100}'
```

The submission returns `job_id`. Poll the returned `status_url` until `status` is `finished` or `failed`. Job statuses/results expire from Redis after the configured TTL.

## Supabase Auth configuration

On Render set:

- `AUTH_REQUIRED=true`
- `SUPABASE_URL=https://YOUR_PROJECT_REF.supabase.co`
- `SUPABASE_PUBLISHABLE_KEY=YOUR_PUBLIC_PUBLISHABLE_OR_ANON_KEY`

`SUPABASE_PUBLISHABLE_KEY` may contain the project's publishable key or legacy anon/public key. Do not use the database password or service-role key. The frontend will pass the current Supabase session access token using `Authorization: Bearer <access_token>`.

The API asks Supabase Auth to validate the token for protected calls. This avoids local JWT verification-key configuration for different Supabase signing algorithms, at the expense of an Auth network request per protected API request.

## Render deployment

The whole-game queue requires **three services**: a web service, a background worker, and Redis-compatible Render Key Value. These service types may incur charges depending on the plans currently available to your account. Do not create paid services until you have reviewed the displayed price. A free web service alone can run the position endpoint but does not provide the durable/distributed queue architecture required by the whole-game endpoint.

### 1. Push this folder to GitHub

Create a private repository called `chesspear-backend`, upload/push the contents of this folder, and confirm `Dockerfile` is at the repository root.

### 2. Create Render Key Value

In Render, create a Redis-compatible **Key Value** instance. Copy its **internal/private connection string** and configure `REDIS_URL` on both the web service and worker. Prefer a no-eviction policy where available and provide sufficient memory for queued PGNs/results.

### 3. Create the web service

- New → Web Service → connect the repository.
- Runtime: Docker.
- Dockerfile path: `./Dockerfile`.
- Health check path: `/health`.
- Set `AUTH_REQUIRED=true`.
- Set `SUPABASE_URL` and `SUPABASE_PUBLISHABLE_KEY`.
- Set `REDIS_URL` to the internal Key Value connection string.
- Set `ALLOWED_ORIGINS` to exact Lovable preview/production origins when the frontend exists (comma-separated). Until then the localhost defaults are only for development.
- Optionally tune `STOCKFISH_THREADS`, `STOCKFISH_HASH_MB`, `MAX_ENGINE_CONCURRENCY`, `JOB_TIMEOUT_SECONDS` and `JOB_RESULT_TTL_SECONDS` to the instance resources.

### 4. Create the background worker

Create a second Render service from the same repository, choose **Background Worker**, use Docker, and set the start command to:

```bash
python -m app.worker
```

Set the same `REDIS_URL`, `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, and Stockfish configuration environment variables. The worker does not need to expose a public URL.

### 5. Smoke test

After deploy, check `https://YOUR-API.onrender.com/health` and `/ready`. `/ready` should report a Stockfish engine name after its cached UCI handshake. Check `/api/v1/queue/health` with a valid Supabase access token; it should report `status: ok`. Then submit a test position with a valid Supabase access token. The complete PGN path can be tested from `/docs` with the same token, then poll the job URL.

The web service and worker each have a separate process; local Python semaphores do not coordinate across different Render instances. Keep `STOCKFISH_THREADS=1` initially and scale only after benchmarking CPU/memory and simultaneous jobs.

## Environment reference

| Variable | Purpose |
|---|---|
| `AUTH_REQUIRED` | Must be `true` in deployed environments. |
| `SUPABASE_URL` | Supabase project URL. |
| `SUPABASE_PUBLISHABLE_KEY` | Public publishable/anon key used for Auth API calls. |
| `STOCKFISH_PATH` | Stockfish executable path inside the container. |
| `STOCKFISH_THREADS` | Threads per engine instance. Start at 1 on a small CPU instance. |
| `STOCKFISH_HASH_MB` | Hash memory per engine instance. |
| `MAX_ENGINE_CONCURRENCY` | Maximum simultaneous synchronous position searches per API process. |
| `REDIS_URL` | Redis/Render Key Value connection string for queued game reviews. |
| `REDIS_QUEUE_NAME` | RQ queue name. |
| `JOB_RESULT_TTL_SECONDS` | Result/failure retention in Redis (default one day). |
| `JOB_TIMEOUT_SECONDS` | Maximum RQ job runtime. |
| `ALLOWED_ORIGINS` | Comma-separated exact browser origins allowed by CORS. |

## API details

### POST `/api/v1/analyze/position`

Request fields:

```json
{
  "fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
  "depth": 12,
  "time_limit": 0.25,
  "multipv": 2
}
```

Bounds: depth 4–20, time limit above 0 and at most 3 seconds, MultiPV 1–3. Both depth and time limits are passed to Stockfish; which limit ends the search depends on search progress and hardware. Output evaluations are reported from White's perspective and the side-to-move's perspective. Mate is represented separately from ordinary centipawns.

### POST `/api/v1/analyze/game`

Request fields: `pgn`, `depth` (4–18), `time_limit` (up to 1.5 seconds per position), and `max_plies` (1–160). Exactly one standard-chess PGN per request is supported. The API queues the job and returns HTTP 202 with a `job_id` and `status_url`.

### GET `/api/v1/jobs/{job_id}`

Returns `queued`, `started`, `finished`, or `failed` status. A finished response contains the analysis result. Only the submitting user can access that job's status/result. Results expire according to `JOB_RESULT_TTL_SECONDS`.

## Next engineering milestones

1. Build a fixed suite of known FENs and annotated PGNs; compare the API's scores/PVs to direct UCI output and verify mate/score perspective.
2. Add classification regression tests and calibrated settings rather than presenting heuristic labels as ground truth.
3. Persist analysis jobs/results durably in Supabase/Postgres instead of Redis-only TTL storage.
4. Add rate limiting and per-user quotas at the API or gateway layer.
5. Add tactical-motif detection (fork, pin, discovered attack, sacrifice, missed win) and a separate explanation layer.
6. Benchmark and add Maia only if human-move prediction improves coaching.
7. Integrate the Lovable frontend after the backend contract is stable.

## Security checklist before launch

- Set `AUTH_REQUIRED=true`.
- Replace local CORS origins with exact preview/production origins.
- Keep `.env` out of Git; never commit secrets.
- Never expose a service-role key or database password in frontend code.
- Configure Render networking so Redis is private and available only to your services.
- Add rate limits, durable persistence, monitoring, backups and an abuse/cost policy before public traffic.
- Review Stockfish GPL-3.0 obligations before distributing a built image or product.
