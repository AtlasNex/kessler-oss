"""The Verifiable Evidence Capsule (PLAN-v5 #11, Wave 2) — checkable measurement.

Why this exists
---------------
The one differentiator: every other vendor shows a dashboard; Kessler hands over a number a third
party can recompute. The capsule is the L2 layer — "re-checkable numbers" — in three properties:

1. **Hash-chained evidence.** Each record carries `sha256(prev_hash + its own canonical JSON)`,
   so any byte edited anywhere breaks every later link. Tamper-evidence, not encryption: a
   tampered capsule is DETECTED, never hidden.
2. **A recomputable verdict.** `verify_capsule` re-runs `compute_asr` over the records and
   demands byte-equality with the `asr` block. A report figure that disagrees with the evidence
   chain is a broken capsule, not a disagreement of opinion.
3. **One anchored head.** The final `prev_hash` (head_hash) is a single 64-hex string a client
   can print on a report, pin in their CI, or anchor in a public page. Everything above it is
   covered by it.

C-2 (stdlib only) holds: hashlib, json, dataclasses. C-1 is untouched — a capsule wraps an
already-validated engagement; it never constructs an Attempt itself.

What the capsule deliberately does NOT claim
--------------------------------------------
The manifest's `claim` is worded once, here, and the linter refuses mutations: a capsule proves
ARITHMETIC and TAMPER-EVIDENCE. It never says the estate is "secure", never grades, never
certifies. (See `claim` below and tests/test_capsule.py.)
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from .asi import Attempt, compute_asr, wilson_interval
from .gate import attempts_digest  # same canonical row digest the gate pins — one rule, reused

#: Versioned shape. Closed-world keys (like the engagement document): deployed parsers reject
#: unknown keys, so a field addition bumps this — never silently extended.
CAPSULE_SCHEMA = "kessler/capsule/v1"

#: The claim, byte-exact. Tests pin it; the verify path refuses capsule `claim` fields that
#: carry certification language. Denials of security are exempt by construction here: the claim
#: never asserts security in the first place.
CAPSULE_CLAIM = (
    "This capsule makes the arithmetic checkable and tamper-evident: recompute every figure "
    "from the chained evidence with the open-source kernel. It proves arithmetic, not security, "
    "and it is not a certification."
)

#: Top-level keys, dump order. Closed world.
CAPSULE_KEYS: tuple[str, ...] = (
    "schema", "claim", "engagement_ref", "scope_sha256", "corpus_hash", "method",
    "created_at", "chain", "asr", "head_hash",
)

#: Metadata for one capsule. Closed world too — these ride into every chain record.
CAPSULE_META_KEYS: tuple[str, ...] = (
    "engagement_ref", "scope_sha256", "corpus_hash", "method", "created_at",
)


def _canon(value: Any) -> bytes:
    """Canonical JSON bytes for hashing: sorted keys, no spaces, utf-8."""
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()


def canonical_corpus_hash() -> str:
    """SHA-256 over the composed corpus, deterministically.

    This is the pin that makes "same corpus version" checkable: a client re-runs the OSS kernel,
    recomposes the corpus, hashes it, and compares. A different corpus hash means the run was
    not against the same test material — the honest failure mode, printed rather than hidden.
    """
    from .corpus import build

    cases, _, _ = build()
    blob = _canon([
        {"id": c.id, "category": c.category, "technique_id": c.technique_id,
         "behavior_id": c.behavior_id, "channel_id": c.channel_id, "content": c.content}
        for c in cases
    ])
    return hashlib.sha256(blob).hexdigest()


def build_capsule(engagement, meta: dict) -> dict:
    """Build the capsule document for one engagement.

    `meta` must carry all five CAPSULE_META_KEYS (engagement_ref/scope_sha256 are cross-checked
    against the engagement and refused on mismatch — a capsule about a different engagement is
    worse than no capsule). The chain wraps: the engagement facts, then every attempt row, then
    the computed ASR. The head hash is the last record's `hash`.
    """
    if not isinstance(meta, dict) or set(meta) != set(CAPSULE_META_KEYS):
        raise ValueError(
            f"meta must be exactly {', '.join(CAPSULE_META_KEYS)} — closed-world capsule metadata"
        )
    if meta["engagement_ref"] != engagement.ref:
        raise ValueError(
            f"meta.engagement_ref {meta['engagement_ref']!r} != engagement.ref "
            f"{engagement.ref!r} — a capsule wraps one engagement, not a near miss"
        )
    if meta["scope_sha256"] != engagement.scope_sha256:
        raise ValueError(
            "meta.scope_sha256 != engagement.scope_sha256 — the capsule would pin the wrong scope"
        )
    if not engagement.attempts:
        raise ValueError(
            "refusing to build a capsule over zero attempts — there is nothing to check"
        )

    # Every attempt row, in document order, as the gate's canonical digest sees them — plus the
    # full evidence fields (observed/payload/environment), because the capsule's job is to make
    # the EVIDENCE tamper-evident, not just the verdicts.
    rows = [
        {
            "category": a.category,
            "technique": a.technique,
            "succeeded": a.succeeded,
            "observed": a.observed,
            "payload": a.payload,
            "environment": a.environment,
            "at": a.at,
            "adapter_ref": a.adapter_ref,
        }
        for a in engagement.attempts
    ]
    asr = compute_asr(engagement.attempts)
    # Deep copies: the chain record, the asr block, and the caller's view must be INDEPENDENT
    # dicts. Sharing one object (a shallow-truth bug the tamper probe caught) means editing the
    # top-level block also edits the chain's copy, and the verify path would then recompute a
    # matching lie. Every hash covers exactly the bytes it claims.
    import copy as _copy
    asr_chain = _copy.deepcopy(asr)
    asr_block = _copy.deepcopy(asr)
    overall = asr["__overall__"]
    interval = wilson_interval(int(overall["successes"]), int(overall["attempts"]))

    chain: list[dict] = []
    prev = "0" * 64  # genesis: the all-zero head, the same convention as a ledger block

    def _link(record: dict) -> None:
        nonlocal prev
        body = {**meta, "prev_hash": prev, "record": record}
        h = hashlib.sha256(_canon(body)).hexdigest()
        chain.append({**body, "hash": h})
        prev = h

    # Record 1: the engagement facts + the gate digest over the attempt sequence (so the chain
    # and the gate's committed baseline pin the SAME canonical rows).
    _link({
        "kind": "engagement",
        "ref": engagement.ref,
        "client": engagement.client,
        "window": {"start": engagement.start, "end": engagement.end},
        "scope_sha256": engagement.scope_sha256,
        "testers": list(engagement.testers),
        "targets": [
            {"id": t["id"], "kind": t["kind"], "version": t.get("version", ""),
             "reaches": list(t["reaches"])}
            for t in engagement.targets
        ],
        "attempts_digest": attempts_digest(engagement.attempts),
    })
    # Records 2..N+1: every attempt, verbatim.
    for r in rows:
        _link({"kind": "attempt", **r})
    # Final record: the computed verdict block the chain must reproduce on verify.
    _link({"kind": "asr", "asr": asr_chain})

    return {
        "schema": CAPSULE_SCHEMA,
        "claim": CAPSULE_CLAIM,
        "engagement_ref": engagement.ref,
        "scope_sha256": engagement.scope_sha256,
        "corpus_hash": meta["corpus_hash"],
        "method": meta["method"],
        "created_at": meta["created_at"],
        "chain": chain,
        "asr": asr,
        "head_hash": prev,
    }


@dataclass(frozen=True)
class VerifyResult:
    """The verdict of `verify_capsule`. Three states, never two (the B-9 discipline):
    valid / tampered / not-even-checkable."""

    ok: bool
    errors: list[str]
    recomputed_asr: dict | None

    def render(self) -> str:
        lines = [
            f"CAPSULE VERIFY  {'VALID' if self.ok else 'FAILED'}  "
            f"({len(self.errors)} error(s))"
        ]
        for e in self.errors:
            lines.append(f"  - {e}")
        if self.ok:
            ov = self.recomputed_asr["__overall__"]
            lines.append(
                f"  recomputed overall ASR {ov['successes']}/{ov['attempts']} = "
                f"{ov['asr'] * 100:.2f}% matches the capsule's verdict block"
            )
        lines.append(
            "  a capsule proves arithmetic and tamper-evidence; it is not a security verdict "
            "and not a certification"
        )
        return "\n".join(lines)


def _reject(claim: str) -> str | None:
    """Refuse certification language in the capsule's own claim field (bundle.py's rule).

    The byte-exact CAPSULE_CLAIM is exempt — it is a DENIAL ("not a certification"), the same
    pattern as bundle._EXEMPT_DENIALS: a regex cannot tell a denial from a claim, so only the
    exact known sentence passes and any mutated variant still trips.
    """
    from .bundle import lint_prose
    if claim == CAPSULE_CLAIM:
        return None
    hits = lint_prose(claim)
    return hits[0] if hits else None


def verify_capsule(capsule: dict) -> VerifyResult:
    """Recompute everything from the chain and refuse to pass on any drift.

    Checks, in order (every failure listed, not just the first):
    1. shape: schema id + closed-world keys;
    2. claim: no certification language, byte-exact known claim or a checkable equivalent;
    3. chain integrity: every record's hash equals sha256(prev_hash + itself), links connect;
    4. records: exactly one engagement record, >=1 attempt record, one asr record, nothing else;
    5. recompute: compute_asr over the attempt records == the asr record == the top-level asr;
    6. head: head_hash == the last record's hash.
    """
    errors: list[str] = []

    if not isinstance(capsule, dict):
        return VerifyResult(False, ["capsule must be a JSON object"], None)
    unknown = sorted(set(capsule) - set(CAPSULE_KEYS))
    missing = [k for k in CAPSULE_KEYS if k not in capsule]
    if missing:
        errors.append(f"missing key(s): {', '.join(missing)}")
    if unknown:
        errors.append(f"unknown key(s): {', '.join(unknown)}")
    if errors:
        return VerifyResult(False, errors, None)
    if capsule["schema"] != CAPSULE_SCHEMA:
        errors.append(f"schema {capsule['schema']!r} != {CAPSULE_SCHEMA!r}")
        return VerifyResult(False, errors, None)

    bad = _reject(capsule["claim"])
    if bad:
        errors.append(f"claim carries certification language: {bad}")

    chain = capsule["chain"]
    if not isinstance(chain, list) or not chain:
        errors.append("chain must be a non-empty list")
        return VerifyResult(False, errors, None)

    prev = "0" * 64
    kinds: list[str] = []
    for i, link in enumerate(chain):
        if not isinstance(link, dict):
            errors.append(f"chain[{i}] is not an object")
            continue
        expected_keys = set(CAPSULE_META_KEYS) | {"prev_hash", "record", "hash"}
        if set(link) != expected_keys:
            errors.append(f"chain[{i}] keys are not exactly the metadata + prev_hash/record/hash")
            continue
        body = {k: link[k] for k in (set(CAPSULE_META_KEYS) | {"prev_hash", "record"})}
        h = hashlib.sha256(_canon(body)).hexdigest()
        if h != link["hash"]:
            errors.append(f"chain[{i}] hash mismatch — record was edited (tamper-evidence)")
        if link["prev_hash"] != prev:
            errors.append(f"chain[{i}] prev_hash does not link to chain[{i - 1 if i else 0}]"
                          + ("" if i else " (genesis must be the all-zero hash)"))
        prev = link["hash"]
        kinds.append(str(link.get("record", {}).get("kind")))

    if kinds.count("engagement") != 1:
        errors.append(f"expected exactly one engagement record, found {kinds.count('engagement')}")
    if kinds.count("asr") != 1 or kinds[-1] != "asr":
        errors.append("expected exactly one asr record, as the final record")
    attempt_recs = [lnk["record"] for lnk in chain if lnk.get("record", {}).get("kind") == "attempt"]
    if not attempt_recs:
        errors.append("no attempt records in the chain — nothing to recompute")

    if errors:
        return VerifyResult(False, errors, None)

    # Rebuild attempts through the kernel constructor (C-1 at the verify boundary too: an
    # unevidenced success in a tampered record would fail the hash check first, but a
    # hand-BUILT capsule with an unevidenced success must fail here as well).
    attempts: list[Attempt] = []
    for i, r in enumerate(attempt_recs):
        try:
            attempts.append(Attempt(
                category=r["category"], technique=r["technique"], succeeded=r["succeeded"],
                observed=r["observed"], payload=r["payload"], environment=r["environment"],
                at=r["at"], adapter_ref=r["adapter_ref"],
            ))
        except (KeyError, ValueError) as exc:
            errors.append(f"attempt record {i} is not a constructible Attempt: {exc}")
    if errors:
        return VerifyResult(False, errors, None)

    recomputed = compute_asr(attempts)
    asr_record = chain[-1]["record"]["asr"]
    if recomputed != asr_record:
        errors.append(
            "recomputed ASR != the chain's asr record — the verdict block does not follow "
            "from the evidence"
        )
    if recomputed != capsule["asr"]:
        errors.append("recomputed ASR != the capsule's top-level asr block")
    if capsule["head_hash"] != chain[-1]["hash"]:
        errors.append("head_hash != the final record's hash — the anchor is wrong or stale")

    return VerifyResult(not errors, errors, recomputed if not errors else None)
