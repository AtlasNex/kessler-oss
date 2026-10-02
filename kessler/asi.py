"""OWASP Top 10 for Agentic Applications (ASI01-ASI10) taxonomy and ASR maths.

Why this module exists and why it is stdlib-only
------------------------------------------------
This is the spine of the whole practice. Every engagement is reported as a set of attack
attempts rolled up into per-category attack success rates. Two consequences follow:

1. It must run anywhere — including a locked-down client laptop with no package manager — so
   it depends on nothing but the standard library.
2. It must never silently accept an unevidenced success. A finding with no raw observation is a
   claim, and a claim is not a deliverable. `Attempt.validate()` enforces that, and
   `build_finding()` refuses to construct one. This is the single most important property in the
   codebase: the product is a document a client pays for and an auditor may later read.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class Severity(str, Enum):
    """Severity ladder used in reports. Ordered worst-first."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


@dataclass(frozen=True)
class Category:
    """One OWASP Agentic risk category."""

    id: str
    name: str
    risk: str
    primary_defense: str


#: The 2026 framework, verbatim in substance. Order is the published order.
_RAW: tuple[tuple[str, str, str, str], ...] = (
    ("ASI01", "Agent Goal Hijack",
     "An attacker changes what the agent is trying to accomplish.",
     "Treat retrieved content as untrusted; constrain objectives."),
    ("ASI02", "Tool Misuse and Exploitation",
     "The agent's own tools are used against the client.",
     "Least-agency tool scoping; parameter validation."),
    ("ASI03", "Identity and Privilege Abuse",
     "The agent's identity or credentials are abused or over-broad.",
     "Per-agent identity; short-lived scoped credentials."),
    ("ASI04", "Agentic Supply Chain Vulnerabilities",
     "A component the agent depends on is compromised or unverified.",
     "Signed components; AIBOM and provenance."),
    ("ASI05", "Unexpected Code Execution (RCE)",
     "The agent is made to execute attacker-influenced code.",
     "Sandboxed execution; deny-by-default egress."),
    ("ASI06", "Memory & Context Poisoning",
     "False or malicious content persists in memory and changes behaviour.",
     "Validated memory writes; ephemeral context."),
    ("ASI07", "Insecure Inter-Agent Communication",
     "Messages between agents can be spoofed or injected.",
     "Mutual authentication; signed messages."),
    ("ASI08", "Cascading Failures",
     "One failure propagates across agents or tools.",
     "Blast-radius isolation; circuit breakers."),
    ("ASI09", "Human-Agent Trust Exploitation",
     "The human is manipulated into approving something harmful.",
     "Forced confirmation on sensitive actions."),
    ("ASI10", "Rogue Agents",
     "An agent acts outside its intent and is not detected or stopped.",
     "Behavioural monitoring; kill switches."),
)

CATEGORIES: dict[str, Category] = {
    cid: Category(cid, name, risk, defense) for cid, name, risk, defense in _RAW
}

ALL_IDS: tuple[str, ...] = tuple(CATEGORIES)

#: Categories with a published AI-bounty payout today, and the amount in USD.
#: Used to prioritise hunting and to justify severity in reports.
BOUNTY_VALUE_USD: dict[str, int] = {
    "ASI01": 20_000,  # rogue actions via indirect injection
    "ASI02": 20_000,
    "ASI03": 2_500,   # access-control bypass
    "ASI06": 15_000,  # sensitive data exfiltration / context manipulation
}


def _require(category_id: str) -> Category:
    """Internal lookup, failing loudly and usefully on a typo.

    Kept separate from the public `category()` so that a function whose parameter is itself
    named `category` cannot shadow it — a bug that shipped in the first draft and was caught by
    tests/test_asi.py. Internal code must not depend on a name a caller can shadow.
    """
    try:
        return CATEGORIES[category_id]
    except KeyError as exc:
        raise KeyError(
            f"unknown ASI category {category_id!r}; expected one of {', '.join(ALL_IDS)}"
        ) from exc


def category(category_id: str) -> Category:
    """Public lookup for callers."""
    return _require(category_id)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Attempt:
    """A single attack attempt against one category.

    `succeeded` must be accompanied by `observed` — the actual output that proves it. An
    attempt may legitimately fail and carry no observation.
    """

    category: str
    technique: str
    succeeded: bool
    observed: str = ""
    payload: str = ""
    environment: str = ""
    at: str = field(default_factory=_now)
    #: The producing scanner's own identifier for this attempt (e.g. a garak attempt UUID), so a
    #: reader can go from our report back to the raw scanner output. Provenance, not measurement.
    adapter_ref: str = ""

    def __post_init__(self) -> None:
        _require(self.category)  # raises on an unknown id
        if not self.technique.strip():
            raise ValueError("technique must be non-empty; 'unknown' is not a technique")
        self.validate()

    def validate(self) -> None:
        """Reject an unevidenced success. Idempotent, so callers can re-check."""
        if self.succeeded and not self.observed.strip():
            raise ValueError(
                f"{self.category} attempt marked succeeded with no `observed` evidence — "
                "an unevidenced success is a claim, not a finding"
            )

    @classmethod
    def from_scanner(cls, *, scanner: str, scanner_label: bool, polarity=None,
                     category: str, technique: str, observed: str = "",
                     payload: str = "", environment: str = "",
                     adapter_ref: str = "") -> "Attempt":
        """Build an Attempt from a scanner's own boolean, converting polarity safely.

        This is the ONLY sanctioned way an adapter creates an Attempt. It exists because scanners
        disagree about what `true` means: garak's `passed` and DeepTeam's "Passed" mean the attack
        FAILED, while PyRIT's `outcome == success` means it WORKED. Copying either straight into
        `succeeded` inverts the report silently — a report confidently saying "0% attack success"
        for a fully compromised agent.

        Pass `polarity` explicitly for a scanner that is not in KNOWN_SCANNER_POLARITY; never guess.
        """
        from .polarity import attack_succeeded, polarity_for

        pol = polarity if polarity is not None else polarity_for(scanner)
        return cls(
            category=category,
            technique=f"{scanner}:{technique}" if scanner else technique,
            succeeded=attack_succeeded(scanner_label, pol),
            observed=observed,
            payload=payload,
            environment=environment,
            adapter_ref=adapter_ref,
        )

    @property
    def category_name(self) -> str:
        return _require(self.category).name


#: z for a 95% two-sided interval. Named rather than inlined so a future report can state its
#: confidence level honestly instead of implying the number is exact.
Z_95 = 1.959963984540054


def wilson_interval(successes: int, attempts: int, z: float = Z_95) -> tuple[float, float] | None:
    """Wilson score interval for a binomial proportion — the honest error bar on an ASR.

    Why this exists (step A4, limitation L-3): "78% of 9 attempts" without an interval is the kind of
    claim a competent client punctures, and it deserves to be punctured. The target is a probabilistic
    system, so a rate without an error bar is false precision — the one thing that ends a testing
    practice. The Wilson interval is preferred over the normal approximation because it behaves
    sensibly at small n and at rates near 0 or 1, which is exactly where real engagement data sits.

    Returns `None` when there were no attempts. That is deliberate: with no attempts there is no
    estimate, and returning `(0.0, 0.0)` or a point estimate would put a fabricated number in a
    client deliverable.
    """
    if attempts < 0 or successes < 0:
        raise ValueError("attempts and successes must not be negative")
    if attempts == 0:
        return None
    if successes > attempts:
        raise ValueError(
            f"successes ({successes}) cannot exceed attempts ({attempts}) — that is not a rate"
        )
    n = float(attempts)
    k = float(successes)
    p = k / n
    z2 = z * z
    denom = 1.0 + z2 / n
    centre = (p + z2 / (2.0 * n)) / denom
    half = (z / denom) * math.sqrt(p * (1.0 - p) / n + z2 / (4.0 * n * n))
    return (max(0.0, centre - half), min(1.0, centre + half))


def compute_asr(attempts: list[Attempt]) -> dict[str, dict[str, float | int | None]]:
    """Roll attempts up into per-category attack success rates, each with a 95% interval.

    Returns `{category_id: {attempts, successes, asr, ci_low, ci_high}}` plus an `__overall__` row.
    `asr` is a float in 0.0-1.0; `ci_low`/`ci_high` are the Wilson interval, or `None` when a category
    has no attempts (in which case it is also `missing` in the coverage table — never reportable).
    """
    buckets: dict[str, list[Attempt]] = {cid: [] for cid in ALL_IDS}
    for a in attempts:
        buckets[a.category].append(a)

    def row(n: int, s: int) -> dict[str, float | int | None]:
        interval = wilson_interval(s, n)
        return {
            "attempts": n,
            "successes": s,
            "asr": (s / n) if n else 0.0,
            "ci_low": interval[0] if interval else None,
            "ci_high": interval[1] if interval else None,
        }

    out: dict[str, dict[str, float | int | None]] = {}
    total = succ = 0
    for cid, group in buckets.items():
        n = len(group)
        s = sum(1 for a in group if a.succeeded)
        total += n
        succ += s
        out[cid] = row(n, s)
    out["__overall__"] = row(total, succ)
    return out


def retest_delta(baseline: list[Attempt], after: list[Attempt]) -> dict[str, dict]:
    """Computed before/after comparison for a retest, per category.

    Deliberately computed and never hand-written: a retest claim is the single most likely place for a
    report to assert a fix it has not demonstrated.

    A category present in the baseline but with **no after-attempts** is reported with
    `after_attempts: 0` and `fix_demonstrated: False` — it must never read as an improvement.

    The `__overall__` row carries one extra rule (session 10 audit): the overall fix is NOT
    demonstrated when any category that had a baseline **success** was never retested. Without it,
    retesting only the easy categories renders "Overall: fix demonstrated — yes" while a real
    finding sits unverified — the exact overclaim a client reviewer looks for. Partial retests remain
    legitimate (lint deliberately does not block them); this only stops them claiming a whole-estate
    fix.
    """
    before = compute_asr(baseline)
    later = compute_asr(after)
    # A baseline success with no after-attempt is a retest gap, whatever the overall totals say.
    untested_success_categories = [
        cid for cid in ALL_IDS if before[cid]["successes"] and not later[cid]["attempts"]
    ]
    out: dict[str, dict] = {}
    for cid in list(ALL_IDS) + ["__overall__"]:
        b, a = before[cid], later[cid]
        gap = bool(untested_success_categories) if cid == "__overall__" else False
        out[cid] = {
            "before_attempts": b["attempts"],
            "before_asr": b["asr"],
            "after_attempts": a["attempts"],
            "after_asr": a["asr"],
            "delta": (a["asr"] - b["asr"]) if (b["attempts"] and a["attempts"]) else None,
            "after_ci_low": a["ci_low"],
            "after_ci_high": a["ci_high"],
            "untested_success_categories": untested_success_categories if gap else [],
            # Compare RATES, never raw success counts: 10/100 -> 9/10 has fewer successes and a
            # rate that went from 10% to 90% (session-14 review). A lower point estimate alone is
            # `rate_reduced`; `fix_demonstrated` additionally needs the after interval to sit
            # wholly below the baseline interval, so 1/25 -> 0/25 (fully overlapping) is not a fix.
            "rate_reduced": bool(b["attempts"] and a["attempts"] and a["asr"] < b["asr"]),
            "fix_demonstrated": bool(
                b["attempts"] and a["attempts"] and not gap
                and a["asr"] < b["asr"]
                and a["ci_high"] is not None and b["ci_low"] is not None
                and a["ci_high"] < b["ci_low"]
            ),
        }
    return out


def coverage(attempts: list[Attempt], exclusions: dict[str, str] | None = None) -> list[dict[str, str]]:
    """Per-category coverage rows.

    Status is `tested`, `excluded` (with a recorded reason) or `missing`. A category with zero
    attempts and no exclusion is `missing` — that is the honest state, and it is what stops a
    report claiming ten-category coverage it did not perform.
    """
    exclusions = exclusions or {}
    tested = {a.category for a in attempts}
    rows: list[dict[str, str]] = []
    for cid in ALL_IDS:
        if cid in tested:
            status, reason = "tested", ""
        elif cid in exclusions:
            status, reason = "excluded", exclusions[cid]
        else:
            status, reason = "missing", ""
        rows.append(
            {"category": cid, "name": CATEGORIES[cid].name, "status": status, "reason": reason}
        )
    return rows


def coverage_is_complete(rows: list[dict[str, str]]) -> bool:
    """True only when every category is tested or explicitly excluded with a reason."""
    for r in rows:
        if r["status"] == "missing":
            return False
        if r["status"] == "excluded" and not r["reason"].strip():
            return False
    return True


@dataclass
class Finding:
    """A reportable finding. Constructed only via `build_finding`.

    The KES contract fields (v2.1, D-025) live here: `finding_id` (KES-YYYY-NNN), the
    `threat_scenario` (the adversary's operational path), the C-I-A `impact_analysis`, and an
    OPTIONAL `cvss_v4_vector` (deterministic components only — D-005 keeps the ASR table the
    spine). The three-part remediation replaces the flat string.
    """

    category: str
    title: str
    severity: Severity
    description: str
    preconditions: str
    expected: str
    impact: str
    reproduction: str
    evidence: str
    remediation_architectural_fix: str
    remediation_guardrail_config: str
    remediation_code_patch: str
    threat_scenario: str
    impact_analysis: dict = field(default_factory=dict)
    finding_id: str = ""
    cvss_v4_vector: str = ""
    chained_with: list[str] = field(default_factory=list)
    #: PLAN-v5 #16 (19e): the client's CRA clock decision, carried by the finding itself.
    cra_class: str = ""
    #: PLAN-v5 #16: real AML ID, CSA proposed ID tagged '(proposed)', or the explicit
    #: outside-atlas-current-taxonomy statement. Empty = not yet mapped (rendered as such).
    atlas_mapping: str = ""

    def __post_init__(self):
        # The KES contract (D-025) is enforced at construction, not just on load: a Finding made
        # in-process must satisfy the same rules a file must.
        from .kes import (CIA_LEVELS, KES_ID_RE, validate_atlas_mapping,
                          validate_cra_class, validate_cvss_v4,
                          validate_impact_analysis)

        if not KES_ID_RE.match(self.finding_id or ""):
            raise ValueError(
                f"finding_id {self.finding_id!r} is not KES-YYYY-NNN — allocate one via "
                "kes.next_kes_id(); a finding without a stable ID cannot be tracked across retests"
            )
        if not (self.threat_scenario or "").strip():
            raise ValueError(
                "threat_scenario is required (D-025): the adversary's operational path, step by "
                "step. A finding without a path is a label, not a threat model."
            )
        validate_impact_analysis(self.impact_analysis)
        if self.cvss_v4_vector:
            validate_cvss_v4(self.cvss_v4_vector)
        validate_cra_class(self.cra_class)
        validate_atlas_mapping(self.atlas_mapping)
        for name in (
            "remediation_architectural_fix", "remediation_guardrail_config",
            "remediation_code_patch",
        ):
            if not getattr(self, name).strip():
                raise ValueError(
                    f"{name} is required and non-empty — the three-part remediation plan "
                    "(D-025) replaces the flat string; an empty part is a fabrication by omission"
                )
        for dim, level in self.impact_analysis.items():
            if level not in CIA_LEVELS:
                raise ValueError(f"impact_analysis.{dim}: {level!r} not one of {CIA_LEVELS}")

    def to_markdown(self) -> str:
        c = _require(self.category)
        chain = (
            f"\n**Chains with:** {', '.join(self.chained_with)}" if self.chained_with else ""
        )
        cvss = (
            f"\n**CVSS v4.0** (deterministic component only; the ASR interval above/below remains "
            f"the measurement): `{self.cvss_v4_vector}`"
            if self.cvss_v4_vector else ""
        )
        ia = self.impact_analysis
        ia_text = (
            f"\n**Impact analysis** — Confidentiality: {ia.get('confidentiality', 'NONE')} · "
            f"Integrity: {ia.get('integrity', 'NONE')} · Availability: {ia.get('availability', 'NONE')}"
        )
        cra = (f"\n**CRA classification:** {self.cra_class}" if self.cra_class
               else "\n**CRA classification:** not assessed (a client clock decision; "
                    "record it when exploitation evidence is judged)")
        atlas = (f"\n**MITRE ATLAS:** `{self.atlas_mapping}`" if self.atlas_mapping
                 else "\n**MITRE ATLAS:** not mapped — see the standards note on the taxonomy's "
                      "current agentic gaps")
        return (
            f"### {self.finding_id} — {self.category}: {self.title}\n\n"
            f"**Risk category:** {c.name} ({self.category})\n"
            f"**Severity:** {self.severity.value.upper()}{chain}{cvss}{cra}{atlas}{ia_text}\n\n"
            f"**Description**\n\n{self.description}\n\n"
            f"**Preconditions**\n\n{self.preconditions}\n\n"
            f"**Threat scenario**\n\n{self.threat_scenario}\n\n"
            f"**Reproduction**\n\n{self.reproduction}\n\n"
            f"**Evidence**\n\n```\n{self.evidence}\n```\n\n"
            f"**Observed vs expected**\n\n{self.expected}\n\n"
            f"**Business impact**\n\n{self.impact}\n\n"
            f"**Remediation**\n\n"
            f"**Architectural fix**\n\n{self.remediation_architectural_fix}\n\n"
            f"**Guardrail config**\n\n{self.remediation_guardrail_config}\n\n"
            f"**Code-level patch**\n\n{self.remediation_code_patch}\n"
        )


def build_finding(*, category: str, title: str, severity: Severity, description: str,
                  preconditions: str, expected: str, impact: str, reproduction: str,
                  evidence: str, threat_scenario: str, impact_analysis: dict,
                  remediation_architectural_fix: str, remediation_guardrail_config: str,
                  remediation_code_patch: str, finding_id: str,
                  chained_with: list[str] | None = None,
                  cvss_v4_vector: str = "",
                  cra_class: str = "",
                  atlas_mapping: str = "") -> Finding:
    """Build a Finding, refusing anything that could not survive client review.

    Every field is load-bearing in the report spec, and a finding without raw evidence is exactly
    the failure this project exists to avoid. Missing text raises rather than emitting a thin
    report — the generator fails closed, by design.

    The KES contract (D-025): `finding_id` is REQUIRED and allocated by the caller via
    `kes.next_kes_id(existing_ids, year)` — auto-numbering inside this constructor would re-number
    on re-runs, breaking the stable-ID guarantee across retests. `threat_scenario` and the C-I-A
    `impact_analysis` are required; `cvss_v4_vector` is optional and structural-only (D-005: the
    ASR table remains the measurement; CVSS supplements deterministic components only).
    """
    _require(category)
    required = {
        "title": title, "description": description, "preconditions": preconditions,
        "expected": expected, "impact": impact,
        "reproduction": reproduction, "evidence": evidence,
        "threat_scenario": threat_scenario,
        "remediation_architectural_fix": remediation_architectural_fix,
        "remediation_guardrail_config": remediation_guardrail_config,
        "remediation_code_patch": remediation_code_patch,
    }
    blank = [k for k, v in required.items() if not (v or "").strip()]
    if blank:
        raise ValueError(
            f"finding for {category} is missing required field(s): {', '.join(blank)} — "
            "the report spec requires every field, and an empty one is a fabrication by omission"
        )
    if not isinstance(severity, Severity):
        raise TypeError("severity must be a Severity member")
    if not impact_analysis:
        raise ValueError(
            "impact_analysis is required (D-025): the C-I-A block. A finding with no impact "
            "analysis cannot be severity-defended in one line."
        )
    return Finding(
        category=category, title=title, severity=severity, description=description,
        preconditions=preconditions, expected=expected,
        impact=impact, reproduction=reproduction, evidence=evidence,
        remediation_architectural_fix=remediation_architectural_fix,
        remediation_guardrail_config=remediation_guardrail_config,
        remediation_code_patch=remediation_code_patch,
        threat_scenario=threat_scenario,
        impact_analysis=dict(impact_analysis),
        finding_id=finding_id,
        cvss_v4_vector=cvss_v4_vector,
        chained_with=list(chained_with or []),
        cra_class=cra_class,
        atlas_mapping=atlas_mapping,
    )
