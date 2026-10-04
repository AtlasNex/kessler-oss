#!/usr/bin/env python3
"""Create the Cloudflare Access gate for /portal/ (A7/B1, s32/K6 wave-2).

Idempotent: an app named 'Kessler Client Portal' is left alone. Prints names/ids only - never
secrets. The app gates ONLY the /portal path on kessler.atlasnex.com; the rest of the site
stays public (verified after creation)."""
import json
import urllib.request
from pathlib import Path

VAULT = Path("C:/Users/sanja/.atlasnex/secrets.json")
cf = json.loads(VAULT.read_text(encoding="utf-8"))["cloudflare"]
TOKEN, ACCOUNT = cf["api_token"], cf["account_id"]
API = "https://api.cloudflare.com/client/v4"
NAME = "Kessler Client Portal"
DOMAIN = "kessler.atlasnex.com/portal"
EMAILS = ["sanjay@atlasnex.com", "Atlasnex@pm.me"]


def api(path: str, body: dict | None = None, method: str | None = None) -> dict:
    req = urllib.request.Request(API + path, method=method or ("POST" if body is not None else "GET"))
    req.add_header("Authorization", "Bearer " + TOKEN)
    if body is not None:
        req.add_header("Content-Type", "application/json")
        req.data = json.dumps(body).encode()
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"success": False, "errors": [{"code": e.code, "message": e.read().decode()[:200]}]}


apps = api(f"/accounts/{ACCOUNT}/access/apps")
if not apps.get("success"):
    raise SystemExit(f"apps list failed: {apps.get('errors')}")
existing = [a for a in apps["result"] if a["name"] == NAME]
if existing:
    app = existing[0]
    print(f"app exists: {app['id']} domain={app['domain']}")
else:
    created = api(f"/accounts/{ACCOUNT}/access/apps", {
        "name": NAME, "domain": DOMAIN, "type": "self_hosted", "session_duration": "24h"})
    if not created.get("success"):
        raise SystemExit(f"app create failed: {created.get('errors')}")
    app = created["result"]
    print(f"app created: {app['id']} domain={app['domain']}")

policies = api(f"/accounts/{ACCOUNT}/access/apps/{app['id']}/policies")
have = policies.get("result", []) if policies.get("success") else []
if not any(p.get("name") == "portal members" for p in have):
    pol = api(f"/accounts/{ACCOUNT}/access/apps/{app['id']}/policies", {
        "name": "portal members", "decision": "allow",
        "include": [{"email": {"email": m}} for m in EMAILS]})
    if not pol.get("success"):
        raise SystemExit(f"policy create failed: {pol.get('errors')}")
    print(f"policy created: portal members ({len(EMAILS)} email entries)")
else:
    print("policy exists: portal members")

print("done: gate applies to", DOMAIN, "(rest of the host stays public)")
