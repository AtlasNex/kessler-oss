#!/usr/bin/env bash
# drill-topology deploy — same env-derivation pattern as bench-oss (values never printed).
set -euo pipefail
cd /opt/kessler-drill

set -a
# shellcheck disable=SC1091
source /opt/g2-honeypot/.env
set +a

if [ -z "${HONEY_MODEL_URL:-}" ] || [ -z "${HONEY_MODEL_KEY:-}" ]; then
  echo "REFUSED: honeypot model env is empty" >&2
  exit 2
fi

umask 077
{
  echo "LAB_BASE_URL=${HONEY_MODEL_URL%/chat/completions}"
  echo "LAB_API_KEY=${HONEY_MODEL_KEY}"
  echo "LAB_MODEL=${HONEY_MODEL_NAME:-qwen}"
} > .env
chmod 600 .env

docker compose up -d --build
docker compose ps --format '{{.Name}} {{.Status}}'
