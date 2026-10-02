"""Susceptibility Data Sheet v0.1 (PLAN-v5 #23) — the measured input the risk-transfer
market consumes and nobody sells.

What it is
----------
One machine-readable page (JSON + a rendered human sheet) for ONE estate: per-ASI intervalled
ASR, N per category, corpus + method versions, the judge-calibration floor printed beside the
numbers, an estate fingerprint from the blast engine, and reliance-limiting language that is
PART of the document, not a disclaimer bolted on. The buyers today are brokers and MGAs
preparing submissions 60-90 days before renewal (19e §5.2), NOT carriers: carriers assess,
they do not yet publish a requirement for this shape (falsification = the broker answer).

FAIR mapping (the note, not the number): FAIR quantifies loss in frequency x magnitude; an
ASR over counted attempts with an interval estimates the *event probability component* — the
susceptibility input a FAIR model multiplies by exposure. A sheet NEVER states a loss
expectancy; magnitude is not ours to know, and printing one would be the kind of unsourced
number this practice refuses.

Honesty rails, enforced here:
* intervalled ASR or nothing: a category with attempts < 40 prints "low-power" (the N-floor
  grammar from the baseline register), and the sheet marks the whole unit as
  measurement-grade: engagement rates ship at their own n WITH their interval;
* `mapped to ASI01-ASI10`, never certified (lint refuses claims);
* judge-calibration floor printed beside every automated-oracle number when the engagement
  used an LLM-judged channel (the measured FP rate from datasets/calibration; the sheet says
  WHICH rows that applies to);
* reliance limits in the payload; a consumer cannot strip them by ignoring rendering.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date

from .asi import ALL_IDS, compute_asr
from .baseline import N_FLOOR
from .blast import compute_blast_radius
from .report import _interval, _pct

SDS_SCHEMA = "kessler/sds/v0.1"

#: Reliance-limiting language, in the payload itself (kill list / honesty register).
RELIANCE_LIMITS = [
    "Findings are mapped to OWASP ASI01-ASI10; no accredited body certifies against this "
    "framework and nothing in this sheet is a certification.",
    "Rates are measured over counted attempts with 95% Wilson intervals; a 0% on a small "
    "sample is a measurement limit, not a guarantee.",
    "The sheet attests that adversarial testing was performed on the stated scope, window "
    "and method; it does not attest security, insurability, or compliance.",
    "Magnitude of loss is out of scope: this is susceptibility input for a loss model, not "
    "a loss model.",
]

#: FAIR-component note (structural, verbatim in the payload).
FAIR_NOTE = (
    "FAIR mapping (component, not output): per-ASI intervalled ASR over counted attempts "
    "informs the primary-event / threat-probability component of a FAIR model; secondary-"
    "event probability (detection/response) and loss magnitude are NOT supplied here and "
    "must not be inferred from it. The estate fingerprint lets a consumer align sheets to "
    "one estate across time; it is an identity, not a score."
)


def sds_from_engagement(engagement, *, corpus_hash: str, method_version: str,
                        judge_floor: dict | None = None,
                        issuer: str = "Kessler (AtlasNex)") -> dict:
    asr = compute_asr(engagement.attempts)
    br = compute_blast_radius(engagement.targets)
    fingerprint = hashlib.sha256(
        json.dumps({"scope": engagement.scope_sha256,
                    "targets": sorted((t["id"], t["kind"], sorted(t.get("reaches") or []))
                                      for t in engagement.targets)},
                   sort_keys=True).encode()).hexdigest()
    categories = {}
    for cid in ALL_IDS:
        row = asr[cid]
        n = int(row["attempts"])
        if not n:
            categories[cid] = {"attempts": 0, "status": "not tested in this scope"}
            continue
        categories[cid] = {
            "attempts": n, "successes": int(row["successes"]),
            "asr": row["asr"], "ci_low": row["ci_low"], "ci_high": row["ci_high"],
            "power": "published" if n >= N_FLOOR else "low-power (n<%d): interval is wide" % N_FLOOR,
        }
    doc = {
        "schema": SDS_SCHEMA,
        "engagement_ref": engagement.ref,
        "client": engagement.client,
        "window": {"start": engagement.start, "end": engagement.end},
        "issued": date.today().isoformat(),
        "issuer": issuer,
        "method": {"corpus_hash": corpus_hash, "method_version": method_version,
                   "evidence_rule": "C-1: no recorded success without a verbatim observation",
                   "interval": "Wilson 95%"},
        "judge_calibration": judge_floor or {"applies": False},
        "estate_fingerprint": fingerprint,
        "blast_summary": br.summary(),
        "categories": categories,
        "overall": {k: asr["__overall__"][k] for k in
                    ("attempts", "successes", "asr", "ci_low", "ci_high")},
        "fair_note": FAIR_NOTE,
        "reliance_limits": RELIANCE_LIMITS,
    }
    return doc


def render_sds_md(sheet: dict) -> str:
    lines = [
        f"# Susceptibility Data Sheet — {sheet['client']}",
        "",
        f"**Engagement** {sheet['engagement_ref']} · **Window** {sheet['window']['start']} to "
        f"{sheet['window']['end']} · **Issued** {sheet['issued']} · **By** {sheet['issuer']}",
        f"**Estate fingerprint** `{sheet['estate_fingerprint'][:16]}…` · **Method** "
        f"{sheet['method']['method_version']} · corpus `{sheet['method']['corpus_hash'][:12]}…`",
        "",
        "| ASI | Attempts | Successes | ASR | 95% interval | Power |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for cid, c in sheet["categories"].items():
        if not c["attempts"]:
            lines.append(f"| {cid} | 0 | — | — | — | {c['status']} |")
            continue
        lines.append(f"| {cid} | {c['attempts']} | {c['successes']} | {_pct(c['asr'])} | "
                     f"[{c['ci_low'] * 100:.1f}%, {c['ci_high'] * 100:.1f}%] | {c['power']} |")
    ov = sheet["overall"]
    lines.append(f"| **overall** | {ov['attempts']} | {ov['successes']} | {_pct(ov['asr'])} | "
                 f"{_interval(ov)} | engagement-scale |")
    if sheet.get("judge_calibration", {}).get("applies"):
        j = sheet["judge_calibration"]
        lines += ["", f"*Judge floor beside these numbers: FP {j.get('fp_rate', 'n/a')}, "
                      f"FN {j.get('fn_rate', 'n/a')} (measured, quoted as measured).*"]
    lines += ["", "## Reliance limits", ""]
    lines += [f"{i}. {t}" for i, t in enumerate(sheet["reliance_limits"], 1)]
    lines += ["", "## FAIR mapping", "", sheet["fair_note"], ""]
    lines += [f"*Machine form: `sds.json` (schema {sheet['schema']}). Recompute check: the "
              "capsule for this engagement re-runs every figure above from its evidence chain.*"]
    return "\n".join(lines)
