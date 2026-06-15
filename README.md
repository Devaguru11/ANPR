# ANPR Dashboard

Philippine traffic / ANPR enforcement platform with a React dashboard, Express API, and two Python analytics assistants.

## Architecture

| Component | Stack | Port |
|-----------|-------|------|
| `client/` | React, Vite, MUI | 5173 |
| `server/` | Node.js, Express, MySQL | 4000 |
| `assistant_ai_service/` | FastAPI, LangGraph, vLLM | 9101 |
| `assistant_enhance_service/` | FastAPI, LangGraph, vLLM | 9103 |
| MySQL (Docker) | mysql:8.0 | 3307 |
| Redis (Docker) | redis:7 | 6380 |

## Quick start (local dev)

### Prerequisites

- Node.js 20+
- Python 3.11+ (3.13 works for API deps; vLLM needs a GPU stack separately)
- Docker Desktop

### 1. One-time setup

```bash
chmod +x scripts/setup-dev.sh scripts/start-dev.sh
./scripts/setup-dev.sh
```

This starts MySQL + Redis, installs npm/Python deps, and seeds a local database with demo ANPR data.

### 2. Start the app

```bash
./scripts/start-dev.sh
```

Open **http://localhost:5173/enterprise/login**

| Field | Value |
|-------|-------|
| Email | `admin@anpr.local` |
| Password | `admin123` |

### 3. Verify

```bash
curl http://127.0.0.1:4000/api/health
# {"ok":true}
```

## What works without extra setup

- Login and JWT auth
- Dashboard, vehicle reports, violations, watchlists
- Challan workflow (demo email mode without SMTP)
- Demo owner/plate lookup from JSON fixtures

## AI assistants (optional)

Chat features need Redis (already in Docker), both Python services, and **vLLM** on port 8000:

```bash
# After vLLM is running with Qwen/Qwen2.5-7B-Instruct-AWQ
START_AI=1 ./scripts/start-dev.sh
```

Health checks:

```bash
curl http://127.0.0.1:9101/health
curl http://127.0.0.1:9103/health
```

## Environment files

| File | Purpose |
|------|---------|
| `server/.env` | API, DB, JWT, AI proxy URLs |
| `client/.env` | Vite API proxy settings |
| `assistant_ai_service/.env` | Stable assistant |
| `assistant_enhance_service/.env` | Analytics assistant |

Copy from each `.env.example` if you need to reset.

## Database

Docker MySQL credentials:

| Setting | Value |
|---------|-------|
| Host | `127.0.0.1:3307` |
| Database | `aiserver` |
| App user | `aiserver` / `anpr_dev` |
| Analytics user | `analytics_ai` / `anpr_dev` |
| Root | `root` / `anpr_root` |

Bootstrap SQL: `server/sql/dev_bootstrap.sql`

Reset database:

```bash
docker compose down -v
docker compose up -d
./scripts/setup-dev.sh
```

## Manual service commands

```bash
# Infrastructure
docker compose up -d

# API
cd server && npm run dev

# Client
cd client && npm run dev

# AI (optional)
cd assistant_ai_service && .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 9101
cd assistant_enhance_service && .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 9103
```

## Site configuration

Regional/timezone settings live in `config/site.config.json` and `config/en.lang.json`.
