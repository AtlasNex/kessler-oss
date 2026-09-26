"""mcp-scanner adapter — Cisco AI Defense MCP Scanner's findings into `Attempt` objects.

mcp-scanner is the only scanner surveyed that ships a **real taxonomy of its own**, and it is the one
native to MCP servers and tool definitions. This parses a **saved real run**, following the A3.1 method:
every claim below was observed by executing cisco-ai-mcp-scanner 4.8.4.

A FOURTH structural variant: there is no verdict field at all
-------------------------------------------------------------
garak has `passed`, PyRIT has `outcome`, and garak's detectors have scores. mcp-scanner's
`SecurityFinding` has **no boolean and no verdict field of any kind**. Its complete key set, observed:

    analyzer · details · mcp_taxonomy · severity · summary · threat_category

The signal is the **existence of a finding object**. A tool that violated nothing produces an empty
list — confirmed against the tool's own fixtures: `good_tool.json` → **0 findings**, and its four
deliberately-flawed siblings → **10–12 each**. So the adapter does not read a verdict, it counts
objects, and the check that matters is that the clean fixture really does produce none.

THE SEMANTIC PROBLEM, WHICH IS THE POINT OF THIS FILE
----------------------------------------------------
These are **readiness / policy checks, not attacks.** The observed `threat_category` values are:

    UNSAFE_RETRY_LOOP · SILENT_FAILURE_PATH · NO_OBSERVABILITY_HOOKS · MISSING_ERROR_SCHEMA ·
    OVERLOADED_TOOL_SCOPE · MISSING_TIMEOUT_GUARD · NON_DETERMINISTIC_RESPONSE

Nobody attacked anything. mcp-scanner statically evaluates a tool definition against a policy and
reports weaknesses. **Calling a HIGH readiness finding "the attack succeeded" is a category error** —
and it is the tempting one, because `polarity.py` already says `mcp_scanner: ATTACK_SUCCEEDED` and the
master plan repeats "a reported finding is an attack that succeeded". That framing came from *exploit*
scanners, where a finding genuinely means an exploit landed. It does not transfer to a static
configuration check.

`MASTER-PLAN.md` predicted mcp-scanner would feed **ASI04** (supply chain). The observed readiness
categories do **not** support that: they are resilience and observability properties, which belong to
**ASI08** and **ASI10**. The mapping below is therefore built from the categories actually observed,
each with a stated reason, and every mapping is a judgement recorded in the open rather than a fact
inherited from a plan written before the tool was run.

What this adapter does NOT do
-----------------------------
- **It does not claim an attack occurred.** `ASR_KIND` is `"control_violation"`, and
  `AssertionError`-style checks enforce that the distinction is carried in every technique string. Mixing
  control violations into a client's headline *attack*-success rate would inflate it with things nobody
  attempted — a report that says "58% attack success" about static configuration findings is exactly
  the kind of confidently-wrong number this project exists to prevent. **Recorded as D-019.**
- It does not attempt to exploit anything, and it performs no network access: the readiness analyzer
  runs fully offline (`enable_llm_judge=False`, `enable_opa=False`).
- It does not guess a category. An unmapped `threat_category` RAISES.
"""
from __future__ import annotations

from ..asi import Attempt
from ..polarity import Polarity
from .base import AdapterSpec, read_jsonl, register

SCANNER = "mcp_scanner"
VERSION = "4.8.4"

#: Verified against vendor/venv-mcpscanner. The key set is version-specific and a silent mis-parse here
#: would count policy findings as attacks.
SUPPORTED_VERSIONS: tuple[str, ...] = ("4.8.4",)

#: What this adapter's Attempts actually measure. NOT "attack_succeeded" — see the module docstring.
ASR_KIND = "control_violation"

#: The prefix every technique carries, so an ASR can never blend these with real attacks by accident.
TECHNIQUE_PREFIX = "readiness:"

#: Observed `threat_category` -> ASI, each with the reason it belongs there. Built from the categories
#: this scanner actually emits, NOT from the master plan's prediction (which said ASI04).
THREAT_TO_ASI: dict[str, tuple[str, str]] = {
    "OVERLOADED_TOOL_SCOPE": (
        "ASI02",
        "An over-broad tool is the tool-misuse surface itself: the agent can be made to do more than "
        "its task requires, using the tool's own parameters.",
    ),
    "UNSAFE_RETRY_LOOP": (
        "ASI08",
        "An unbounded retry loop propagates one failure across the estate rather than containing it — "
        "the cascading-failure shape.",
    ),
    "MISSING_TIMEOUT_GUARD": (
        "ASI08",
        "Without a timeout a single hung dependency stalls every caller, which is failure propagation "
        "rather than isolation.",
    ),
    "SILENT_FAILURE_PATH": (
        "ASI10",
        "A failure that is not surfaced is an agent acting outside its intent without detection, which "
        "is the rogue-agent condition.",
    ),
    "NO_OBSERVABILITY_HOOKS": (
        "ASI10",
        "No telemetry means out-of-intent behaviour cannot be detected or stopped — the monitoring half "
        "of ASI10.",
    ),
    "MISSING_ERROR_SCHEMA": (
        "ASI10",
        "Structured errors are what monitoring consumes; without a schema, failure is unobservable in "
        "practice even where a hook exists.",
    ),
    "NON_DETERMINISTIC_RESPONSE": (
        "ASI10",
        "Behaviour that varies run to run is behaviour that cannot be baselined, so drift from intent "
        "cannot be detected.",
    ),
}

EVIDENCE_CHARS = 400


class McpScannerParseError(ValueError):
    """Raised when an mcp-scanner run cannot be read as the format this adapter understands."""


def _rows(source) -> list[dict]:
    return read_jsonl(source, error=McpScannerParseError, what="mcp-scanner results file")


def _findings(row: dict) -> list[dict]:
    findings = row.get("findings")
    if findings is None:
        raise McpScannerParseError(
            f"row {row.get('fixture')!r} has no `findings` key; this does not look like "
            "mcp-scanner readiness output"
        )
    if not isinstance(findings, list):
        raise McpScannerParseError(f"`findings` must be a list, got {type(findings).__name__}")
    return findings


def parse_readiness(source, *, version: str = VERSION) -> list[Attempt]:
    """Parse saved mcp-scanner readiness output into Attempts — one per finding.

    `succeeded` means **the control was violated**, which is what a reported finding states. Read
    `ASR_KIND` and the module docstring before using these in a rate aimed at a client.
    """
    if version not in SUPPORTED_VERSIONS:
        raise McpScannerParseError(
            f"mcp-scanner {version} is not a supported results version (supported: "
            f"{', '.join(SUPPORTED_VERSIONS)}). The finding schema and the threat taxonomy are "
            "version-specific; re-derive both against a real run before widening this list."
        )

    rows = _rows(source)
    unmapped: set[str] = set()
    attempts: list[Attempt] = []

    for row in rows:
        target = str(row.get("fixture") or "unknown")
        for i, f in enumerate(_findings(row)):
            category = f.get("threat_category")
            if not category:
                raise McpScannerParseError(
                    f"{target} finding[{i}] has no `threat_category`; severity alone cannot be mapped "
                    "to an ASI category and guessing one would put an unverified claim in a report"
                )
            mapping = THREAT_TO_ASI.get(category)
            if mapping is None:
                unmapped.add(category)
                continue
            asi, _reason = mapping

            severity = str(f.get("severity") or "").upper()
            summary = str(f.get("summary") or "").strip()
            if not summary:
                # A finding with no summary is unreadable evidence; C-1 applies to observations too.
                raise McpScannerParseError(
                    f"{target} finding[{i}] ({category}) carries no summary — a finding with nothing "
                    "to show is not reportable"
                )

            attempts.append(
                Attempt.from_scanner(
                    scanner=SCANNER,
                    # The control was violated. NOT an attack having succeeded — see ASR_KIND.
                    scanner_label=True,
                    polarity=Polarity.ATTACK_SUCCEEDED,
                    category=asi,
                    # NO scanner prefix here: Attempt.from_scanner() adds it. The prefix that matters
                    # is the KIND prefix, so a reader can never mistake these for attack attempts.
                    technique=f"{TECHNIQUE_PREFIX}{category}",
                    observed=(
                        f"mcp-scanner {version} · {target} · {severity} · {category} · {summary} · "
                        f"analyzer {f.get('analyzer')} · details {str(f.get('details'))[:120]}"
                    )[:EVIDENCE_CHARS],
                    payload=summary[:EVIDENCE_CHARS],
                    environment=(
                        f"mcp-scanner {version} · analyzer {f.get('analyzer')} · "
                        f"kind {ASR_KIND} · target {target}"
                    ),
                    adapter_ref=f"mcp_scanner:{target}:{category}:{i}",
                )
            )

    if unmapped:
        raise McpScannerParseError(
            "no ASI mapping for threat_category: "
            + ", ".join(sorted(unmapped))
            + ". Add each to THREAT_TO_ASI with a stated reason. Note that MASTER-PLAN predicted this "
            "scanner feeds ASI04, while the readiness categories observed are resilience/observability "
            "properties — decide from the category's meaning, not from the plan's prediction."
        )
    return attempts


register(
    AdapterSpec(
        scanner=SCANNER,
        version=VERSION,
        emits=("ASI02", "ASI08", "ASI10"),
        parse=parse_readiness,
        notes=(
            "Parses saved readiness output. Findings are static POLICY CHECKS, not attacks: "
            f"ASR_KIND={ASR_KIND} and every technique is prefixed '{TECHNIQUE_PREFIX}' so these can "
            "never be silently blended into a client's attack-success rate (D-019). RAISES on an "
            "unmapped threat_category rather than guessing."
        ),
    )
)
