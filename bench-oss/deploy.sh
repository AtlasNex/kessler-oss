#!/usr/bin/env bash
# bench-oss deploy — derive the lab model endpoint from the honeypot env (never printed),
# write the compose .env, bring the OSS agent builds up. Idempotent.
set -euo pipefail
cd /opt/bench-oss

set -a
# shellcheck disable=SC1091
source /opt/g2-honeypot/.env
set +a

# the honeypot .env is CRLF (session-28 lesson): strip carriage returns BEFORE deriving
# anything, or the suffix strip below silently fails and the key rides a trailing \r
HONEY_MODEL_URL="$(printf '%s' "$HONEY_MODEL_URL" | tr -d '\r')"
HONEY_MODEL_KEY="$(printf '%s' "$HONEY_MODEL_KEY" | tr -d '\r')"
HONEY_MODEL_NAME="$(printf '%s' "${HONEY_MODEL_NAME:-}" | tr -d '\r')"

if [ -z "${HONEY_MODEL_URL:-}" ] || [ -z "${HONEY_MODEL_KEY:-}" ]; then
  echo "REFUSED: honeypot model env is empty; wire /opt/g2-honeypot/.env first" >&2
  exit 2
fi

LAB_BASE_URL="${HONEY_MODEL_URL%/chat/completions}"
if [ "$LAB_BASE_URL" = "$HONEY_MODEL_URL" ]; then
  echo "NOTE: HONEY_MODEL_URL did not end in /chat/completions; using it verbatim as base" >&2
fi

umask 077
# mktemp+mv, NOT '{ ... } > .env': the redirect truncates .env BEFORE the in-block grep
# runs, so both key-preservation guards always fell through and re-minted fresh keys on
# every deploy (found the hard way, session 29 — it broke the BENCH-OSS-03 probe).
tmp=".env.tmp.$$"
{
  echo "LAB_BASE_URL=${LAB_BASE_URL}"
  echo "LAB_API_KEY=${HONEY_MODEL_KEY}"
  echo "LAB_MODEL=${HONEY_MODEL_NAME:-qwen}"
  if [ -f .env ] && grep -q '^WEBUI_SECRET_KEY=' .env; then
    grep '^WEBUI_SECRET_KEY=' .env
  else
    echo "WEBUI_SECRET_KEY=$(openssl rand -hex 32)"
  fi
  if [ -f .env ] && grep -q '^LITELLM_KEY=' .env; then
    grep '^LITELLM_KEY=' .env
  else
    echo "LITELLM_KEY=sk-kessler-$(openssl rand -hex 24)"
  fi
  if [ -f .env ] && grep -q '^OLLAMA_KEY=' .env; then
    grep '^OLLAMA_KEY=' .env
  else
    echo "OLLAMA_KEY=sk-kessler-$(openssl rand -hex 24)"
  fi
} > "$tmp"
mv -f "$tmp" .env
chmod 600 .env

docker compose up -d

# BENCH-OSS-04: ensure the bench model exists (idempotent; ~4.7GB download on first boot only)
docker compose exec -T ollama ollama list 2>/dev/null | grep -q 'qwen2.5:7b-instruct' || \
  docker compose exec -T ollama ollama pull qwen2.5:7b-instruct

docker compose ps --format '{{.Name}} {{.Status}}'
