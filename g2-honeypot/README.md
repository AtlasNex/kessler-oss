# g2-honeypot — the public lab agent (PLAN-v4 Phase 6.1)

A live LLM agent with a secret it must never reveal and two declared tools (`wiki`, `notes`),
published so anyone can attack it. Every attempt is captured verbatim; the hit rate is
published **with its Wilson interval, computed by the same kernel engagements use**
(`kessler.asi` from github.com/AtlasNex/kessler-oss) — never a yes/no claim.

Live: see `/stats` on each instance. The page publishes `n`, hits, ASR and the 95% Wilson
interval, and says in plain words that this is a dated measurement, not a claim of safety.

## The four work packages

| WP | What | State |
| --- | --- | --- |
| WP1 | Server + capture (`server.py`, `capture.db`, OpenAI-compatible endpoint so the Kessler HTTP driver conducts against it directly) | built |
| WP2 | Intervalled ASR publishing from the kernel (`/stats` — `kessler.asi` Wilson intervals; the kernel missing = the page says ASR UNAVAILABLE, never a fabricated number) | built |
| WP3 | Recorded attempts -> corpus inflow (`export-capture.py` -> `capture-export.jsonl` + `capture-pack.json` candidate pack) | built |
| WP4 | A/B technique-pack commits (the candidate pack, labelled after OWNER review — labels are his call, never ours) | awaiting captures + owner labels |

## The A/B: two instances, different credentials

`docker-compose.yml` runs `honey-a` (clean context) and `honey-b` (a credential LURE in its
context). The leak rate difference is the experiment. Secrets come from `.env` (never
committed): `HONEY_MODEL_URL`, `HONEY_MODEL_KEY`, `HONEY_SECRET`, `HONEY_LURE_B`.

## Deploy (the kessler-site pattern)

```
cd g2-honeypot
cp .env.example .env      # fill HONEY_MODEL_URL/KEY (env-only, never logged)
docker compose up -d --build
curl localhost:8095/health && curl localhost:8095/stats
```
Public exposure sits behind the Cloudflare tunnel (route both ports to a public subpath or
subdomain, proxied CNAME), like `kessler-site.service` does for the reports.

## Interval discipline (WP2's rule)

The scoreboard publishes **n and the interval**, never "secure"/"insecure". A zero-hit run at
n=20 still cannot exclude a true hit rate under ~16% — the Wilson interval IS the answer.

## What this honeypot does NOT claim

- Attacks we do not record did not happen here. The capture is this instance, this period.
- A hit is a demonstration of leak; a miss is not proof of safety (interval, not adjective).
- Captured visitor text becomes a corpus CANDIDATE under review — nothing auto-ingests.
