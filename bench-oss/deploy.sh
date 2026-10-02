#!/usr/bin/env bash
# bench-oss deploy — derive the lab model endpoint from the honeypot env (never printed),
# write the compose .env, bring the OSS agent builds up. Idempotent.
set -euo pipefail
cd /opt/bench-oss

set -a
# shellcheck disable=SC1091
source /opt/g2-honeypot/.env
set +a

if [ -z "${HONEY_MODEL_URL:-}" ] || [ -z "${HONEY_MODEL_KEY:-}" ]; then
  echo "REFUSED: honeypot model env is empty; wire /opt/g2-honeypot/.env first" >&2
  exit 2
fi

LAB_BASE_URL="${HONEY_MODEL_URL%/chat/completions}"
if [ "$LAB_BASE_URL" = "$HONEY_MODEL_URL" ]; then
  echo "NOTE: HONEY_MODEL_URL did not end in /chat/completions; using it verbatim as base" >&2
fi

umask 077
{
  echo "LAB_BASE_URL=${LAB_BASE_URL}"
  echo "LAB_API_KEY=${HONEY_MODEL_KEY}"
  echo "LAB_MODEL=${HONEY_MODEL_NAME:-qwen}"
  if [ -f .env ] && grep -q '^WEBUI_SECRET_KEY=' .env; then
    grep '^WEBUI_SECRET_KEY=' .env
  else
    echo "WEBUI_SECRET_KEY=$(openssl rand -hex 32)"
  fi
} > .env
chmod 600 .env

docker compose up -d
docker compose ps --format '{{.Name}} {{.Status}}'
