#!/usr/bin/env bash
# Tars each of the three docker-compose.yml data volumes (postgres_data,
# chroma_data, neo4j_data) so they can be copied to another machine and
# restored with restore-volumes.sh -- see detailed_plan.md 13절.
set -euo pipefail

cd "$(dirname "$0")/.."
PROJECT=$(basename "$PWD" | tr '[:upper:]' '[:lower:]')
OUT_DIR="volumes/backup"
mkdir -p "$OUT_DIR"

for name in postgres_data chroma_data neo4j_data; do
  volume="${PROJECT}_${name}"
  echo "backing up $volume -> $OUT_DIR/$name.tar.gz"
  MSYS_NO_PATHCONV=1 docker run --rm \
    -v "${volume}:/data:ro" \
    -v "$(pwd)/${OUT_DIR}:/backup" \
    alpine \
    tar czf "/backup/${name}.tar.gz" -C /data .
done

echo "done. copy $OUT_DIR/*.tar.gz to the other machine and run scripts/restore-volumes.sh there."
