#!/usr/bin/env bash
# Restores the three docker-compose.yml data volumes from volumes/backup/*.tar.gz
# (produced by backup-volumes.sh on the source machine). Run this BEFORE the
# first `docker compose up -d` on the new machine -- see detailed_plan.md 13절.
set -euo pipefail

cd "$(dirname "$0")/.."
PROJECT=$(basename "$PWD" | tr '[:upper:]' '[:lower:]')
IN_DIR="volumes/backup"

for name in postgres_data chroma_data neo4j_data; do
  archive="${IN_DIR}/${name}.tar.gz"
  volume="${PROJECT}_${name}"
  if [ ! -f "$archive" ]; then
    echo "skipping $volume: $archive not found"
    continue
  fi
  echo "restoring $archive -> $volume"
  docker volume create "$volume" >/dev/null
  MSYS_NO_PATHCONV=1 docker run --rm \
    -v "${volume}:/data" \
    -v "$(pwd)/${IN_DIR}:/backup" \
    alpine \
    sh -c "rm -rf /data/* && tar xzf /backup/${name}.tar.gz -C /data"
done

echo "done. now run: docker compose up -d"
