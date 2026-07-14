#!/usr/bin/env bash
# Stops what scripts/dev-up.sh started: backend/frontend dev processes and the
# docker infra containers (volumes are left intact -- see BACKUP_RESTORE.md).
set -uo pipefail

cd "$(dirname "$0")/.."

for name in backend frontend; do
  pidfile="logs/${name}.pid"
  [ -f "$pidfile" ] || continue
  pid=$(cat "$pidfile")
  if kill -0 "$pid" 2>/dev/null; then
    echo "stopping $name (pid $pid)"
    # uvicorn --reload / vite spawn child processes; kill the tree on Windows.
    taskkill //F //T //PID "$pid" >/dev/null 2>&1 || kill "$pid" 2>/dev/null
  fi
  rm -f "$pidfile"
done

echo "== docker compose stop =="
docker compose stop

echo "done."
