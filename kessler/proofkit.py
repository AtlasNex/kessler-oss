"""Client-facing proof artefacts (PLAN-v5 Wave 1 + the RFI annex of Wave 2 #16).

One file because they share one reason to exist: every artifact is a render-time transform of
the engagement document — no new measurement code, per the plan's artifact-first rule. The
canonical five artefacts stay in `report.py`; these are the money-shaped extras, shipped by
`kessler proofkit` alongside them.

What lives here:
1. **Coverage heatmap** (#6): per-category x per-channel attempts/hits with the honest join
   story. A scored corpus-case attempt carries its case id in `adapter_ref`
   (`runner:KC-xxxx:target`); the case -> (category, behaviour, channel) mapping comes from
   recomposing the SAME corpus. Rows that are not corpus-case attempts (technique-unit runs,
   scanner adapters) are counted as unrecorded — never guessed into a cell.
2. **Named-chain executive summary + board one-pager** (#4): business language, worst chain,
   retest window. Pure render.
3. **Retest certificate** (#1): the SOC-2-rejection-killer artifact. Renders ONLY from a real
   retest block; without one it raises — the certificate is a fact, not a formality.
4. **Underwriter evidence pack** (#5): the four documents underwriters ask for, bundled, plus
   the eight-component map (19e §4.1), capability-aware: rows we do not perform say so.
5. **OWASP GenAI VEC v1.0 procurement checklist** (#8): honest YES/PARTIAL/N/A claim list.
6. **RFI response annex** (Wave 2 #16, 19e §5.1): the evidence-for-a-regulator export.
7. **Remediation tracking log** (#3): CSV + HTML keyed by stable KES IDs (D-025) — never
   renumbered, merged with the client's own tracker state.

All stdlib (C-2). No hand-typed numbers anywhere: every rate is computed from the rows.
"""
from __future__ import annotations

import csv
import io
from datetime import date, timedelta

from .asi import ALL_IDS, compute_asr, retest_delta
from .report import _interval, _pct, _SEVERITY_RANK

#: Behaviour families collapse the 600+ behaviour ids into the columns a client can read.
#: A behaviour id not matching any prefix lands in "Other" — counted, never dropped.
BEHAVIOUR_FAMILIES: tuple[tuple[str, str], ...] = (
    ("goal", "Goal steering"),
    ("tool", "Tool abuse"),
    ("cred", "Credential & identity"),
    ("supply", "Supply chain"),
    ("exec", "Code execution"),
    ("memory", "Memory & context"),
    ("agent", "Inter-agent / cascade"),
    ("human", "Human trust"),
    ("monitor", "Monitoring & kill-switch"),
    ("exfil", "Exfiltration"),
    ("persist", "Persistence"),
)


def _behaviour_family(behavior_id: str) -> str:
    bid = (behavior_id or "").lower()
    for prefix, label in BEHAVIOUR_FAMILIES:
        if bid.startswith(prefix) or f"-{prefix}-" in bid or bid.startswith(f"{prefix}_"):
            return label
    return "Other"


def _md_escape(text: str) -> str:
    return (text or "").replace("|", "\\|").replace("\n", " ")


def corpus_case_index() -> dict[str, dict]:
    """case id -> {category, technique, behavior, channel, behavior_family}, from the live corpus."""
    from .corpus import build

    cases, _, _ = build()
    return {
        c.id: {"category": c.category, "technique": c.technique_id,
               "behavior": c.behavior_id, "channel": c.channel_id,
               "behavior_family": _behaviour_family(c.behavior_id)}
        for c in cases
    }


def heatmap_grid(engagement) -> dict:
    """Per (category x family x channel) cell: attempts/hits. The join is honest by
    construction: unrecorded rows are COUNTED as unrecorded, never dropped or guessed."""
    index = corpus_case_index()
    cells: dict[tuple, dict] = {}
    joined = missed = 0
    for a in engagement.attempts:
        case_id = a.adapter_ref.split(":")[1] if a.adapter_ref.startswith("runner:KC-") else None
        info = index.get(case_id) if case_id else None
        if info is None:
            missed += 1
            continue
        joined += 1
        key = (info["category"], info["behavior_family"], info["channel"])
        cell = cells.setdefault(key, {"attempts": 0, "hits": 0})
        cell["attempts"] += 1
        cell["hits"] += 1 if a.succeeded else 0
    return {
        "categories": [c for c in ALL_IDS if any(k[0] == c for k in cells)],
        "families": sorted({k[1] for k in cells}),
        "channels": sorted({k[2] for k in cells}),
        "cells": {f"{k[0]}|{k[1]}|{k[2]}": v for k, v in sorted(cells.items())},
        "joined": joined,
        "unrecorded": missed,
        "corpus_total": len(index),
    }


def render_heatmap_md(engagement) -> str:
    """One row per category, columns per channel, cell = hits/attempts with an unweighted cell
    rate. The Overall ASR column comes from compute_asr (the spine), so the table can never
    disagree with the ASR table."""
    grid = heatmap_grid(engagement)
    asr = compute_asr(engagement.attempts)
    channels = grid["channels"]
    lines = [
        f"**Join coverage:** {grid['joined']} of {grid['joined'] + grid['unrecorded']} recorded "
        "attempts carry a corpus-case identity (technique-unit runs and scanner adapters do "
        "not; they are counted in the ASR table, not guessed into cells here). Cell rates are "
        "unweighted per-cell; the run's rates are the ASR table's, always.",
        "",
        "| ASI category | " + " | ".join(channels) + " | Overall ASR |",
        "| --- | " + " | ".join("---" for _ in channels) + " | --- |",
    ]
    for cid in grid["categories"]:
        row = [f"**{cid}**"]
        for ch in channels:
            n = s = 0
            for fam in grid["families"]:
                c = grid["cells"].get(f"{cid}|{fam}|{ch}")
                if c:
                    n += c["attempts"]
                    s += c["hits"]
            row.append(f"{s}/{n} ({s / n * 100:.0f}%)" if n else "·")
        ov = asr[cid]
        row.append(f"{_pct(ov['asr'])} {_interval(ov)}" if ov["attempts"] else "—")
        lines.append("| " + " | ".join(row) + " |")
    lines += [
        "",
        f"Corpus composed: **{grid['corpus_total']:,} test cases** across the delivery channels "
        "above (the corpus is the menu; this run's sampled denominator is the ASR table's).",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------- chain summary

def render_chain_summary(engagement, *, retest_due: str = "",
                         previous_ref: str = "") -> str:
    """The named-chain executive summary + board one-pager (#4): business language, worst
    chain, what changed, next steps. Renders from the document, never from memory."""
    asr = compute_asr(engagement.attempts)
    ov = asr["__overall__"]
    ranked = sorted(engagement.findings, key=lambda f: _SEVERITY_RANK[f.severity])
    chains = [f for f in ranked if f.chained_with]
    worst = chains[0] if chains else (ranked[0] if ranked else None)

    lines = [
        f"# Board summary — {engagement.client}",
        "",
        f"**Engagement** {engagement.ref} · **Window** {engagement.start} to "
        f"{engagement.end} · **Tester(s)** {', '.join(engagement.testers)}",
        "",
        "## What we did",
        "",
        f"We attacked the {len(engagement.targets)} system(s) in scope the way a real adversary "
        f"would: {ov['attempts']} attempts across the OWASP Agentic risk categories, each "
        "attempt counted and evidenced. Every number below is the share of attacks that "
        "achieved their objective, with the statistical band a measurement this size can "
        "honestly carry.",
    ]
    if ov["attempts"]:
        lines += [
            "",
            "## The headline number",
            "",
            f"**{ov['successes']} of {ov['attempts']} attacks succeeded — {_pct(ov['asr'])} "
            f"(95% band {_interval(ov)}).**",
            "",
            "A rate is not a grade: it says how often the attack worked when we tried it, over "
            "counted attempts. The band is the honesty — 0% on a small sample is not proof of "
            "safety; it means 'we could not make it fail in these tries'.",
        ]
    if worst is not None:
        chain_txt = ""
        if worst.chained_with:
            chain_txt = (
                " On its own this is contained; chained with "
                f"{', '.join(worst.chained_with)} it composes into the path an attacker would "
                "actually take."
            )
        lines += [
            "",
            "## The one thing to brief the board on",
            "",
            f"**{worst.finding_id} — {worst.title}** ({worst.severity.value.upper()}). "
            f"{worst.impact}{chain_txt}",
        ]
    if previous_ref:
        lines += [
            "",
            "## What changed since the last run",
            "",
            f"Baseline run: {previous_ref}. The before/after per-category table is the retest "
            "appendix of the full report; the gate verdict (pass/regression, computed from "
            "interval separation, not points) is in the run record.",
        ]
    due = retest_due or (date.fromisoformat(engagement.end) + timedelta(days=30)).isoformat()
    lines += [
        "",
        "## What happens next",
        "",
        "Remediate the findings in report order, then book the retest: a fix counts as fixed "
        f"only when the re-run's interval separates from the baseline's. **Retest window opens "
        f"{due}** (30 days from window end; the retest lane ships with this engagement).",
        "",
        "*Mapped to the OWASP Top 10 for Agentic Applications (ASI01-ASI10). No accredited body "
        "certifies against this framework; nothing here is a certification or a verdict of "
        "safety.*",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------- retest certificate

def _delta_interval(d: dict) -> dict:
    """Adapt a retest_delta row to the {ci_low, ci_high} shape _interval renders."""
    return {"ci_low": d.get("after_ci_low"), "ci_high": d.get("after_ci_high")}


def render_retest_certificate(engagement, *, issued: str, retest_window: str) -> str:
    """The retest certificate (Wave 1 #1) — the artifact whose absence is a top SOC 2
    evidence-rejection cause (19e checklist rows 1 + 11).

    Stable KES IDs, original-vs-retest ASR with Wilson intervals, dates, the named tester.
    Every figure comes from `retest_delta` — a render, not a second measurement. Without a
    retest block this RAISES: the certificate is a fact, never a formality.
    """
    if engagement.retest is None:
        raise ValueError(
            "a retest certificate without a retest block would certify a comparison that never "
            "happened — record the retest run first (`kessler run` against the same scope)"
        )
    delta = retest_delta(engagement.attempts, engagement.retest["attempts"])
    by_cat: dict[str, list] = {}
    for f in engagement.findings:
        by_cat.setdefault(f.category, []).append(f)

    lines = [
        "# Retest certificate",
        "",
        f"**Engagement:** {engagement.ref} · **Client:** {engagement.client}",
        f"**Original window:** {engagement.start} to {engagement.end}",
        f"**Retest window:** {retest_window}",
        f"**Issued:** {issued}",
        f"**Tester(s) of record:** {', '.join(engagement.testers)}",
        f"**Scope document:** signed, SHA-256 `{engagement.scope_sha256}`",
        "",
        "## Per-category outcome (computed; the interval decides)",
        "",
        "| Category | Findings (KES) | Original | Retest | Delta | Fix demonstrated? |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for cid, d in delta.items():
        if cid == "__overall__" or not (d["before_attempts"] or d["after_attempts"]):
            continue
        fids = ", ".join(f.finding_id for f in by_cat.get(cid, [])) or "—"
        after = (f"{d['after_attempts']} / {_pct(d['after_asr'])} {_interval(_delta_interval(d))}"
                 if d["after_attempts"] else "— not retested")
        if d["fix_demonstrated"]:
            verdict = "yes — intervals separate"
        elif d.get("rate_reduced"):
            verdict = "rate down, **not demonstrated**"
        else:
            verdict = "**not demonstrated**"
        dt = "n/a" if d["delta"] is None else f"{d['delta'] * 100:+.1f} pp"
        lines.append(f"| {cid} | {fids} | {d['before_attempts']} / {_pct(d['before_asr'])} | "
                     f"{after} | {dt} | {verdict} |")
    ov = delta["__overall__"]
    ov_dt = "n/a" if ov["delta"] is None else f"{ov['delta'] * 100:+.1f} pp"
    n_findings = sum(len(v) for v in by_cat.values())
    verdict_ov = ("yes — intervals separate" if ov["fix_demonstrated"]
                  else "not demonstrated at the overall level")
    lines.append(
        f"| **overall** | {n_findings} finding(s) | "
        f"{ov['before_attempts']} / {_pct(ov['before_asr'])} | "
        f"{ov['after_attempts']} / {_pct(ov['after_asr'])} | {ov_dt} | {verdict_ov} |"
    )
    gaps = ov["untested_success_categories"]
    if gaps:
        lines += ["", f"**Retest gap:** baseline successes on {', '.join(gaps)} were not "
                      "retested; the overall row cannot claim the estate was fixed. "
                      "Per-category rows stand."]
    lines += [
        "",
        "## What this certificate is",
        "",
        "A dated record that a retest run happened against the same scope, with its intervalled "
        "rates on both sides. A fix counts as *demonstrated* only when the after-run's 95% "
        "interval sits wholly below the baseline's — a lower point estimate whose intervals "
        "overlap is recorded, honestly, as not demonstrated. This is measurement, not "
        "certification: no accredited body certifies against OWASP ASI01-ASI10, and nothing "
        "here asserts the system is secure.",
        "",
        "*Mapped to OWASP ASI01-ASI10 · generated by Kessler from the engagement document "
        "(regenerating is a re-run, not a rewrite).*",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------- underwriter pack

#: The eight-component underwriting package (19e §4.1, verified public sources) mapped to what
#: a Kessler engagement actually ships. Capability-aware: rows the practice does not perform
#: say so and name who does, instead of pretending.
_UW_MAP: tuple[tuple[str, str, str], ...] = (
    ("1. Adversarial-testing report (methodology, findings, risk ratings, remediation status)",
     "SHIPS", "report.md + coverage.md; ASR per category with 95% Wilson intervals; the KES "
              "finding contract (CVSS v4 structural, C-I-A impact, three-part remediation)"),
    ("2. Model/agent inventory with data-access scope and decision authority",
     "SHIPS", "aibom.json (CycloneDX 1.6) + blast-radius analysis (the reach union per agent)"),
    ("3. Written scope-constraint / autonomy-envelope statement",
     "SHIPS", "the signed scope document (its SHA-256 is printed on every artefact) + the "
              "blast-radius measurement behind it"),
    ("4. Audit telemetry — tamper-evident inputs/decisions/outputs",
     "PARTIAL", "the attempt ledger is evidence-gated (C-1) and hash-chainable via the "
                "Verifiable Evidence Capsule; ≥90-day production log retention is the CLIENT's "
                "own system — we attest to testing evidence, not to their log retention"),
    ("5. Incident history + remediation record",
     "PARTIAL", "the remediation-tracking log (stable KES IDs) ships; the incident register "
                "itself is the client's system of record"),
    ("6. Framework alignment mapping (NIST AI RMF / ISO 42001)",
     "SHIPS", "`kessler bundle` annexes + crosswalk — alignment documents, never certificates"),
    ("7. EU AI Act technical documentation (Arts 11/53/55 set)",
     "PARTIAL", "the Art 55 assessment annex (R3.1) + the RFI Response Annex; the full "
                "technical documentation set is the provider's obligation"),
    ("8. CRA incident/vulnerability reporting readiness",
     "NOT PERFORMED", "registration, 24h/72h clocks and severity classification are the "
                      "manufacturer's duty; outside a red-team engagement's scope"),
)

_UW_DISCLAIMER = (
    "No accredited body certifies against OWASP ASI01-ASI10; nothing in this pack is a "
    "certification. EU AI Act operator-breach exposure is Art 99(4) (EUR 15M or 3% of global "
    "turnover, whichever is higher); Art 99(3) (EUR 35M or 7%) applies to prohibited practices "
    "only. MITRE ATLAS has no Lateral Movement or Command-and-Control tactics; findings in "
    "categories with no ATLAS home are stated as outside ATLAS's current taxonomy."
)


def render_underwriter_pack(engagement, *, retest_window: str, verify_url: str = "") -> str:
    """The underwriter evidence pack (Wave 1 #5): the four documents underwriters ask for,
    bundled, plus the eight-component map. Renders from the engagement document."""
    asr = compute_asr(engagement.attempts)
    ov = asr["__overall__"]
    by_sev: dict[str, int] = {}
    for f in engagement.findings:
        by_sev[f.severity.value] = by_sev.get(f.severity.value, 0) + 1
    sev_summary = ", ".join(f"{n} {s}" for s, n in sorted(by_sev.items())) or "none raised"
    lines = [
        "# Underwriter evidence pack",
        "",
        f"**Insured:** {engagement.client} · **Engagement:** {engagement.ref} · "
        f"**Testing window:** {engagement.start} to {engagement.end}",
        f"**Retest window:** {retest_window}",
        f"**Scope document:** signed, SHA-256 `{engagement.scope_sha256}`",
    ]
    if verify_url:
        lines.append(f"**Verify this evidence:** {verify_url}")
    lines += [
        "",
        "## 1. The four documents underwriters ask for",
        "",
        "| Document | Status | Where |",
        "| --- | --- | --- |",
        "| Completion letter | included | `attestation-letter.md` (this pack's sibling) |",
        "| Scope statement | included | signed scope document, SHA-256 above |",
        f"| Remediation status by severity | {sev_summary} | remediation-tracking log "
        "(`kessler proofkit`) |",
        f"| Retest date | {retest_window} | retest certificate (this pack's sibling) |",
        "",
        "## 2. The measurement, in the underwriter's grammar",
        "",
        f"Overall attack success: **{ov['successes']} of {ov['attempts']} attempts, "
        f"{_pct(ov['asr'])} (95% Wilson interval {_interval(ov)})**, mapped to OWASP "
        "ASI01-ASI10. A rate over counted attempts with its interval is the submission-grade "
        "form: auditable arithmetic, not a verdict, and it ages honestly against a retest.",
        "",
        "## 3. The eight-component package, mapped",
        "",
        "| Component | Kessler ships? | Evidence / gap |",
        "| --- | --- | --- |",
    ]
    for comp, state, detail in _UW_MAP:
        lines.append(f"| {comp} | {state} | {detail} |")
    lines += [
        "",
        "## 4. Reliance and limits",
        "",
        _UW_DISCLAIMER,
        "",
        "This pack is a render-time transform of the engagement document (the Kessler kernel "
        "is open source; every figure recomputes from the evidence). Findings never leave the "
        "client's network except in the report.",
        "",
        "*Sources: 19e §4.1 (SecureTom 8-component package; AgentInsured/Armilla; aiuc-1.com; "
        f"gov.ca.gov SB 813/AB 1405) · generated {date.today().isoformat()} by Kessler.*",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------- VEC checklist

#: The OWASP GenAI Vendor Evaluation Criteria for AI Red-Teaming Providers (Tooling v1.0) —
#: capability-aware claim list for the site's procurement page. Source:
#: https://genai.owasp.org/resource/owasp-vendor-evaluation-criteria-for-ai-red-teaming-providers-tooling-v1-0/
#: Statuses are claims with named evidence, not a score: YES = shipped and test-pinned;
#: PARTIAL = shipped with a stated boundary; N/A = not applicable to a services-first practice.
VEC_V10: tuple[tuple[str, str, str], ...] = (
    ("Transparent methodology", "YES",
     "methodology page + versioned method strings on every artefact; intervals printed beside "
     "every rate"),
    ("Evidence behind claims", "YES",
     "C-1: an unevidenced success cannot be constructed or loaded, enforced in the open-source "
     "kernel"),
    ("Reproducible runs", "YES",
     "one engagement document; regenerating any artefact is a re-run, not a rewrite"),
    ("Tool-call replay / agent-trace logging", "PARTIAL",
     "transcripts ride verbatim in attempt evidence and are hash-chained by the capsule; a "
     "per-finding replay bundle is on the roadmap"),
    ("Raw evidence supports all claims", "YES",
     "the evidence block IS the claim's source text"),
    ("Tester-action vs model-behaviour separation", "YES",
     "adapters map scanner verdicts through the polarity kernel; the kernel records attempts, "
     "not opinions"),
    ("Third-party-verifiable numbers", "YES",
     "Verifiable Evidence Capsule: hash-chained evidence, anchored head, OSS recompute"),
    ("Independent benchmark participation", "N/A",
     "we publish our own baseline register (preregistered N floors); we do not enter vendor "
     "leaderboards"),
    ("Incident-response support", "PARTIAL",
     "48h critical-response expectation in every SOW; no 24/7 contractual SLA — stated on the "
     "quote"),
    ("Client data handling", "YES",
     "findings never leave the client's network except the report; CVD discipline for anything "
     "discovered in public systems"),
    ("Insurance / liability posture", "PARTIAL",
     "T1 platform and T4 sub-contract lanes carry their paper; direct enterprise cover waits "
     "on the broker's written answer (never claimed before it exists)"),
    ("Certification claims", "N/A",
     "no accredited body certifies against ASI01-ASI10; we map, never certify — stated on "
     "every artefact"),
)


def render_vec_checklist() -> str:
    rows = "\n".join(f"| {c} | {s} | {d} |" for c, s, d in VEC_V10)
    return (
        "| Vendor-evaluation criterion (OWASP GenAI VEC v1.0) | Status | Where it holds, or why it does not apply |\n"
        "| --- | --- | --- |\n" + rows + "\n\n"
        "YES = shipped and pinned by the open test suite; PARTIAL = shipped with a stated "
        "boundary; N/A = not applicable to a services-first practice. Source: [OWASP GenAI VEC "
        "v1.0 (tooling)](https://genai.owasp.org/resource/owasp-vendor-evaluation-criteria-for-ai-red-teaming-providers-tooling-v1-0/)."
    )


# --------------------------------------------------------------------------- RFI annex (#16)

def render_rfi_annex(engagement) -> str:
    """The Art 91 RFI-response annex (Wave 2 #16, 19e §5.1): evidence you can hand a regulator.
    Methodology, N, intervals, findings register, remediation status — from the document."""
    asr = compute_asr(engagement.attempts)
    lines = [
        "# RFI response annex — adversarial-testing evidence",
        "",
        f"**Provider:** {engagement.client} · **Engagement:** {engagement.ref} · "
        f"**Window:** {engagement.start} to {engagement.end}",
        f"**Scope document:** signed, SHA-256 `{engagement.scope_sha256}`",
        "",
        "**Method.** Adversarial testing of agentic AI mapped to OWASP ASI01-ASI10, reported "
        "as attack-success rates over counted attempts with 95% Wilson intervals; every "
        "recorded success carries the verbatim observation that demonstrates it. The kernel is "
        "open source (Apache-2.0); these figures recompute from the evidence.",
        "",
        "## Category measurement",
        "",
        "| ASI | Attempts | Successes | ASR | 95% interval |",
        "| --- | --- | --- | --- | --- |",
    ]
    for cid, row in asr.items():
        if cid == "__overall__" or not row["attempts"]:
            continue
        lines.append(f"| {cid} | {row['attempts']} | {row['successes']} | {_pct(row['asr'])} | "
                     f"{_interval(row)} |")
    ov = asr["__overall__"]
    lines.append(f"| **overall** | {ov['attempts']} | {ov['successes']} | {_pct(ov['asr'])} | "
                 f"{_interval(ov)} |")
    lines += [
        "",
        "## Findings register",
        "",
        "| KES ID | Category | Severity | Title |",
        "| --- | --- | --- | --- |",
    ]
    for f in sorted(engagement.findings, key=lambda f: _SEVERITY_RANK[f.severity]):
        lines.append(f"| {f.finding_id} | {f.category} | {f.severity.value.upper()} | "
                     f"{_md_escape(f.title)} |")
    if not engagement.findings:
        lines.append("| — | — | — | no findings raised; the rates above are the result |")
    lines += [
        "",
        "## Remediation status",
        "",
        "Tracked by stable KES ID in the remediation log (`kessler proofkit`); a fix counts as "
        "demonstrated only when a retest interval separates from the baseline's.",
        "",
        "## Limits (stated, because an RFI answer is itself finable)",
        "",
        _UW_DISCLAIMER,
        "",
        "This annex attests to testing performed over the stated window and scope. It is not a "
        "certification, not a conformity assessment, and not legal advice; the obligations "
        "under the EU AI Act remain the provider's.",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------- remediation log

_CSV_FIELDS = ("finding_id", "title", "category", "severity", "status", "owner", "target_date",
               "fixed_in", "retest_ref", "retest_result", "notes")


def remediation_rows(engagement, *, existing: dict[str, dict] | None = None) -> list[dict]:
    """One row per KES ID, merged with any previously tracked state.

    `existing` maps finding_id -> the client/tracker's row (status, owner, dates). KES IDs are
    stable (D-025) and NEVER renumbered: a finding present in both sources keeps the tracker's
    status; a new finding enters as `open`. The CSV is the artifact an auditor diffs.
    """
    existing = existing or {}
    rows = []
    for f in sorted(engagement.findings, key=lambda f: _SEVERITY_RANK[f.severity]):
        prev = existing.get(f.finding_id, {})
        rows.append({
            "finding_id": f.finding_id,
            "title": f.title,
            "category": f.category,
            "severity": f.severity.value,
            "status": prev.get("status", "open"),
            "owner": prev.get("owner", ""),
            "target_date": prev.get("target_date", ""),
            "fixed_in": prev.get("fixed_in", ""),
            "retest_ref": prev.get("retest_ref", ""),
            "retest_result": prev.get("retest_result", ""),
            "notes": prev.get("notes", ""),
        })
    return rows


def render_remediation_csv(engagement, *, existing: dict[str, dict] | None = None) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=_CSV_FIELDS, lineterminator="\n")
    w.writeheader()
    for row in remediation_rows(engagement, existing=existing):
        w.writerow(row)
    return buf.getvalue()


_HTML_ESC = str.maketrans({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"})


def render_remediation_html(engagement, *, existing: dict[str, dict] | None = None) -> str:
    rows = remediation_rows(engagement, existing=existing)
    trs = []
    for r in rows:
        tds = "".join(f"<td>{str(r[k]).translate(_HTML_ESC)}</td>" for k in _CSV_FIELDS)
        trs.append(f"<tr>{tds}</tr>")
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<title>Remediation tracking log — "
        f"{engagement.ref.translate(_HTML_ESC)}</title>"
        "<style>body{font-family:system-ui,sans-serif;margin:24px;color:#111}"
        "table{border-collapse:collapse;width:100%;font-size:.85rem}"
        "th,td{border:1px solid #ccc;padding:6px 9px;text-align:left;vertical-align:top}"
        "th{background:#f4f2ec;font-family:ui-monospace,monospace;font-size:.72rem;"
        "text-transform:uppercase;letter-spacing:.05em}"
        "tr:nth-child(even) td{background:#fafaf7}"
        ".note{color:#555;font-size:.85rem;margin-top:14px}</style></head><body>"
        "<h1>Remediation tracking log</h1>"
        f"<p>Engagement <strong>{engagement.ref.translate(_HTML_ESC)}</strong> — "
        f"{engagement.client.translate(_HTML_ESC)} · window {engagement.start} to "
        f"{engagement.end}</p>"
        "<table><thead><tr>"
        + "".join(f"<th>{k.replace('_', ' ')}</th>" for k in _CSV_FIELDS)
        + "</tr></thead><tbody>" + "".join(trs) + "</tbody></table>"
        "<p class='note'>KES IDs are stable and never renumbered across retests (contract "
        "D-025). Status values are the client's tracker's, merged verbatim; a finding absent "
        "from the tracker renders <em>open</em>. This log is remediation bookkeeping — it is "
        "not a certification, and a fixed row counts as fixed only when a retest run "
        "demonstrates it.</p>"
        "</body></html>"
    )


#: The proof-kit bundle's filenames, in write order (the manifest `kessler proofkit` prints).
PROOFKIT_ARTEFACTS = (
    "board-summary.md", "coverage-heatmap.md", "remediation-log.csv", "remediation-log.html",
    "underwriter-pack.md", "rfi-annex.md",
)


def render_proofkit(engagement, *, existing: dict[str, dict] | None = None,
                    retest_window: str = "", verify_url: str = "",
                    previous_ref: str = "") -> dict[str, str]:
    """Every proof-kit artifact as text, keyed by filename. The retest certificate is NOT in
    this bundle: it renders only from a document carrying a real retest block, via
    `kessler proofkit --certificate` (a certificate of nothing is worse than no certificate)."""
    window = retest_window or (
        date.fromisoformat(engagement.end) + timedelta(days=30)).isoformat()
    return {
        "board-summary.md": render_chain_summary(engagement, retest_due=window,
                                                 previous_ref=previous_ref),
        "coverage-heatmap.md": render_heatmap_md(engagement),
        "remediation-log.csv": render_remediation_csv(engagement, existing=existing),
        "remediation-log.html": render_remediation_html(engagement, existing=existing),
        "underwriter-pack.md": render_underwriter_pack(engagement, retest_window=window,
                                                       verify_url=verify_url),
        "rfi-annex.md": render_rfi_annex(engagement),
    }
