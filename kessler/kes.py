"""The KES finding contract (D-025) — finding IDs, threat scenarios, C-I-A impact, CVSS v4.

Why this module exists
----------------------
The owner's engine brief specifies the deliverable standard: every finding carries a stable
identifier (KES-YYYY-NNN), a step-by-step threat scenario (the adversary's operational path), a
per-dimension impact analysis (confidentiality / integrity / availability), and an OPTIONAL CVSS
v4.0 vector. Two constraints shape how it is added:

1. **D-005 unchanged — the ASR table stays the spine.** CVSS scores a deterministic system: one
   exploit, one outcome. An agentic finding is probabilistic — the same prompt succeeds N% of M
   attempts, and no scalar summary of that is honest. So CVSS is accepted only as a *supplement*
   on deterministic components, never a replacement for the interval, and never a roll-up.
2. **C-2 (stdlib-only).** No cvss library. The format check is structural: `CVSS:4.0/` followed by
   `/K:V` pairs with known keys. Full semantic validation is deliberately out of scope — a
   wrong-but-well-formed vector is a human problem; a malformed one would corrupt deliverables,
   and that is caught here.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

#: CIADB-labelled impact levels: Confidentiality, Integrity, Availability.
CIA_LEVELS = ("HIGH", "MEDIUM", "LOW", "NONE")

#: CVSS v4.0 metric keys (FIRST v4.0 spec) — the structural allowlist for vector validation.
CVSS_V4_KEYS = frozenset(
    "AV AC PR UI VC VI VA SC SI SA E AU R A V RE U L MA M".split()
)

# ponytail: the key list is a structural allowlist, not a semantic validator — wrong-but-well-formed
# vectors pass, because a full metric model is overreach for stdlib-only and a human reviews the
# report anyway. Upgrade path: table-driven validator if a client demands machine-verified vectors.

#: KES-YYYY-NNN — the owner's brief's ID scheme.
KES_ID_RE = re.compile(r"^KES-\d{4}-\d{3}$")

#: Deterministic allocation template. Padding fixed at 3 digits (999 per engagement-year is ample).
KES_ID_FMT = "KES-{year}-{seq:03d}"

#: The finding fields this contract adds to `FINDING_FIELDS` (schema.py).
KES_FINDING_FIELDS: tuple[str, ...] = (
    "finding_id",
    "threat_scenario",
    "impact_analysis",
    "cvss_v4_vector",
)

#: Remediation becomes three parts (the owner's brief: architectural fix, guardrail config,
#: code-level patch). Flat strings in the document; the renderer composes them.
REMEDIATION_PARTS: tuple[str, ...] = (
    "remediation_architectural_fix",
    "remediation_guardrail_config",
    "remediation_code_patch",
)


#: CRA classification (PLAN-v5 #16, 19e §1/§5.4): an agent framework / MCP server / agent-built
#: product sold into the EU is a product with digital elements; a demonstrated active
#: exploitability starts the client's 24h/72h clocks. The field lets the triage decision be made
#: from the finding itself: which class applies, and the one line why the class is what it is.
CRA_CLASSES = ("aev-reportable",        # actively exploited vulnerability: reliable evidence of
                                            # exploitation exists (a demonstrated hit IS that evidence)
               "severe-incident",       # exploitation happened and caused a severe incident
               "bau-finding")           # business-as-usual: no exploitation evidence found
CRA_RE = re.compile(r"^(" + "|".join(CRA_CLASSES) + r")$")

#: ATLAS mapping state (PLAN-v5 #16, honesty register). Either a real AML technique ID, a
#: proposed-gap ID tagged as PROPOSED (CSA AML.T0090-T0095 are not adopted yet; the tag is
#: load-bearing), or the explicit statement that ATLAS's current taxonomy has no home here.
#: ("outside-atlas" is the only sentence the practice will ever write about those six gap
#: categories — never a forced mapping onto a tactic that does not exist.)
ATLAS_RE = re.compile(r"^(AML\.T\d{4}(?:\.\d{4})?(?: \(proposed\))?|outside-atlas-current-taxonomy)$")

#: Technique IDs that DO NOT EXIST in ATLAS as of content release v2026.07 (the CSA gap-analysis
#: proposals). A bare mapping to one claims a home that is not there; it is only valid tagged
#: '(proposed)'. Bump this constant (and DECISIONS) when/if MITRE adopts an ID.
ATLAS_PROPOSED_IDS = frozenset(f"AML.T{n:04d}" for n in range(90, 96))


def validate_cra_class(value: str) -> None:
    if value and not CRA_RE.match(value):
        raise ValueError(
            f"cra_class {value!r} is not one of {', '.join(CRA_CLASSES)} (empty = not assessed; "
            "the field is the client's 24h/72h clock decision, never a free-text guess)")


def validate_atlas_mapping(value: str) -> None:
    if value and not ATLAS_RE.match(value):
        raise ValueError(
            f"atlas_mapping {value!r} is not a valid ATLAS statement: use a real AML.T#### ID, a "
            "CSA proposed ID tagged ' (proposed)' (AML.T0090-T0095 are NOT adopted), or the exact "
            "sentence 'outside-atlas-current-taxonomy' — a forced mapping onto a nonexistent "
            "tactic is the error this rail prevents")
    base = value.replace(" (proposed)", "") if value else ""
    if base in ATLAS_PROPOSED_IDS and not value.endswith(" (proposed)"):
        raise ValueError(
            f"atlas_mapping {value!r}: AML.T0090-T0095 are CSA PROPOSALS (gap analysis, 27 Mar "
            "2026) — not adopted by MITRE as of v2026.07. Tag them '(proposed)' or map to an ID "
            "that exists; an untagged proposed ID reads as an existing mapping and is the "
            "exact drift this rail exists to stop")


def validate_cvss_v4(vector: str) -> str:
    """Structural validation of a CVSS v4.0 vector string. Returns it normalised.

    Raises ValueError on anything that is not `CVSS:4.0/` + well-formed `/K:V` pairs with known
    metric keys. Deliberately does NOT check that the key *values* are legal for that metric —
    see the module docstring: malformed is a machine problem, wrong is a human problem.
    """
    if not isinstance(vector, str) or not vector.startswith("CVSS:4.0/"):
        raise ValueError("cvss_v4_vector must start with 'CVSS:4.0/'")
    body = vector[len("CVSS:4.0/"):]
    if not body:
        raise ValueError("cvss_v4_vector has no metrics after the prefix")
    seen: set[str] = set()
    for part in body.split("/"):
        if ":" not in part:
            raise ValueError(f"malformed metric {part!r} (expected KEY:VALUE)")
        k, v = part.split(":", 1)
        if k not in CVSS_V4_KEYS:
            raise ValueError(f"unknown CVSS v4 metric key {k!r}")
        if not k or not v:
            raise ValueError(f"empty metric key or value in {part!r}")
        if k in seen:
            raise ValueError(f"duplicate metric key {k!r}")
        seen.add(k)
    return vector


def validate_impact_analysis(ia: dict) -> dict:
    """Validate the C-I-A impact block: exactly three keys, each a CIADB level."""
    if not isinstance(ia, dict):
        raise ValueError("impact_analysis must be an object")
    expected = {"confidentiality", "integrity", "availability"}
    keys = set(ia)
    if keys != expected:
        missing, extra = expected - keys, keys - expected
        raise ValueError(
            "impact_analysis must have exactly confidentiality/integrity/availability"
            + (f"; missing: {sorted(missing)}" if missing else "")
            + (f"; unknown: {sorted(extra)}" if extra else "")
        )
    for k, v in ia.items():
        if v not in CIA_LEVELS:
            raise ValueError(
                f"impact_analysis.{k}: {v!r} not one of {', '.join(CIA_LEVELS)}"
            )
    return ia


def next_kes_id(existing: list[str], year: int) -> str:
    """Next free KES-YYYY-NNN given the existing IDs (per engagement-year sequence).

    Deterministic from the data: the sequence is one more than the highest used number for that
    year, so re-running never re-numbers (a re-run, not a rewrite — the plan's own rule).
    """
    prefix = f"KES-{year}-"
    used = []
    for s in existing:
        if not isinstance(s, str) or not s.startswith(prefix):
            continue
        suffix = s[len(prefix):]
        if suffix.isdigit():
            used.append(int(suffix))
    return KES_ID_FMT.format(year=year, seq=(max(used) + 1) if used else 1)


@dataclass(frozen=True)
class ThreatScenario:
    """The adversary's operational path, step by step.

    Plain strings, not objects: a scenario is written prose a reader follows, and nesting it
    would make the document harder to write and review without making it more true.
    """

    steps: tuple[str, ...]

    def __post_init__(self):
        if not self.steps:
            raise ValueError("threat_scenario needs at least one step")
        for i, s in enumerate(self.steps, 1):
            if not isinstance(s, str) or not s.strip():
                raise ValueError(f"threat_scenario step {i} is empty")

    def to_text(self) -> str:
        return "\n".join(f"{i}. {s}" for i, s in enumerate(self.steps, 1))


@dataclass(frozen=True)
class RemediationPlan:
    """Three-part remediation per the owner's brief (D-025)."""

    architectural_fix: str
    guardrail_config: str
    code_patch: str

    def __post_init__(self):
        for name in ("architectural_fix", "guardrail_config", "code_patch"):
            if not getattr(self, name).strip():
                raise ValueError(f"remediation.{name} is empty — a three-part plan with an empty "
                                 "part is a fabrication by omission")

    def to_text(self) -> str:
        return (
            f"**Architectural fix**\n\n{self.architectural_fix}\n\n"
            f"**Guardrail config**\n\n{self.guardrail_config}\n\n"
            f"**Code-level patch**\n\n{self.code_patch}"
        )


def validate_remediation_parts(raw: dict) -> None:
    """On load: all three remediation parts present and non-empty."""
    for part in REMEDIATION_PARTS:
        v = raw.get(part)
        if not isinstance(v, str) or not v.strip():
            raise ValueError(f"finding.{part} is required and non-empty (D-025 three-part plan)")
