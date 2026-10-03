#!/usr/bin/env bash
# Re-mint the Open WebUI instance API key for bench-oss (BENCH-OSS-01).
# Runs ON THE HOST. Values are never printed.
#
# Why this exists: bench-oss deploy.sh used to truncate .env before its preserve-greps
# ran (fixed session 29), so past deploys silently rotated WEBUI_SECRET_KEY. A minted
# session JWT then 401s on the measured endpoint anyway: /api/chat/completions
# authenticates via get_current_user_by_api_key (a row in the api_key table, resolved
# by Users.get_user_by_api_key) — independent of WEBUI_SECRET_KEY, so this path
# survives future secret rotations. Key format mirrors the app's create_api_key():
# "sk-" + uuid4 hex.
#
# Authorization: our own deployed instance on our own host (ownership, PLAN-v5 #22).
set -euo pipefail

# docker exec without -i drops stdin and nested quoting through ssh is the known trap —
# the python source travels base64-encoded as a single argv.
PY=$(cat <<'PYEOF'
import sqlite3, uuid, time
from open_webui.utils.auth import create_api_key
key = create_api_key()
db = sqlite3.connect("/app/backend/data/webui.db")
uid = db.execute('select id from "user" where role=\'admin\' limit 1').fetchone()[0]
now = int(time.time())
db.execute("delete from api_key")
db.execute(
    "insert into api_key (id, user_id, key, data, expires_at, last_used_at, created_at, updated_at)"
    " values (?,?,?,?,?,?,?,?)",
    (str(uuid.uuid4()), uid, key, "bench-oss", None, None, now, now))
# config table is (key, value, updated_at); values are RAW scalars ('true'/'false'), not JSON
if db.execute("select 1 from config where key='auth.enable_api_keys'").fetchone():
    db.execute("update config set value='true', updated_at=? where key='auth.enable_api_keys'", (now,))
else:
    db.execute("insert into config (key, value, updated_at) values ('auth.enable_api_keys', 'true', ?)", (now,))
db.commit()
print(key)
PYEOF
)
B64=$(printf '%s' "$PY" | base64 -w0)
KEY=$(docker exec bench-openwebui python3 -c "import base64;exec(base64.b64decode('$B64').decode())")

case "$KEY" in
  sk-*) ;;
  *) echo "mint failed (no sk- prefix)" >&2; exit 1 ;;
esac

tmp=$(mktemp)
grep -v "^OPENWEBUI_KEY=" /opt/bench-oss/keys.env > "$tmp" || true
echo "OPENWEBUI_KEY=$KEY" >> "$tmp"
install -m 600 "$tmp" /opt/bench-oss/keys.env
shred -u "$tmp"
echo "OPENWEBUI_KEY re-minted via api_key table (value never printed)."

# restart so the config cache picks up enable_api_keys, then smoke the measured endpoint
docker restart bench-openwebui >/dev/null
set -a; source /opt/bench-oss/keys.env; set +a
code=000
for i in $(seq 1 12); do
  sleep 5
  # mid-boot the peer can drop the socket (curl 56) — set -e must not kill the retry loop
  code=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
    http://127.0.0.1:8101/api/chat/completions \
    -H "Authorization: Bearer $OPENWEBUI_KEY" -H "Content-Type: application/json" \
    -d '{"model":"qwen3.8-flash","messages":[{"role":"user","content":"ping"}]}') || code=000
  [ "$code" = "200" ] && break
done
echo "smoke POST -> HTTP $code"
[ "$code" = "200" ] || exit 1
