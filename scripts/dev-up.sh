#!/usr/bin/env bash
# One command to get a fully running local stack for manual testing:
# docker infra (postgres/chroma/neo4j) + backend (uvicorn) + frontend (vite).
# Safe to re-run -- skips steps that are already done/running.
set -euo pipefail

cd "$(dirname "$0")/.."
PROJECT=$(basename "$PWD" | tr '[:upper:]' '[:lower:]')
mkdir -p logs

if ! docker info >/dev/null 2>&1; then
  echo "Docker daemon not reachable -- start Docker Desktop first, then re-run this script." >&2
  exit 1
fi

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example -- fill in OPENAI_API_KEY/BIZINFO_API_KEY if you need those features."
fi

echo "== docker compose up -d =="
docker compose up -d

echo "== waiting for postgres healthcheck =="
until [ "$(docker inspect -f '{{.State.Health.Status}}' "${PROJECT}-postgres-1" 2>/dev/null)" = "healthy" ]; do
  sleep 1
done

echo "== backend =="
if curl -s -o /dev/null http://127.0.0.1:8000/health; then
  echo "backend already running on :8000, skipping"
else
  (
    cd backend
    if [ ! -d venv ]; then
      python -m venv venv
      venv/Scripts/pip install -r requirements.txt
    fi
    source venv/Scripts/activate
    nohup uvicorn app.main:app --reload > ../logs/backend.log 2>&1 &
    echo $! > ../logs/backend.pid
  )
  echo "backend starting (logs/backend.log)"
fi

echo "== frontend =="
if curl -s -o /dev/null http://localhost:5173; then
  echo "frontend already running on :5173, skipping"
else
  (
    cd frontend
    [ -d node_modules ] || npm install
    nohup npm run dev > ../logs/frontend.log 2>&1 &
    echo $! > ../logs/frontend.pid
  )
  echo "frontend starting (logs/frontend.log)"
fi

echo "== waiting for backend/frontend to answer (up to 30s) =="
be=000
fe=000
for _ in $(seq 1 30); do
  sleep 1
  be=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/health || true)
  fe=$(curl -s -o /dev/null -w '%{http_code}' http://localhost:5173 || true)
  [ "$be" = "200" ] && [ "$fe" = "200" ] && break
done

echo
echo "backend  http://127.0.0.1:8000/health -> $be   (log: logs/backend.log)"
echo "frontend http://localhost:5173         -> $fe   (log: logs/frontend.log)"
echo "demo login: demo-001@example.com / demo1234 (or demo-002@example.com)"
echo "stop everything with: bash scripts/dev-down.sh"
