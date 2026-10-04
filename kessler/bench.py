"""Open Bench v0 (PLAN-v5 #22) — the legally-clean public baseline.

Scope, locked by the plan (§2.3, owner-accepted in D-037): OWN lab + the g2 honeypots +
self-hosted open-source agent builds + CONSENTING OPT-IN targets only. Never a third-party
hosted stack: attacking someone else's product without their written permission is a crime
and an ending, no matter how interesting the number. Per-target written authorization is a
preregistration field; maintainer consent for an OSS repo is NOT consent to attack a hosted
instance (self-hosted mirrors or provider-ToS-compliant use only).

What v0 is
----------
A **unit registry**: every bench unit is one engagement document over the PREREGISTERED
automated-oracle subset, registered with its target kind, authorization record, corpus pin
and method. Published cells appear only at the preregistered floor (n >= 400 per cell,
`baseline.N_FLOOR`); below it the cell prints "not yet powered" and publishes nothing.
The register renders as the public baseline page's data; the methodology page is versioned
by `METHOD_VERSION`; every cell re-runs from the OSS kernel.

Cascade discipline (kill list 6): this module reads documents and computes. It never launches
traffic itself — the runner (`kessler run`) does that against scopes you own or are written
authorized for. An unauthorized target cannot be registered: `auth` is a required field and
a row without it raises at register time.
"""
from __future__ import annotations

import json
from pathlib import Path

from .asi import compute_asr
from .baseline import N_FLOOR

BENCH_SCHEMA = "kessler/open-bench/v0"

#: The methodology stamp. Bump with the PREREGISTRATION diff recorded in DECISIONS; cells
#: from different method versions are never compared (that would be theatre, not a baseline).
METHOD_VERSION = "v0.0"

#: What "preregistered automated subset" concretely means (frozen here so it cannot drift):
#: the `--automated-only` corpus subset (4 automated-oracle techniques, 1,101 composed cases),
#: Wilson intervals, C-1 evidence gate, echo/live drivers as recorded in the document method.
PREREGISTRATION = {
    "subset": "automated-oracle cases of the composed corpus (kessler run --automated-only)",
    "corpus_case_count": 1101,
    "per_cell_floor": N_FLOOR,
    "interval": "Wilson 95% (kessler.asi.wilson_interval)",
    "evidence": "C-1: no success without a verbatim observation",
    "verdict_rule": "no verdicts; rates with intervals only (kill list 6)",
}

#: Target kinds the bench accepts. Third-party hosted services are NOT a kind that exists here.
KINDS = ("own-lab", "g2-honeypot", "oss-selfhosted", "opt-in-consented")

#: The authorization record kinds that satisfy the scope law.
AUTH_KINDS = ("ownership", "written-authorization")

UNIT_KEYS = ("ref", "target_kind", "authorization", "corpus_hash", "method_version",
             "n", "successes", "per_category", "document_sha256", "window", "measured")


def register_unit(*, ref: str, target_kind: str, authorization: dict, engagement,
                  corpus_hash: str, measured: str) -> dict:
    """Build one bench unit from an engagement document (the SAME doc that produced the run).

    `authorization` must name one of AUTH_KINDS: `{"kind":"ownership"}` for our own lab /
    honeypot, or `{"kind":"written-authorization","file":"<path-or-reference>","signed":"..."}`
    for consented targets. Anything else raises: an unregistered target is refused here, which
    is the point of registering."""
    if target_kind not in KINDS:
        raise ValueError(f"target kind {target_kind!r} not in bench scope: {', '.join(KINDS)} "
                         "(third-party hosted targets are not a registrable kind)")
    kind = authorization.get("kind")
    if kind not in AUTH_KINDS:
        raise ValueError(
            f"authorization kind {kind!r} is not a bench-scope authorization: expected one of "
            f"{', '.join(AUTH_KINDS)} (maintainer consent to a repo is NOT consent to attack a "
            "hosted instance)")
    if kind == "written-authorization" and not authorization.get("file"):
        raise ValueError("written-authorization must name the authorization file/reference")
    asr = compute_asr(engagement.attempts)
    ov = asr["__overall__"]
    per_category = {
        cid: {"attempts": int(r["attempts"]), "successes": int(r["successes"])}
        for cid, r in asr.items() if cid != "__overall__" and r["attempts"]
    }
    from .schema import dumps
    import hashlib
    doc_sha = hashlib.sha256(dumps(engagement).encode("utf-8")).hexdigest()
    return {
        "ref": ref,
        "target_kind": target_kind,
        "authorization": dict(authorization),
        "corpus_hash": corpus_hash,
        "method_version": METHOD_VERSION,
        "n": int(ov["attempts"]),
        "successes": int(ov["successes"]),
        "per_category": per_category,
        "document_sha256": doc_sha,
        "window": f"{engagement.start} to {engagement.end}",
        "measured": measured,
    }


def load_register(path) -> dict:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if raw.get("schema") != BENCH_SCHEMA:
        raise ValueError(f"register schema {raw.get('schema')!r} != {BENCH_SCHEMA!r}")
    if raw.get("preregistration") != PREREGISTRATION:
        raise ValueError("register's preregistration block differs from the code's frozen "
                         "PREREGISTRATION - the preregistration moved without a decision entry")
    for u in raw["units"]:
        if set(u) != set(UNIT_KEYS):
            raise ValueError(f"unit {u.get('ref')!r} does not match the closed-world unit keys")
    return raw


def save_register(register: dict, path) -> None:
    Path(path).write_text(json.dumps(register, indent=1, ensure_ascii=False) + "\n",
                          encoding="utf-8")


def render_bench_md(register: dict) -> str:
    """The public table. Cells publish at the floor; the rest show their n and say so.
    The honesty posture is the UL/"attests that testing was performed on the stated
    scope/date/method" pattern - no vendor is graded, no stack is attacked, numbers
    are re-runnable."""
    lines = [
        "| Bench unit | Kind | Corpus | n | ASR | Interval | Status |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    from .asi import wilson_interval
    for u in sorted(register["units"], key=lambda u: u["ref"]):
        powered = u["n"] >= N_FLOOR
        ci = wilson_interval(u["successes"], u["n"]) if u["n"] else (None, None)
        rate = f"{u['successes'] / u['n'] * 100:.1f}%" if powered else "—"
        band = (f"[{ci[0] * 100:.1f}%, {ci[1] * 100:.1f}%]" if powered and ci[0] is not None
                else "—")
        if powered:
            status = ("published" if u["successes"]
                      else f"published; 0 observed in n={u['n']} attempts")
        else:
            status = f"not yet powered (n={u['n']} < {N_FLOOR})"
        lines.append(f"| {u['ref']} | {u['target_kind']} | {u['corpus_hash'][:12]}… | "
                     f"{u['n']} | {rate} | {band} | {status} |")
    lines += [
        "",
        f"Preregistration (frozen in code, method {METHOD_VERSION}): automated-oracle subset "
        f"only, per-cell floor n>={N_FLOOR}, Wilson 95%, evidence-gated, no verdicts. Every "
        f"unit re-runs from the open kernel; scope law: own lab, our honeypots, self-hosted "
        f"OSS builds, and written-authorized consented targets - never a third-party hosted "
        f"stack, and maintainer consent to a repo is not consent to attack its instance.",
        " A zero row reports what was not observed among the attempts run; read the "
        "interval's upper bound at that n and nothing more.",
    ]
    return "\n".join(lines)
