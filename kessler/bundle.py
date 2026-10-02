"""Compliance evidence bundle (PLAN-v4 Phase 3.2) — EU AI Act Art 55 / ISO 42001 / NIST AI RMF.

Why this module exists
----------------------
Enterprise procurement "gates on these frameworks by name" (ZIRAN issue #289, verified); a
competitor sells attestation-style bundles at $6,000/framework; the kernel already holds every
input (attempts, coverage, AIBOM, testers, window). The bundle is a render-time transform of the
engagement document — no new measurement code — with ONE wording locked forever (the honesty rule):

    "This bundle attests to testing performed, not that the system meets the framework."

The locked sentence appears verbatim on the cover page, and `lint_prose()` refuses certification
language anywhere in the bundle's own prose — the Phase 3.3 rule, as an extension of the report
linter's C5-PROSE discipline.

The carve-out, stated so nobody assumes a bug
---------------------------------------------
The locked sentence itself contains "meets the framework" — as a DENIAL. A regex cannot tell a
denial from a claim, so `lint_prose` removes every EXACT occurrence of the sentence before
scanning (the same pattern as the report linter's markdown-table exclusion for _ASR_CLAIM, added
after its own false-positive story). Any mutated variant — "attests that the system meets the
framework", "certified" — still trips the rule, because only the byte-exact disclaimer is exempt.

What the bundle is — and is not
-------------------------------
Each framework annex states the obligation (with its article/control reference), what this
engagement supplies as evidence, and what remains the client's responsibility. It never asserts
conformity, certification, or that "no findings" means "secure".
"""
from __future__ import annotations

import re

from .asi import ALL_IDS, compute_asr

#: The locked wording. Appears verbatim on the cover page; the test pins the exact bytes.
LOCKED_WORDING = (
    "This bundle attests to testing performed, not that the system meets the framework."
)

#: Annex order: law first, then the certifiable management-system standard, then the voluntary
#: NIST framework.
FRAMEWORKS: tuple[tuple[str, str], ...] = (
    ("EU AI Act — Article 55 (systemic-risk GPAI providers)", "annex-euaiact-art55.md"),
    ("ISO/IEC 42001:2023 (AI management systems)", "annex-iso42001.md"),
    ("NIST AI Risk Management Framework 1.0 (incl. Generative AI Profile)", "annex-nist-ai-rmf.md"),
)

#: Sources pinned so the crosswalk is checkable, not asserted.
SOURCES: tuple[tuple[str, str], ...] = (
    ("EU AI Act Art. 55 text", "https://artificialintelligenceact.eu/article/55/"),
    ("EU AI Act timeline + corrections V-1..V-3", "docs/COMPLIANCE.md"),
    ("NIST AI RMF 1.0", "https://doi.org/10.6028/NIST.AI.100-1"),
    ("ISO/IEC 42001:2023", "https://www.iso.org/standard/42001"),
    ("OWASP Agentic Top 10 2026 (verified verbatim, CC BY-SA 4.0)",
     "docs/research/03-standards-and-frameworks.md §2.3"),
    ("MITRE ATLAS releases + CSA agentic gap analysis",
     "docs/research/03-standards-and-frameworks.md §10"),
    ("SAFE-MCP SAFE-T IDs", "docs/research/17-expansion-research.md (move 8)"),
)

#: MITRE ATLAS facts, from the repo's verified research (docs/research/03 §10;
#: docs/research/17 §1.7; docs/research/19e §3.2), pinned as constants so wording cannot drift
#: from what was verified. Content re-pinned to v2026.07 per PLAN-v5 #16 (atlas-data commit
#: 2306eca: 16 tactics, 101 techniques, 77 sub-techniques, 68 case studies; adds AI Agent Tool
#: Poisoning techniques and the "AI Red Team" mitigation entry; monthly release cadence since
#: Secure AI v2, 6 May 2026). Data format remains v6.0.0 (introduced with v2026.05).
ATLAS_FORMAT_VERSION = ("data format v6 (v6.0.0), content release v2026.07 (monthly cadence; "
                        "16 tactics / 101 techniques / 77 sub-techniques)")
ATLAS_PLATFORM_TAG = "Agentic AI"
ATLAS_RED_TEAM_MITIGATION = (
    'ATLAS content release v2026.07 added a mitigation entry, "AI Red Team" — the taxonomy\'s own '
    "home for adversarial-robustness testing of AI systems."
)
ATLAS_GAP_NOTE = (
    "MITRE ATLAS has no Lateral Movement and no Command-and-Control tactics, and CSA's 2026 gap "
    "analysis finds six agentic technique categories with no adequate ATLAS home (agent-to-agent "
    "lateral movement, tool-chain poisoning, orchestrator hijacking, credential relay through "
    "delegation chains, cross-session memory persistence, MCP server compromise as a pivot). "
    "Findings in categories with no ATLAS home are stated as **outside ATLAS's current taxonomy** "
    "rather than mapped onto tactics that do not exist. The CSA proposals AML.T0090-T0095 remain "
    "**proposed** (untagged citation of them is a mapping error)."
)

#: Standards block for the report's section 3, re-pinned per Phase 3.1: ATLAS format v6 + the
#: Agentic AI platform tag, SAFE-MCP cited with its SAFE-T ID examples, OWASP LLM list pinned to
#: the 2026 edition. Every claim here is verified in the repo's research files (SOURCES above);
#: report.py imports THIS constant as its `_STANDARDS` — one wording, three surfaces, no drift.
STANDARDS_BLOCK_V2 = (
    "OWASP Top 10 for Agentic Applications (ASI01-ASI10) — findings are **mapped to** this framework; "
    "there is no accredited certification body for it, so nothing in this report is certified, "
    "accredited or \"compliant\".\n"
    "- OWASP Top 10 for Large Language Model Applications, **2026 edition** (the 2025 edition was "
    "superseded on 3 August 2026).\n"
    "- OWASP MCP Top 10 — cited as **beta**; MCP attack classes carry SAFE-MCP SAFE-T references "
    "(e.g. SAFE-T1001 tool poisoning, SAFE-T1201 rug pull) where a published ID exists.\n"
    "- MITRE ATLAS, data format v6 with content release v2026.07 (16 tactics / 101 techniques / "
    "77 sub-techniques; monthly cadence), with findings tagged to the **Agentic AI** platform "
    "where a mapping exists; categories with no ATLAS "
    "home are stated as outside ATLAS's current taxonomy.\n"
    "- CISA/NSA *Careful Adoption of Agentic AI Services* (2026).\n"
    "- NIST AI Risk Management Framework and its Generative AI Profile.\n\n"
    "Where an agentic finding has no home in MITRE ATLAS — which has no Lateral Movement or C2 tactics, "
    "and no tactic for six agentic categories — it is described as **outside ATLAS's current "
    "taxonomy** rather than mapped onto something it is not."
)

#: The certification-language rule (Phase 3.3). Two-word phrases with optional whitespace,
#: case-insensitive. Deliberately narrow: it must catch the overclaims that would end the practice
#: without firing on honest words like "tested" or "unified".
_CERTIFICATION_RE = re.compile(
    r"\b(?:certif(?:y|ies|ied|ication)|accredit(?:ed|ation|s)"
    r"|compliant with|meets the framework"
    r"|compliance with (?:the )?(?:eu ai act|iso|iec|nist))\b",
    re.IGNORECASE,
)


#: Denial sentences this module itself emits, byte-exact, exempt from the rule — the same
#: pattern as the report linter's markdown-table exclusion for _ASR_CLAIM (a rule must not fire
#: on its own product's honest output). The LOCKED_WORDING is the first of them. Any OTHER
#: occurrence of a trigger token — including mutated variants of these sentences — trips.
_EXEMPT_DENIALS: tuple[str, ...] = (
    LOCKED_WORDING,
    "Mapped to, never certified — no accredited certification body exists for it",
)


def lint_prose(text: str) -> list[str]:
    """Return certification-language violations, line-attributed. Empty list = clean.

    The byte-exact denial sentences above are removed before scanning: they are the denials the
    rule exists to protect, and any other phrasing of the same idea is still flagged.
    """
    if not text:
        return []
    cleaned = text
    for denial in _EXEMPT_DENIALS:
        cleaned = cleaned.replace(denial, "[REVIEWED DENIAL]")
    hits = []
    for line_no, line in enumerate(cleaned.splitlines(), 1):
        m = _CERTIFICATION_RE.search(line)
        if m:
            hits.append(
                f"line {line_no}: certification language {m.group(0)!r} — the bundle attests to "
                "testing performed, never that a system meets the framework"
            )
    return hits


def _pct(v: float) -> str:
    return f"{v * 100:.1f}%"


def _interval(row: dict) -> str:
    if row["ci_low"] is None or row["ci_high"] is None:
        return "n/a"
    return f"[{_pct(row['ci_low'])}, {_pct(row['ci_high'])}]"


def _categories_tested(engagement) -> list[str]:
    return sorted({a.category for a in engagement.attempts})


def _coverage_rows(engagement) -> str:
    tested = _categories_tested(engagement)
    excluded = sorted(engagement.exclusions)
    missing = [cid for cid in ALL_IDS if cid not in tested and cid not in excluded]
    return (
        f"- Categories tested: {', '.join(tested) if tested else 'none recorded'} "
        f"({len(engagement.attempts)} attempt(s) recorded)\n"
        f"- Categories excluded with a written reason: "
        f"{', '.join(excluded) if excluded else 'none'}\n"
        f"- Categories neither tested nor excluded: {', '.join(missing) if missing else 'none'}"
    )


def _evidence_block(engagement) -> str:
    asr = compute_asr(engagement.attempts)
    overall = asr["__overall__"]
    tested = _categories_tested(engagement)
    return (
        f"- Adversarial testing executed {engagement.start} to {engagement.end} by "
        f"{', '.join(engagement.testers) if engagement.testers else '[TESTER NAMES]'}, against "
        f"{len(engagement.targets)} in-scope target(s), under a signed scope (SHA-256 "
        f"`{engagement.scope_sha256}`).\n"
        f"- {overall['attempts']} recorded attack attempt(s) across the OWASP Agentic categories "
        f"({', '.join(tested) if tested else 'no category recorded'}), reported as "
        f"attack-success rates with 95% Wilson intervals: overall ASR {_pct(overall['asr'])} "
        f"(95% CI {_interval(overall)}).\n"
        f"- Documented methodology: every attempt carries its raw observation (C-1: an "
        f"unevidenced success cannot be constructed or loaded); coverage complete or excluded "
        f"with written reasons (C-4).\n"
        f"- Findings with stable IDs (KES-YYYY-NNN), threat scenarios, C-I-A impact analysis, "
        f"three-part remediation.\n"
        f"- The AIBOM inventory (CycloneDX 1.6) of the agents, tools, MCP servers and models in "
        f"scope."
    )


def _annex_art55(engagement) -> str:
    return f"""## Annex A — EU AI Act, Article 55 (systemic-risk GPAI providers)

**Obligation (Art. 55(1)(a)):** providers of general-purpose AI models classified as systemic
risk shall perform model evaluations including adversarial testing, carried out per documented
methodologies, to identify and mitigate systemic risks. Art. 55 binds the **provider** of the
model, not the deployer (COMPLIANCE.md V-2): a provider maps this annex into its own Art. 55(1)(a)
file; a deployer uses the same testing as its own risk-management input.

**What this engagement supplies:**

{_evidence_block(engagement)}

**What remains the provider's responsibility:** the Art. 55 evaluations span beyond adversarial
testing — systemic-risk assessment (55(1)(b)), incident reporting to the AI Office (55(1)(c)),
and cybersecurity state (55(1)(d)). This engagement is one documented input, not the evaluation
file, and only the provider, with its own compliance function, can assert conformity.
{LOCKED_WORDING}"""


def _annex_iso42001(engagement) -> str:
    return f"""## Annex B — ISO/IEC 42001:2023 (AI management systems)

**Relevant controls:** an AI management system requires documented AI risk assessment and
treatment (Clauses 8.2/8.3), AI system impact assessment (8.5), and operation controls over the
AI system lifecycle — including evidence that security testing of AI behaviour is performed and
recorded. Conformity to ISO/IEC 42001 is an audit outcome for the **organisation**, granted by an
external audit body; no engagement output can substitute for it.

**What this engagement supplies:**

{_evidence_block(engagement)}

**What remains the client's responsibility:** operating the management system, its internal
audit, and the external audit that grants conformity. {LOCKED_WORDING}"""


def _annex_nist(engagement) -> str:
    return f"""## Annex C — NIST AI Risk Management Framework 1.0 (incl. Generative AI Profile)

**Relevant functions:** MEASURE (quantitative, reproducible measurement of AI behaviour — here:
attack-success rates over stated attempts with 95% Wilson intervals, not opinions) and MANAGE
(treatment priority, retest verification — here: findings with three-part remediation and a
computed retest delta when a retest was performed). The Generative AI Profile's security
measurement guidance is the same discipline at model level.

**What this engagement supplies:**

{_evidence_block(engagement)}

**What remains the client's responsibility:** GOVERN and MAP decisions — risk tolerances,
deployment context, and the organisational functions around the system. {LOCKED_WORDING}"""


#: The annex renderers, keyed by the FRAMEWORKS order.
_ANNEX_RENDERERS = (_annex_art55, _annex_iso42001, _annex_nist)


def render_cover(engagement) -> str:
    """The cover page. The locked sentence sits alone and bold, where an auditor reads first."""
    tested = _categories_tested(engagement)
    return f"""# Compliance evidence bundle — {engagement.client}

**Engagement reference:** {engagement.ref}
**Testing window:** {engagement.start} to {engagement.end}
**Scope document:** signed, SHA-256 `{engagement.scope_sha256}`
**Testers:** {", ".join(engagement.testers) if engagement.testers else "[TESTER NAMES]"}
**Frameworks covered by this bundle:** {", ".join(name for name, _ in FRAMEWORKS)}

**What this bundle contains:** one annex per framework, each stating the obligation, the evidence
this engagement supplies (attempts, attack-success rates with intervals, coverage denominator,
findings with the KES contract, AIBOM), and what remains the client's responsibility. The
measurement spine of every annex is the engagement document itself — this bundle is a rendering
of it, never an independent claim.

**Categories addressed:** {", ".join(tested) if tested else "none recorded"} of the OWASP Agentic
Top 10 (ASI01-ASI10); the full denominator is in the coverage table.

**{LOCKED_WORDING}**"""


def render_annexes(engagement) -> dict[str, str]:
    """One markdown annex per framework, keyed by the FRAMEWORKS filename."""
    return {
        fname: renderer(engagement)
        for (_, fname), renderer in zip(FRAMEWORKS, _ANNEX_RENDERERS)
    }


def render_crosswalk(engagement) -> str:
    """The standards crosswalk (Phase 3.1): ATLAS v6 + Agentic AI platform + SAFE-MCP + 2026
    OWASP edition, re-pinned over the engagement's categories. Cites every mapping's source
    version; states the ATLAS gap instead of inventing tactics."""
    tested = _categories_tested(engagement)
    lines = [
        "# Standards crosswalk",
        "",
        f"- **OWASP Top 10 for Agentic Applications 2026** (ASI01-ASI10, CC BY-SA 4.0; document "
        f"dated December 2025, announced 9 December 2025) — the syllabus this engagement tested: "
        f"{', '.join(tested) if tested else 'no category recorded'}. *Mapped to, never certified — "
        f"no accredited certification body exists for it.*",
        f"- **OWASP Top 10 for LLM Applications, 2026 edition** (v1.0, 3 August 2026; superseded "
        f"the 2025 list) — cited by edition so a reader cannot mistake it for the 2025 list.",
        f"- **OWASP MCP Top 10** — cited as **beta** (its own page is not final). MCP attack "
        f"classes additionally carry SAFE-MCP SAFE-T references where a published ID exists "
        f"(e.g. SAFE-T1001 tool poisoning, SAFE-T1201 rug pull).",
        f"- **MITRE ATLAS, {ATLAS_FORMAT_VERSION}** — findings are tagged to the "
        f"**{ATLAS_PLATFORM_TAG}** platform where a mapping exists. {ATLAS_GAP_NOTE}",
        f"- **CISA/NSA *Careful Adoption of Agentic AI Services* (1 May 2026)** — the first "
        f"coordinated multinational agentic-AI guidance; the report structure follows its "
        f"expected-practice shape. Voluntary: evidence of expected practice, not law.",
        f"- **NIST AI RMF 1.0 + GenAI Profile; ISO/IEC 42001:2023; EU AI Act Arts 53/55** — "
        f"evidence maps are in the annexes. Deadlines and penalty tiers as corrected in "
        f"docs/COMPLIANCE.md (V-1..V-3).",
        "",
        "**Sources**",
        "",
    ]
    lines += [f"- {name}: {ref}" for name, ref in SOURCES]
    return "\n".join(lines)


def render_bundle(engagement) -> dict[str, str]:
    """Every bundle artefact, keyed by filename. Pure function of the engagement document."""
    out = {"bundle-cover.md": render_cover(engagement)}
    out.update(render_annexes(engagement))
    out["standards-crosswalk.md"] = render_crosswalk(engagement)
    return out
