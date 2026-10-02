"""Append-only content-addressed evidence store (PLAN-v5 #10).

Why this exists
---------------
The engagement document is the EXPORT contract (sealed, schema `kessler/engagement/v1`); the
store is the OPERATIONAL substrate under it: every evidence object ever recorded, written once,
addressed by its own SHA-256, never modified, never deleted mid-stream. It answers the auditor
question the document alone cannot: "show me byte-level history of what you recorded and when
you recorded it." SQLite would work; ndjson is lazier (one file, append with `>>`, readable with
`cat`, diffable in a pinch) and the ceiling is stated below.

What is content-addressed here: the RECORD (the JSON line: kind + payload + recorded_at). A
duplicate payload for the same kind hashes to the same id and is a no-op append (dedupe by
construction, not by query). There is nothing to "fix" later: a corrected observation is a NEW
record; readers follow the newest id referenced by the document. History never changes (C-9's
storage twin).

Honest limits (ponytail, stated):
* ceiling: single-writer, file-based; fine for hundreds of engagements per year, and the store
  file grows linearly with evidence volume; upgrade path is SQLite (same API shape) if anyone
  runs concurrent writers;
* it is NOT a blockchain or a tamper-proof claim: an attacker who can rewrite the whole file can
  rewrite this too. Tamper-EVIDENCE comes from the capsule chain (capsule.py) and from storing
  the head digest off-box (the /verify anchor). This module guarantees append-consistency: a
  file that was appended to still verifies, and any earlier mutation breaks its line-hash.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

STORE_SCHEMA = "kessler/store-record/v1"


def _canon(obj: dict) -> bytes:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":")).encode("utf-8")


def record_id(record: dict) -> str:
    return hashlib.sha256(_canon(record)).hexdigest()


class EvidenceStore:
    """One append-only ndjson file. `append(kind, payload)` returns (id, wrote_new)."""

    def __init__(self, path):
        self.path = Path(path)

    def _lines(self) -> list[str]:
        if not self.path.exists():
            return []
        return [ln for ln in self.path.read_text(encoding="utf-8").splitlines() if ln.strip()]

    def append(self, kind: str, payload: dict, *, recorded_at: str) -> tuple[str, bool]:
        body = {"schema": STORE_SCHEMA, "kind": kind, "payload": payload,
                "recorded_at": recorded_at}
        rid = record_id(body)
        existing = {json.loads(ln)["id"] for ln in self._lines()}
        if rid in existing:
            return rid, False                      # idempotent: same bytes, no re-append
        body["id"] = rid
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(body, sort_keys=True, ensure_ascii=False) + "\n")
        return rid, True

    def verify(self) -> dict:
        """Every line must re-hash to its own id; ids must be unique; order must be stable.
        A mutated historical line breaks its own hash; the file is append-only by check, not
        by filesystem promise."""
        seen: set[str] = set()
        errors: list[str] = []
        for i, ln in enumerate(self._lines(), 1):
            try:
                rec = json.loads(ln)
            except json.JSONDecodeError:
                errors.append(f"line {i}: not valid JSON")
                continue
            rid = rec.pop("id", None)
            if rec.get("schema") != STORE_SCHEMA:
                errors.append(f"line {i}: schema {rec.get('schema')!r} != {STORE_SCHEMA}")
            elif rid != record_id(rec):
                errors.append(f"line {i}: content hash mismatch — the record was mutated "
                              "after it was written (append-only violated)")
            elif rid in seen:
                errors.append(f"line {i}: duplicate id {rid[:12]}…")
            seen.add(rid or f"bad-{i}")
        return {"ok": not errors, "records": len(seen), "errors": errors,
                "head": sorted(seen)[-1] if seen else None}

    def head_digest(self) -> str:
        """SHA-256 over the whole file — pin this off-box; the /verify anchor does."""
        if not self.path.exists():
            return hashlib.sha256(b"").hexdigest()
        return hashlib.sha256(self.path.read_bytes()).hexdigest()


def ingest_engagement(store: "EvidenceStore", engagement, *, recorded_at: str) -> dict:
    """Write every attempt's evidence + finding payload into the store, and return the id map
    the document references. Idempotent: re-ingesting an unchanged document writes nothing."""
    ids = {"attempts": [], "findings": []}
    for i, a in enumerate(engagement.attempts):
        rid, _ = store.append("attempt", {
            "category": a.category, "technique": a.technique, "succeeded": a.succeeded,
            "observed": a.observed, "payload": a.payload, "at": a.at,
            "adapter_ref": a.adapter_ref, "index": i}, recorded_at=recorded_at)
        ids["attempts"].append(rid)
    for f in engagement.findings:
        rid, _ = store.append("finding", {
            "finding_id": f.finding_id, "category": f.category, "title": f.title,
            "evidence": f.evidence, "reproduction": f.reproduction}, recorded_at=recorded_at)
        ids["findings"].append(rid)
    return ids
