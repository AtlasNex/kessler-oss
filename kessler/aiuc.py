"""AIUC-1 quarterly evidence pack (PLAN-v5 #24) — the crosswalk and the signed quarterly pack.

What this is
------------
AIUC-1 (the underwriting certification standard: 51 requirements / 130 controls across six
pillars; technical testing at least quarterly, 1,000-5,000 scenarios; certificates issued by
AIUC via accredited auditors) is the certification the market formed this year. We do not
compete with it and never claim it: KESS findings are **mapped to** AIUC-1 control territory
as an evidence engine an auditor or a submission preparer can consume. The pack renders the
quarterly evidence shape AIUC conditions cover on: what was tested this quarter, at what N,
with what intervals, what remediation closed, and what the quarterly re-attestation (Monitor
/ R4 / Standing Attestation) re-runs.

Honesty rails (kill list 2, honesty register):
* the word "certified"/"accredited" appears ONLY in the denial sentence, and
  bundle.lint_prose gates the render;
* the crosswalk is a HYPOTHESIS mapping from the research stream (19e §3/§4) to control
  TERRITORY, not to numbered requirements we do not have the standard's text for; the sheet
  says exactly that.
"""
from __future__ import annotations

from datetime import date

from .asi import compute_asr
from .bundle import lint_prose
from .report import _interval, _pct

PACK_SCHEMA = "kessler/aiuc-pack/v0"

#: The six AIUC-1 pillars (public description: 51 requirements / 130 controls across six
#: pillars; source aiuc-1.com/learn/certificate via 19e) mapped to the evidence a Kessler
#: engagement actually ships. Control numbers are NOT asserted — we do not hold the full
#: standard text; the mapping is territory, and the pack says so.
PILLAR_MAP: tuple[tuple[str, str, str], ...] = (
    ("Data & privacy", "ASI03 identity/privilege, ASI06 memory poisoning (exfiltration paths)",
     "ASR table + blast radius (what leaked from where) + AIBOM data-access inventory"),
    ("Security", "ASI01 goal hijack, ASI02 tool misuse, ASI05 code execution",
     "Automated-oracle attempts with verbatim evidence + remediation log (stable KES IDs)"),
    ("Safety", "ASI09 human-agent trust, ASI10 rogue agents (approval-gate, kill-switch latency)",
     "Conducted multi-turn sequences + containment profile (approval-gate timing row)"),
    ("Reliability", "ASI08 cascading failures, MCP drift (supply-chain runtime class)",
     "Cascade chain-search + drift radar stability rows + retest certificates"),
    ("Accountability", "evidence chain, named testers, dated scope",
     "Verifiable Evidence Capsule (re-computable by the auditor) + attestation letter"),
    ("Societal risks", "out of a red-team engagement's scope",
     "stated as NOT covered — the client's own governance evidence fills this pillar"),
)

DISCLAIMER = (
    "AIUC-1 certificates are issued by AIUC through accredited auditors. This pack is mapped "
    "evidence for a submission, not a certification: Kessler does not certify, accredit, or "
    "decide AIUC-1 conformance, and no accredited body certifies against OWASP ASI01-ASI10. "
    "The pillar mapping is to control TERRITORY described in public sources, not to numbered "
    "requirements (the full standard text is not held)."
)


def build_pack(engagement, *, quarter: str, corpus_hash: str, method_version: str,
                previous_ref: str = "", retest_status: str = "") -> dict:
    asr = compute_asr(engagement.attempts)
    doc = {
        "schema": PACK_SCHEMA,
        "quarter": quarter,
        "engagement_ref": engagement.ref,
        "client": engagement.client,
        "window": {"start": engagement.start, "end": engagement.end},
        "prepared": date.today().isoformat(),
        "issuer": "Kessler (AtlasNex)",
        "method": {"corpus_hash": corpus_hash, "method_version": method_version,
                   "unit": "composed corpus cases (automated-oracle subset where scored)"},
        "measurement": {
            cid: {k: asr[cid][k] for k in ("attempts", "successes", "asr", "ci_low", "ci_high")}
            for cid in asr if cid != "__overall__" and asr[cid]["attempts"]
        },
        "overall": {k: asr["__overall__"][k] for k in
                    ("attempts", "successes", "asr", "ci_low", "ci_high")},
        "findings_count": len(engagement.findings),
        "retest": {
            "performed": engagement.retest is not None,
            "previous_ref": previous_ref,
            "status_note": retest_status or ("retest run recorded in the document"
                                             if engagement.retest is not None
                                             else "no retest block in this quarter's document"),
        },
        "pillars": [
            {"pillar": p, "kessler_evidence": "mapped to: " + m, "artifact": a}
            for p, m, a in PILLAR_MAP
        ],
        "disclaimer": DISCLAIMER,
    }
    # the pack must satisfy its own anti-certification lint: the ONLY trigger-word sentence
    # allowed is the DISCLAIMER, and it is removed before the scan (the exemption the lint
    # itself documents - a paraphrase of the denial would still trip, by design)
    scan = " ".join(str(v) for v in doc.values()).replace(DISCLAIMER, "")
    problems = lint_prose(scan)
    if problems:
        raise ValueError(f"AIUC pack carries certification language: {problems[0]}")
    return doc


def render_pack_md(pack: dict) -> str:
    lines = [
        f"# Quarterly evidence pack (AIUC-1 territory) — {pack['client']}",
        "",
        f"**Quarter** {pack['quarter']} · **Engagement** {pack['engagement_ref']} · "
        f"**Window** {pack['window']['start']} to {pack['window']['end']} · "
        f"**Prepared** {pack['prepared']} by {pack['issuer']}",
        "",
        "## Measurement this quarter",
        "",
        "| ASI | Attempts | Successes | ASR | 95% interval |",
        "| --- | --- | --- | --- | --- |",
    ]
    for cid, row in sorted(pack["measurement"].items()):
        lines.append(f"| {cid} | {row['attempts']} | {row['successes']} | {_pct(row['asr'])} | "
                     f"[{row['ci_low'] * 100:.1f}%, {row['ci_high'] * 100:.1f}%] |")
    ov = pack["overall"]
    lines.append(f"| **overall** | {ov['attempts']} | {ov['successes']} | {_pct(ov['asr'])} | "
                 f"{_interval(ov)} |")
    lines += [
        "",
        f"Findings raised: **{pack['findings_count']}** (stable KES IDs in the remediation "
        f"log). Retest: {pack['retest']['status_note']}"
        + (f" (previous run: {pack['retest']['previous_ref']})."
           if pack["retest"]["previous_ref"] else "."),
        "",
        "## Pillar territory map",
        "",
        "| AIUC-1 pillar | Kessler evidence (mapped) | Artifact |",
        "| --- | --- | --- |",
    ]
    for p in pack["pillars"]:
        lines.append(f"| {p['pillar']} | {p['kessler_evidence']} | {p['artifact']} |")
    lines += ["", "## Limits", "", pack["disclaimer"], ""]
    lines += ["*Every figure above recomputes from the engagement's evidence capsule; the "
              "auditor can check the arithmetic with the open-source kernel.*"]
    return "\n".join(lines)
