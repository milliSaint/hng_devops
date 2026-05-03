# FIXES.md — Bug Report

Every issue found in the starter repository, with file, line, problem, and fix.

---

## Fix 1 — Committed secrets in version control

**File:** `api/.env`
**Line:** 1–2
**Problem:** The `.env` file containing `REDIS_PASSWORD=supersecretpassword123` was committed to git. Any credential in version control is permanently exposed even after deletion.
**Fix:** Ran `git rm --cached api/.env` to untrack the file. Added `.env` to `.gitignore` to prevent future commits.

---

## Fix 2 — Hardcoded Redis host in API

**File:** `api/main.py`
**Line:** 8
**Problem:** `redis.Redis(host="localhost", port=6379)` — hardcoded `localhost` works on a single machine but breaks in containers where Redis runs as a separate service with its own hostname.
**Fix:** Replaced with `os.environ.get("REDIS_HOST", "redis")` and `os.environ.get("REDIS_PORT", 6379)` so the host is configurable via environment variables.

---

## Fix 3 — Redis password defined but never used in API

**File:** `api/main.py`
**Line:** 8
**Problem:** The `.env` file defined `REDIS_PASSWORD` but the Redis client was initialised without a password parameter, so the password was silently ignored and Redis ran unauthenticated.
**Fix:** Added `REDIS_PASSWORD = os.environ.get("REDIS_PASSWORD", None)` and passed it to `redis.Redis(password=REDIS_PASSWORD)`.

---

## Fix 4 — 404 returned as 200 in API

**File:** `api/main.py`
**Line:** 20–21
**Problem:** `return {"error": "not found"}` returns HTTP 200 with an error body. Clients and health checks cannot distinguish success from failure.
**Fix:** Replaced with `raise HTTPException(status_code=404, detail="not found")` which correctly returns HTTP 404.

---

## Fix 5 — Missing /health endpoint in API

**File:** `api/main.py`
**Problem:** No health check endpoint existed. Docker HEALTHCHECK and `depends_on: condition: service_healthy` require an endpoint to probe.
**Fix:** Added `GET /health` returning `{"status": "ok"}` with HTTP 200.

---

## Fix 6 — Hardcoded Redis host in worker

**File:** `worker/worker.py`
**Line:** 6
**Problem:** `redis.Redis(host="localhost", port=6379)` — same localhost hardcoding as the API. Fails in containers.
**Fix:** Replaced with environment variables `REDIS_HOST`, `REDIS_PORT`, and `REDIS_PASSWORD`.

---

## Fix 7 — Redis password never used in worker

**File:** `worker/worker.py`
**Line:** 6
**Problem:** Redis client initialised without password, so authenticated Redis connections would be rejected.
**Fix:** Added `REDIS_PASSWORD = os.environ.get("REDIS_PASSWORD", None)` and passed it to `redis.Redis(password=REDIS_PASSWORD)`.

---

## Fix 8 — Unused imports in worker

**File:** `worker/worker.py`
**Line:** 4
**Problem:** `import signal` was present but never used, causing a flake8 `F401` error that would fail the lint stage.
**Fix:** Removed the unused `signal` import.

---

## Fix 9 — Hardcoded API URL in frontend

**File:** `frontend/app.js`
**Line:** 6
**Problem:** `const API_URL = "http://localhost:8000"` — hardcoded localhost breaks containers where the API runs as a separate service named `api`.
**Fix:** Replaced with `const API_URL = process.env.API_URL || "http://api:8000"` so the URL is configurable via environment variable.

---

## Fix 10 — Unpinned Python dependencies

**File:** `api/requirements.txt`, `worker/requirements.txt`
**Line:** All lines
**Problem:** `fastapi`, `uvicorn`, `redis` were listed without version pins. This produces non-reproducible builds — the same Dockerfile can install different versions on different days.
**Fix:** Pinned all versions: `fastapi==0.111.0`, `uvicorn==0.29.0`, `redis==5.0.4`, `httpx==0.27.0`.

---

## Fix 11 — No Dockerfiles or docker-compose

**File:** N/A (missing files)
**Problem:** No `Dockerfile` existed for any service and no `docker-compose.yml` was present, making the application impossible to containerise or run as a multi-service stack.
**Fix:** Created `Dockerfile` for `api`, `worker`, and `frontend` with multi-stage builds, non-root users, and HEALTHCHECK instructions. Created `docker-compose.yml` with named internal network, health-condition dependencies, environment variable configuration, and CPU/memory limits.
