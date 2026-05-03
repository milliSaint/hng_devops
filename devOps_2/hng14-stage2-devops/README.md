# HNG Stage 2 — Job Processing Microservices

A containerised job processing system with three services: a Node.js frontend, a Python/FastAPI backend, and a Python worker — all connected via Redis.

## Prerequisites

- Docker 20.10+
- Docker Compose v2.0+
- Git

## Services

| Service | Port | Description |
|---|---|---|
| frontend | 3000 | Job submission dashboard |
| api | 8000 (internal) | FastAPI job management |
| worker | — | Background job processor |
| redis | 6379 (internal) | Job queue |

## Run Locally (from scratch)

### 1. Clone the repo

```bash
git clone https://github.com/unicornoceanldadev/hng14-stage2-devops.git
cd hng14-stage2-devops
```

### 2. Create your `.env` file

```bash
cp .env.example .env
```

Edit `.env` and set a Redis password:

```
REDIS_PASSWORD=yourpassword
FRONTEND_PORT=3000
```

### 3. Build and start the stack

```bash
docker compose up --build
```

### 4. Verify it's running

```bash
# Submit a job
curl -X POST http://localhost:3000/submit

# Check job status (replace <job_id> with the returned ID)
curl http://localhost:3000/status/<job_id>
```

Expected output after ~3 seconds:

```json
{"job_id": "...", "status": "completed"}
```

### 5. Tear down

```bash
docker compose down -v
```

## What a Successful Startup Looks Like

```
redis-1    | Ready to accept connections tcp
api-1      | INFO:     Application startup complete.
api-1      | INFO:     Uvicorn running on http://0.0.0.0:8000
worker-1   | Processing job ...
frontend-1 | Frontend running on port 3000
```

All four containers show as healthy:

```bash
docker compose ps
# NAME        STATUS
# redis-1     Up (healthy)
# api-1       Up (healthy)
# worker-1    Up (healthy)
# frontend-1  Up (healthy)
```

## API Endpoints

| Method | Path | Description |
|---|---|---|
| GET | /health | Health check — returns `{"status":"ok"}` |
| POST | /jobs | Create a new job |
| GET | /jobs/{job_id} | Get job status |

## CI/CD Pipeline

GitHub Actions pipeline runs on every push in strict order:

```
lint → test → build → security scan → integration test → deploy (main only)
```

- **lint**: flake8 (Python), eslint (JavaScript), hadolint (Dockerfiles)
- **test**: pytest with Redis mocked, coverage report uploaded as artifact
- **build**: all images tagged with git SHA + latest, pushed to local registry
- **security**: Trivy scan, fails on CRITICAL CVEs
- **integration**: full stack spun up, job submitted and polled to completion
- **deploy**: rolling update to server, new container must pass healthcheck within 60s

## Environment Variables

| Variable | Description | Default |
|---|---|---|
| `REDIS_PASSWORD` | Redis auth password | required |
| `REDIS_HOST` | Redis hostname | `redis` |
| `REDIS_PORT` | Redis port | `6379` |
| `API_URL` | API base URL (frontend) | `http://api:8000` |
| `FRONTEND_PORT` | Host port for frontend | `3000` |

## Bugs Fixed

See [FIXES.md](FIXES.md) for a full list of all 11 issues found and fixed in the starter repo.
