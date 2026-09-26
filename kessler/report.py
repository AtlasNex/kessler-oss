"""The deliverable: five artefacts, each a pure function of one engagement document.

Why this module exists
----------------------
`docs/IMPLEMENTATION-PLAN.md` section 1: regenerating a report after a fix must be a **re-run, not a
rewrite**. That is the largest single labour saving in the practice and the honest commercial
justification for the harness. So nothing here is hand-assembled: every figure comes from
`compute_asr()`, every finding from `Finding.to_markdown()`, every coverage row from `coverage()`.

The five artefacts (A5's definition of done)
--------------------------------------------
| Artefact | What it is |
| --- | --- |
| `report.md` | The 10-section client deliverable, per `docs/REPORT-SPEC.md` |
| `coverage.md` | Every ASI category: tested / excluded-with-reason / missing. No blanks |
| `attestation-letter.md` | The narrow attestation, per `templates/attestation-letter.md` |
| `findings.sarif` | SARIF 2.1.0, so a client can pipe findings into their own tooling |
| `aibom.json` | Inventory of agents, tools, MCP servers and models in scope, plus the gaps |

The gate (C-4)
--------------
`render_all()` calls `lint.assert_emittable()` **first** and raises. A report that claims ten-category
coverage it did not perform is the one failure this project exists to avoid, so the generator has no
override and no draft mode (D-008).

Two honesty properties worth knowing
------------------------------------
1. **Prose is self-checked.** The rendered report is fed back through the linter's prose-ASR rule, so a
   number in the narrative that disagrees with the computed ASR fails the build. The generator cannot
   quietly disagree with itself.
2. **What it could not fill, it says.** Attestation fields the document does not carry (testers, an
   email) stay visibly bracketed, and `unresolved()` lists them. A template silently shipping with
   `[Client legal entity name]` intact would be worse than an error.
"""
from __future__ import annotations

from pathlib import Path

from .asi import Severity, compute_asr, retest_delta
from .lint import assert_emittable, lint

#: Bumped when the rendered shape changes; storygraph compatibility for a client's tooling.
AIBOM_SCHEMA = "kessler/aibom/v1"
SARIF_SCHEMA = (
    "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json"
)
SARIF_VERSION = "2.1.0"
GENERATOR = "Kessler"

#: Severity -> SARIF level. SARIF has three levels; our five-step ladder folds onto them.
#: Every result carries `ai/exploitability` (Microsoft's draft AI-findings profile). Its
#: all-or-nothing rule holds by construction: C-1 guarantees every finding is evidenced, so
#: every result is `demonstrated` — an unevidenced finding cannot be constructed to dilute the run.
#: KES-YYYY-NNN stays the ruleId (D-025: stable IDs across retests); the profile's CWE/NOVEL
#: grammar is a different namespace for AI-generated *code* findings, documented in the run note
#: rather than imported at the cost of the KES contract.
_SARIF_LEVEL = {
    Severity.CRITICAL: "error",
    Severity.HIGH: "error",
    Severity.MEDIUM: "warning",
    Severity.LOW: "note",
    Severity.INFO: "note",
}

#: Worst-first, for ordering findings without relying on enum declaration order.
_SEVERITY_RANK = {
    Severity.CRITICAL: 0, Severity.HIGH: 1, Severity.MEDIUM: 2, Severity.LOW: 3, Severity.INFO: 4,
}

#: The standards section. Static by design: it is a statement of method, not of result, and the
#: honesty constraints in MASTER-PLAN section 1.6 are baked into the wording. Re-pinned Phase 3
#: (PLAN-v4): ATLAS data-format v6 with the Agentic AI platform tag, SAFE-MCP SAFE-T IDs beside
#: the beta MCP Top 10. The single source for this wording is kessler.bundle.STANDARDS_BLOCK_V2 —
#: imported, not copied, so docs, bundle and report cannot drift apart.
from .bundle import STANDARDS_BLOCK_V2 as _STANDARDS  # noqa: E402  (re-pin, Phase 3.1)


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def _interval(row: dict) -> str:
    if row["ci_low"] is None or row["ci_high"] is None:
        return "n/a"
    return f"[{row['ci_low'] * 100:.1f}%, {row['ci_high'] * 100:.1f}%]"


def unresolved(text: str) -> list[str]:
    """Bracketed placeholders still awaiting a human. Reported, never silently filled.

    Matched on an uppercase convention (`[TESTER NAMES]`) rather than any bracket, because the report
    legitimately contains bracketed numbers — a confidence interval renders as `[9.7%, 70.0%]`, and
    flagging those as unfilled placeholders would make this check useless noise.
    """
    import re

    return sorted(set(re.findall(r"\[([A-Z][A-Z0-9 _/&-]{2,60})\]", text)))


def _worst_severity(engagement) -> dict:
    """Worst finding severity per category, for the ASR table's Severity column.

    The report spec (section 4) puts a Severity column in the ASR table, and there is no per-category
    severity in the data — only per-finding. So this derives it: the worst finding on the category, or
    em-dash when the category produced none. Deriving it here, once, keeps the table honest: a
    hand-typed severity could disagree with section 5 and nothing downstream would catch that.
    """
    order = (Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW, Severity.INFO)
    worst: dict[str, Severity] = {}
    for f in engagement.findings:
        cur = worst.get(f.category)
        if cur is None or order.index(f.severity) < order.index(cur):
            worst[f.category] = f.severity
    return worst


def _asr_table(engagement) -> str:
    asr = compute_asr(engagement.attempts)
    tested = {a.category for a in engagement.attempts}
    sev = _worst_severity(engagement)
    lines = [
        "| ASI category | Attempts | Successes | ASR | 95% interval | Severity | Reported? |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for cid in [c for c in asr if c != "__overall__"]:
        row = asr[cid]
        if row["attempts"]:
            state = "yes"
        elif cid in engagement.exclusions:
            state = "excluded, with reason"
        else:
            state = "**unsupported**"
        lines.append(
            f"| {cid} | {row['attempts']} | {row['successes']} | "
            f"{_pct(row['asr']) if row['attempts'] else 'n/a'} | "
            f"{_interval(row)} | {sev[cid].value.upper() if cid in sev else '—'} | {state} |"
        )
    overall = asr["__overall__"]
    order = (Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW, Severity.INFO)
    overall_sev = min(sev.values(), key=order.index).value.upper() if sev else "—"
    lines.append(
        f"| **Overall** | {overall['attempts']} | {overall['successes']} | {_pct(overall['asr'])} | "
        f"{_interval(overall)} | {overall_sev} | yes |"
    )
    lines.append("")
    lines.append(
        "**How to read this table.** An attack-success rate is the proportion of attempts that "
        "achieved the stated effect, over a stated number of attempts, with a 95% Wilson score "
        "interval. The **Severity** column is the worst finding recorded against that category "
        "(section 5), derived from the data rather than hand-typed; an em-dash means no finding was "
        "raised on that category, which is not the same as no risk. A category with attempts but a "
        "rate of 0% is a measurement, not a guarantee: the "
        "interval is the honest part of that statement. A category marked *excluded* was contracted "
        "out of scope with a written reason; a category marked **unsupported** was neither tested nor "
        "excluded, and this report should not have been emitted (see the coverage table)."
    )
    if not tested:
        lines.append("\n> No attempts were recorded. This table is empty by construction, not by finding.")
    return "\n".join(lines)


def _blast_radius(engagement) -> str:
    from .blast import compute_blast_radius, render_blast_radius_md

    return render_blast_radius_md(compute_blast_radius(engagement.targets))


def _chain_narrative(engagement) -> str:
    chained = [(f.category, f.chained_with) for f in engagement.findings if f.chained_with]
    if not chained:
        return (
            "No chained path was demonstrated in this engagement. That is a statement about what was "
            "attempted, not a claim that no chain exists — see the coverage table for what was in and "
            "out of scope."
        )
    out = [
        "The following findings compose. Individually mild issues that compose into a serious outcome "
        "are the reason this section exists: each step was reported separately, and the chain is the "
        "story.\n"
    ]
    for category, with_ in chained:
        out.append(f"- **{category}** chains with **{', '.join(with_)}**")
    return "\n".join(out)


def _retest_appendix(engagement) -> str:
    if engagement.retest is None:
        return "No retest was performed for this engagement, so no before/after comparison is available."
    delta = retest_delta(engagement.attempts, engagement.retest["attempts"])
    lines = [
        "Computed from two runs in the same `Attempt` shape — not hand-written.\n",
        "| ASI category | Before (attempts / ASR) | After (attempts / ASR) | Delta | Fix demonstrated? |",
        "| --- | --- | --- | --- | --- |",
    ]
    for cid, d in delta.items():
        if not d["before_attempts"] and not d["after_attempts"]:
            continue
        name = "**Overall**" if cid == "__overall__" else cid
        delta_text = "n/a" if d["delta"] is None else f"{d['delta'] * 100:+.1f} pp"
        # An em-dash, never 0.0%: a category nobody retested must not read as "retested, all held".
        after = (f"{d['after_attempts']} / {_pct(d['after_asr'])}" if d["after_attempts"]
                 else "— not retested")
        # Three honest states, never two: a demonstrated fix (intervals separate), a rate that
        # fell but with overlapping intervals (real but not yet evidence), or neither.
        if d["fix_demonstrated"]:
            verdict = "yes"
        elif d.get("rate_reduced"):
            verdict = "rate down, **not demonstrated** (intervals overlap)"
        else:
            verdict = "**not demonstrated**"
        lines.append(
            f"| {name} | {d['before_attempts']} / {_pct(d['before_asr'])} | {after} | {delta_text} | "
            f"{verdict} |"
        )
    gaps = delta["__overall__"]["untested_success_categories"]
    lines.append(
        "\nA fix is marked *demonstrated* only when both runs recorded attempts and the after-run's "
        "Wilson interval sits wholly below the baseline's — a lower rate whose intervals still overlap "
        "is recorded as *rate down, not demonstrated*, because on the evidence it could be noise. A "
        "category with no after-run is a gap in evidence, not an improvement."
        + (f"\n\n**Retest gap:** baseline successes on {', '.join(gaps)} were **not retested**, so "
           "the overall row cannot claim the estate was fixed — per-category rows stand, the "
           "aggregate does not." if gaps else "")
    )
    return "\n".join(lines)


def render_report(engagement) -> str:
    """The 10-section deliverable. Fails closed: refuses to render incomplete coverage."""
    assert_emittable(engagement)

    asr = compute_asr(engagement.attempts)
    overall = asr["__overall__"]
    ranked = sorted(engagement.findings, key=lambda f: _SEVERITY_RANK[f.severity])[:3]

    s1 = [
        f"**Client:** {engagement.client}",
        f"**Engagement reference:** {engagement.ref}",
        f"**Testing window:** {engagement.start} to {engagement.end}",
        f"**Scope document:** signed, SHA-256 `{engagement.scope_sha256}`",
        f"**Systems tested:** {len(engagement.targets)} in scope — "
        + (", ".join(t["id"] for t in engagement.targets) if engagement.targets else "none recorded"),
        f"**Methodology:** adversarial testing mapped to OWASP ASI01-ASI10, reported as attack-success "
        f"rates over {overall['attempts']} attempts across {len([1 for c in asr if c != '__overall__' and asr[c]['attempts']])} "
        "categories.",
        "**Testers:** " + (", ".join(engagement.testers) if engagement.testers
                           else "[TESTER NAMES]"),
        "**Versions tested:** " + ("; ".join(
            f"`{t['id']}` {t['version']}" for t in engagement.targets if t.get("version")
        ) or "[VERSIONS NOT RECORDED — fill from the scope document]"),
        "**Report version:** generated from the engagement document; regenerating after a fix is a "
        "re-run, not a rewrite.",
    ]

    s2 = (
        f"Across {overall['attempts']} recorded attempts, the overall attack-success rate was "
        f"**{_pct(overall['asr'])}** (95% interval {_interval(overall)}). "
        f"{overall['successes']} attempt(s) achieved their stated objective.\n\n"
        + (
            ("The three highest-severity findings, in business terms:\n\n" if len(ranked) > 2
             else f"All {len(ranked)} recorded finding(s), worst first, in business terms:\n\n")
            + "\n".join(
                f"{n}. **{f.title}** ({f.category}, {f.severity.value.upper()}) — {f.impact}"
                for n, f in enumerate(ranked, 1)
            )
            + (
                f"\n\n{overall['successes']} attempt(s) succeeded; {len(engagement.findings)} "
                "finding(s) are reported. Every attempt is counted in the ASR table in section 4 "
                "regardless of whether it became a reportable finding — the counts answer different "
                "questions (what worked vs what must be fixed) and may legitimately differ."
                if overall["successes"] != len(engagement.findings) else ""
            )
            + "\n\n**What to fix first:** the highest-severity finding listed above. Remediation "
            "guidance for each is in section 5."
            if ranked
            else "No findings were recorded. The measurement above is the result: what was attempted, "
            "and how often it worked."
        )
    )

    s3 = (
        "**In scope**\n\n"
        + (
            "\n".join(
                f"- `{t['id']}` — {t['kind']}"
                + (f" — reaches {', '.join(t['reaches'])}" if t.get("reaches") else "")
                for t in engagement.targets
            )
            if engagement.targets
            else "- none recorded"
        )
        + "\n\n**Excluded, with reasons**\n\n"
        + (
            "\n".join(f"- **{cid}** — {reason}" for cid, reason in sorted(engagement.exclusions.items()))
            if engagement.exclusions
            else "- nothing was excluded"
        )
        + "\n\n**Standards and frameworks**\n\n"
        + _STANDARDS
        + "\n\n**Approach.** The testing recorded in this engagement combines automated probing with manual "
        "multi-turn adversarial testing against the targets listed above; the specific approach "
        "(black-box / grey-box / white-box) for each target is stated in the signed scope document. "
        "**Standard of evidence:** every reported success carries the observation that demonstrates it; "
        "a success without evidence cannot be recorded (constraint C-1), so the absence of a finding is "
        "not evidence of absence of a flaw.\n\n"
        "**Handling of client data.** As specified in section 6 of the signed scope document: "
        "kept only in the engagement environment, redacted in this report where noted, and "
        "deleted on the schedule stated there."
    )

    sections = [
        ("1. Cover and engagement facts", "\n".join(s1)),
        ("2. Executive summary", s2),
        ("3. Scope and methodology", s3),
        ("4. Attack success rate table", _asr_table(engagement)),
        (
            "5. Findings",
            (
                "\n\n".join(f.to_markdown() for f in
                            sorted(engagement.findings, key=lambda f: _SEVERITY_RANK[f.severity]))
                if engagement.findings
                else "No findings were recorded for this engagement."
            ),
        ),
        ("6. Agentic blast-radius analysis", _blast_radius(engagement)),
        ("7. Chained attack narrative", _chain_narrative(engagement)),
        ("8. AIBOM gap note", render_aibom_gap_note(engagement)),
        ("9. Retest appendix", _retest_appendix(engagement)),
        (
            "10. Attestation letter",
            "Delivered as a separate signed artefact, `attestation-letter.md`, so it can be filed "
            "without the rest of this report.",
        ),
    ]

    head = [
        f"# Adversarial testing report — {engagement.client}",
        "",
        f"*Engagement {engagement.ref} · {engagement.start} to {engagement.end} · "
        "generated by Kessler*",
        "",
        "---",
        "",
    ]
    body: list[str] = []
    for title, content in sections:
        body += [f"## {title}", "", content, "", "---", ""]
    return "\n".join(head + body)


def render_coverage(engagement) -> str:
    """The coverage table as its own artefact. Every category present. No blanks."""
    assert_emittable(engagement)   # the coverage artefact is not exempt from C-4 (review F-9)
    rows = engagement.coverage()
    lines = [
        f"# Coverage — {engagement.ref}",
        "",
        "Every OWASP Agentic category is accounted for. A category is *tested*, *excluded* with a "
        "written reason, or **missing** — and a missing category blocks the report (C-4).",
        "",
        "| ASI category | Name | Status | Reason |",
        "| --- | --- | --- | --- |",
    ]
    for r in rows:
        reason = r["reason"] or ("—" if r["status"] == "tested" else "**NO REASON RECORDED**")
        lines.append(f"| {r['category']} | {r['name']} | {r['status']} | {reason} |")
    tested = sum(1 for r in rows if r["status"] == "tested")
    lines += [
        "",
        f"**{tested} of {len(rows)}** categories tested; "
        f"**{sum(1 for r in rows if r['status'] == 'excluded')}** excluded with a reason; "
        f"**{sum(1 for r in rows if r['status'] == 'missing')}** missing.",
        "",
        "*A category being excluded is not a finding about that category. This table states the "
        "denominator so the reader can judge the coverage, which is why it is published rather than "
        "summarised.*",
    ]
    return "\n".join(lines)


def render_attestation(engagement) -> str:
    """The narrow attestation. Scope-only wording; overclaiming here is the mistake that ends a practice."""
    retest_line = (
        "Findings remediated by the client were retested; before and after attack success rates are "
        "recorded in the report appendix."
        if engagement.retest is not None
        else "No retest was performed in this engagement."
    )
    return f"""# Attestation Letter

[CLIENT LEGAL ENTITY NAME]
[CLIENT ADDRESS]

**Date:** [DATE]
**Engagement reference:** {engagement.ref}
**Scope document:** signed, SHA-256 `{engagement.scope_sha256}`

## Subject: attestation of adversarial testing performed

To whom it may concern,

Kessler (AtlasNex) was engaged by the client to perform adversarial security testing of the AI agent
systems enumerated in the scope document referenced above.

**Testing was performed between {engagement.start} and {engagement.end}** by
{", ".join(engagement.testers) if engagement.testers else "[TESTER NAMES]"}, limited to the systems,
environments and testing windows listed in that document.

**Method.** The engagement followed the OWASP Top 10 for Agentic Applications (ASI01-ASI10). Each
category was tested, or excluded with a recorded reason. Testing combined automated probing with manual
multi-turn adversarial testing. Results are reported as attack-success rates over a stated number of
attempts per category.

**Specifically, this attestation covers:**

- the systems listed in the scope document, and no others;
- the testing period stated above;
- adversarial testing against the OWASP Agentic risk categories as scoped: every one of the ten
  categories was either tested or formally excluded with a written reason, exactly as the coverage
  table in the report records. Excluded categories were **not** tested.

**This attestation does not:**

- certify that the systems tested are secure, or that no vulnerabilities remain — the method measures
  what was attempted and cannot establish the absence of all flaws;
- attest that the client meets the EU AI Act, NIST AI RMF, ISO/IEC 42001, SOC 2, DORA, DPDP or any
  other framework in whole. Adversarial testing is one input to those obligations, which remain the
  responsibility of the client;
- constitute a certification, an accreditation, or legal or regulatory advice.

**Retest.** {retest_line}

Signed,

**AtlasNex**
security@atlasnex.com
"""


def render_sarif(engagement) -> dict:
    """SARIF 2.1.0 with Microsoft's draft AI-findings profile (PLAN-v4 Phase 2.3).

    Lets a client pipe findings into their own tooling. Profile mapping, from the profile's own
    doc (microsoft/sarif-sdk docs/ai/generating-sarif.md, draft):
      * `ai/origin: "generated"` on run.properties — the analysis engine is our harness, so the
        findings are AI-involved detections (not `annotated` enrichment of another tool's run);
      * `ai/exploitability: "demonstrated"` on EVERY result — the profile's all-or-nothing rule
        is satisfied by construction because C-1 refuses unevidenced findings at construction;
      * run-level honesty note carried in properties (this is not a certification).
    """
    results = []
    for f in sorted(engagement.findings, key=lambda f: _SEVERITY_RANK[f.severity]):
        results.append({
            "ruleId": f.finding_id or f.category,
            "level": _SARIF_LEVEL[f.severity],
            "message": {"text": f"{f.title} — {f.impact}"},
            "properties": {
                "findingId": f.finding_id,
                "severity": f.severity.value,
                "ai/exploitability": "demonstrated",
                "evidence": f.evidence,
                "reproduction": f.reproduction,
                "threatScenario": f.threat_scenario,
                "impactAnalysis": dict(f.impact_analysis),
                "cvssV4": f.cvss_v4_vector,
                "remediation": {
                    "architectural_fix": f.remediation_architectural_fix,
                    "guardrail_config": f.remediation_guardrail_config,
                    "code_patch": f.remediation_code_patch,
                },
                "chainedWith": list(f.chained_with),
            },
        })
    return {
        "$schema": SARIF_SCHEMA,
        "version": SARIF_VERSION,
        "runs": [{
            "tool": {"driver": {
                "name": GENERATOR,
                "informationUri": "https://github.com/AtlasNex/kessler",
                "rules": [{"id": c} for c in sorted({f.category for f in engagement.findings})],
            }},
            "properties": {
                "ai/origin": "generated",
                "engagement": engagement.ref,
                "scope_sha256": engagement.scope_sha256,
                "note": (
                    "Findings are mapped to OWASP ASI01-ASI10. No accredited certification body exists "
                    "for this framework; these results are not a certification. Every result carries "
                    "ai/exploitability=demonstrated: the profile's C-1 rule — an unevidenced success "
                    "cannot be constructed or loaded — is enforced upstream of this export."
                ),
            },
            "results": results,
        }],
    }


#: The AIBOM artefact is CycloneDX-1.6-compatible JSON (PLAN-v3 3.1): bomFormat/specVersion/
#: components per the CycloneDX spec (required: bomFormat, specVersion; component: type, name),
#: with Kessler-specific semantics carried in the spec's own `properties` extension mechanism —
#: reach strings and inventory gaps. Verified structurally by tests (a JSON Schema lib would
#: break C-2). The kessler/aibom/v2 stamp remains for our own consumers to pin against.
AIBOM_SCHEMA = "kessler/aibom/v2"
_CYCLONEDDX_SPEC_VERSION = "1.6"

#: Scope target kind -> CycloneDX component type (spec enum, bom-1.6.schema.json).
#: platform is for RUNTIMES (Python, Node) per the spec's own definition — an MCP server is an
#: application that happens to serve tools; the kessler:kind property carries the distinction
#: (swarm-batch-3 correction, 23 Sep).
_AIBOM_KIND_TO_TYPE = {
    "agent": "application",
    "mcp_server": "application",
    "tool": "application",
    "memory": "data",
    "model": "machine-learning-model",
}


def aibom_gaps(engagement) -> list[str]:
    """Inventory gaps: a component kind absent from scope is itself worth telling the client."""
    kinds_present = {t["kind"] for t in engagement.targets}
    return [f"no {kind} inventory recorded in scope" for kind in
            ("agent", "mcp_server", "tool", "memory", "model") if kind not in kinds_present]


def render_aibom(engagement) -> dict:
    """The machine-readable AI-BOM: CycloneDX 1.6-compatible, gaps as `kessler:gap` properties."""
    components = []
    for t in engagement.targets:
        props = [{"name": "kessler:kind", "value": t["kind"]}]
        props += [{"name": "kessler:reach", "value": r} for r in (t.get("reaches") or [])]
        components.append({
            "type": _AIBOM_KIND_TO_TYPE[t["kind"]],
            "name": t["id"],
            "version": t.get("version", ""),
            "description": t.get("notes", ""),
            "properties": props,
        })
    bom = {
        "bomFormat": "CycloneDX",
        "specVersion": _CYCLONEDDX_SPEC_VERSION,
        # RFC-4122 serial: CycloneDX recommends it and consumer tooling dedupes on it. Fresh
        # per render is correct here — a re-render IS a new document (C-9: nothing retrochanges).
        "serialNumber": "urn:uuid:" + str(__import__("uuid").uuid4()),
        "version": 1,
        "metadata": {
            "timestamp": __import__("datetime").datetime.now(
                __import__("datetime").timezone.utc).isoformat(timespec="seconds"),
            "tools": [{"vendor": "Kessler (AtlasNex)", "name": "kessler", "version": "1"}],
            "component": {"type": "application", "name": engagement.ref},
        },
        "components": components,
        # CycloneDX JSON forbids extra top-level keys, so our own stamp and the gaps ride in
        # the spec's properties extension. scope_sha256: the hash of the signed scope that
        # bounds this inventory (the document stays re-derivable from its authorisation).
        "properties": [
            {"name": "kessler:schema", "value": AIBOM_SCHEMA},
            {"name": "kessler:engagement", "value": engagement.ref},
            {"name": "kessler:scope_sha256", "value": engagement.scope_sha256},
        ] + [{"name": "kessler:gap", "value": g} for g in aibom_gaps(engagement)],
    }
    return bom


def render_aibom_gap_note(engagement) -> str:
    """Section 8's prose. The absence of an inventory is itself a finding."""
    components = [
        {"id": t["id"], "kind": t["kind"], "version": t.get("version", ""),
         "notes": t.get("notes", "")} for t in engagement.targets
    ]
    lines = [f"**{len(components)} component(s) recorded in scope** "
             "(CycloneDX 1.6 — see `aibom.json`):", ""]
    lines += [f"- `{c['id']}` — {c['kind']}"
                + (f" — version {c['version']}" if c.get("version") else "")
              for c in components] or ["- none recorded"]
    gaps = aibom_gaps(engagement)
    if gaps:
        lines += ["", "**Gaps an auditor will ask about:**", ""]
        lines += [f"- {g}" for g in gaps]
        lines += [
            "",
            "*An AIBOM is emerging as an expected artefact under the EU AI Act and ISO/IEC 42001. Where "
            "no inventory exists, that absence is recorded here as a gap rather than passed over — it "
            "is usually the fastest thing the client can fix.*",
        ]
    else:
        lines += ["", "No inventory gaps: every component kind is represented in scope."]
    return "\n".join(lines)


def render_all(engagement) -> dict[str, str]:
    """Every artefact, as text, keyed by filename. The C-4 gate runs first and raises."""
    assert_emittable(engagement)
    import json

    return {
        "report.md": render_report(engagement),
        "coverage.md": render_coverage(engagement),
        "attestation-letter.md": render_attestation(engagement),
        "findings.sarif": json.dumps(render_sarif(engagement), indent=2) + "\n",
        "aibom.json": json.dumps(render_aibom(engagement), indent=2) + "\n",
    }


def write_all(engagement, outdir) -> list[Path]:
    """Write every artefact to `outdir`. Returns the paths, so a caller never assumes success."""
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for name, text in render_all(engagement).items():
        p = out / name
        p.write_text(text, encoding="utf-8")
        written.append(p)
    return written


def self_check(engagement) -> list:
    """Lint the generated report's own prose against the computed numbers.

    The generator must not be able to disagree with itself: if a figure in the narrative does not match
    the data, this returns the blocker rather than the prose shipping.
    """
    report = render_report(engagement)
    return lint(engagement, prose=report)
