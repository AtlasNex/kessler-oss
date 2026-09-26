#!/usr/bin/env python3
"""WP3: export captured attempts as corpus-inflow candidates + a first-party behaviour pack.

Reads capture.db (copy it out of the container first: `docker cp g2-honey-a:/data/capture.db .`)
and writes:
  capture-export.jsonl  — every attempt verbatim (the C-1 evidence, for the corpus inflow review)
  capture-pack.json     — a FIRST-PARTY behaviour pack of the attack texts seen (deduped),
                          for owner review before it enters datasets/behaviors/ (WP4's A/B
                          pack commits are the same rows, labelled after review)

Rows are candidates, never claims. The licence gate still governs anything that lands in
datasets/behaviors/; this script never writes there itself (human gate, PLAN-v4 Phase 6.1).
"""
from __future__ import annotations

import json
import sqlite3
import sys
from datetime import date
from pathlib import Path

DB = sys.argv[1] if len(sys.argv) > 1 else "capture.db"
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else "capture-export")

conn = sqlite3.connect(DB)
rows = conn.execute("SELECT at, instance, request, reply, hit FROM attempts ORDER BY id").fetchall()
OUT.mkdir(parents=True, exist_ok=True)

with (OUT / "capture-export.jsonl").open("w", encoding="utf-8") as fh:
    for at, instance, request, reply, hit in rows:
        fh.write(json.dumps({"at": at, "instance": instance, "request": request,
                             "reply": reply, "hit": bool(hit)}, ensure_ascii=False) + "\n")

seen: set[str] = set()
pack_rows = []
for at, instance, request, reply, hit in rows:
    try:
        text = json.loads(request).get("messages", [{}])[-1].get("content", "")
    except (json.JSONDecodeError, IndexError, AttributeError):
        continue
    text = text.strip()
    if not text or text in seen:
        continue
    seen.add(text)
    pack_rows.append({"id": f"B-HONEY-{len(pack_rows) + 1:03d}", "text": text,
                      "applies_to": ["ASI01", "ASI06", "ASI10"]})

pack = {
    "schema": "kessler/behaviors/v1",
    "name": "g2-honeypot-captures",
    "version": 1,
    "description": ("First-party frames over ATTACK TEXTS captured live by the g2-honeypot "
                    "(WP3/WP4). CANDIDATE PACK: owner review required before it enters "
                    "datasets/behaviors/ — labels are the owner's call."),
    "updated": date.today().isoformat(),
    "provenance": {
        "source": "g2-honeypot live captures (public lab agent)",
        "url": "https://kessler.atlasnex.com/",
        "licence": "MIT (first-party capture processing; the attack texts are first-party "
                   "observed behaviour of visitors to a honeypot WE own)",
        "retrieved": date.today().isoformat(),
        "verified_by": "captured verbatim by g2-honeypot/server.py; deduped on exact text",
    },
    "behaviors": pack_rows,
}
(OUT / "capture-pack.json").write_text(json.dumps(pack, indent=1, ensure_ascii=False) + "\n",
                                       encoding="utf-8")
print(f"EXPORTED {len(rows)} attempt(s) -> {OUT}/capture-export.jsonl")
print(f"CANDIDATE PACK {len(pack_rows)} row(s) -> {OUT}/capture-pack.json (owner review, WP4)")
