"""AI-Infra-Guard adapter — Tencent AIG's mcp_scan findings into `Attempt` objects.

A3.3, built against a **real run**: AI-Infra-Guard v4.6.1 deployed from its official release
(data bundle + docker-compose; the release ships no binary — B-11) and executed against real
source via its task API. Two real result documents are committed as fixtures: a clean MCP server
(0 findings, score 100) and a deliberately-vulnerable probe (3 findings, score 0).

A FIFTH structural variant: a score, a note, and findings — no verdict field per finding
------------------------------------------------------------------------------------------
garak has `passed`, PyRIT has `outcome`, mcp-scanner has nothing at all, DeepTeam has a score.
AIG's result carries a *document-level* score (0-100) plus a `results` list whose entries have
exactly this key set, observed:

    description · file · level · line_end · line_start · risk_type · suggestion · title

No per-finding boolean exists. As with mcp-scanner (D-019), the signal is the **existence of a
finding object**: the same deployment that flags 3 planted vulnerabilities in the probe returns
**0 findings** for a clean server, so counting objects is trustworthy here.

THE SEMANTIC RULE CARRIES OVER FROM D-019
------------------------------------------
`mcp_scan` is a static + LLM-assisted **code audit** of MCP server source. Nobody attacked
anything. Calling a Critical code-audit finding "the attack succeeded" is the category error
D-019 exists for, so this adapter declares `ASR_KIND = "control_violation"` and prefixes every
technique with `audit:` — these Attempts can never silently blend into a client's attack-success
rate. Recorded as D-021.

Version is NOT in the payload
-----------------------------
The result document carries no AIG version. The version below is the **deployed release tag**
verified against the running containers. It is a parameter, defaulted, not guessed from the file:
a result from a different AIG release must be re-derived before this list widens.

What this adapter does NOT do
-----------------------------
- It does not claim an attack occurred (see D-021).
- It refuses a result whose `scanNote` is not `complete`: an incomplete scan that emitted some
  findings would understate what a full scan would have caught.
- It does not guess a category. An unmapped `risk_type` RAISES.
- The document-level `score` is decoration and is ignored: ASR maths live in `kessler/asi.py`.
"""
from __future__ import annotations

import html
import json
from pathlib import Path

from ..asi import Attempt
from ..polarity import Polarity
from .base import AdapterSpec, register

SCANNER = "ai_infra_guard"
VERSION = "4.6.1"

#: Verified against the v4.6.1 release deployment. Version-specific: the result schema and the
#: risk_type vocabulary are the scanner's, and a silent mis-parse would count audit findings as attacks.
SUPPORTED_VERSIONS: tuple[str, ...] = ("4.6.1",)

#: NOT "attack_succeeded" — see the module docstring and D-021.
ASR_KIND = "control_violation"

#: The prefix every technique carries, so an ASR can never blend these with real attacks by accident.
TECHNIQUE_PREFIX = "audit:"

#: Observed `risk_type` -> ASI, each with the reason it belongs there. Built from the risk types the
#: scanner actually emitted, each a judgement recorded in the open. Unmapped values RAISE.
RISK_TYPE_TO_ASI: dict[str, tuple[str, str]] = {
    "MCP05 (Command Injection & Execution)": (
        "ASI05",
        "A tool whose model-controlled parameter reaches a shell or interpreter is the "
        "unexpected-code-execution surface itself: the agent's own tool becomes the RCE vector.",
    ),
    "CWE-22: Path Traversal / Arbitrary File Read": (
        "ASI02",
        "A read tool with unconstrained paths lets the agent be directed past its task's file "
        "scope using the tool's own parameters — tool misuse and exploitation.",
    ),
}

#: risk_type strings arrive HTML-escaped in real output ("&amp;" for "&"); normalised before mapping.

EVIDENCE_CHARS = 400

#: The only scan state this adapter accepts.
SCAN_COMPLETE = "complete"


class AiInfraGuardParseError(ValueError):
    """Raised when an AIG result cannot be read as the format this adapter understands."""


def _document(source) -> dict:
    """Load the saved HTTP response body of AIG's result endpoint (a single JSON object)."""
    if isinstance(source, dict):
        return source
    if isinstance(source, (str, Path)):
        p = Path(source)
        raw = p.read_text(encoding="utf-8", errors="replace") if p.exists() else str(source)
        try:
            doc = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise AiInfraGuardParseError(
                f"{p if p.exists() else 'input'} is not valid JSON ({exc.msg}); "
                "the adapter expects the result endpoint's response body"
            ) from exc
    else:
        raise AiInfraGuardParseError(
            f"unsupported source type {type(source).__name__}; pass a path, JSON string or dict"
        )
    if not isinstance(doc, dict):
        raise AiInfraGuardParseError("expected a JSON object, got a list/scalar")
    return doc


def _result(doc: dict) -> dict:
    data = doc.get("data")
    if not isinstance(data, dict):
        raise AiInfraGuardParseError(
            "no `data` object — this is not AIG's result-endpoint response body"
        )
    result = data.get("result")
    if not isinstance(result, dict):
        raise AiInfraGuardParseError(
            "`data.result` is missing or not an object; the response may be a status body, "
            "not a result body"
        )
    note = result.get("scanNote")
    if note != SCAN_COMPLETE:
        raise AiInfraGuardParseError(
            f"scanNote is {note!r}, not {SCAN_COMPLETE!r} — an incomplete scan must not be parsed"
        )
    findings = result.get("results")
    if not isinstance(findings, list):
        raise AiInfraGuardParseError("`data.result.results` is missing or not a list")
    return result


def _risk_type(finding: dict, where: str) -> str:
    risk_type = str(finding.get("risk_type") or "").strip()
    if not risk_type:
        raise AiInfraGuardParseError(
            f"{where} carries no `risk_type`; severity or title alone cannot be mapped to an "
            "ASI category and guessing one would put an unverified claim in a report"
        )
    return html.unescape(risk_type)


def parse_result(source, *, version: str = VERSION) -> list[Attempt]:
    """Parse a saved AIG result-endpoint response into Attempts — one per finding.

    `succeeded` means **the control was violated** (a vulnerability exists in the audited source),
    which is what a reported finding states. Read `ASR_KIND` and the module docstring before using
    these in a rate aimed at a client.
    """
    if version not in SUPPORTED_VERSIONS:
        raise AiInfraGuardParseError(
            f"AI-Infra-Guard {version} is not a supported result version (supported: "
            f"{', '.join(SUPPORTED_VERSIONS)}). The result schema and risk_type vocabulary are "
            "version-specific; re-derive both against a real run before widening this list."
        )

    doc = _document(source)
    result = _result(doc)
    findings = result["results"]
    llm = str(result.get("llm") or "unknown-model")

    unmapped: set[str] = set()
    attempts: list[Attempt] = []

    for i, f in enumerate(findings):
        if not isinstance(f, dict):
            raise AiInfraGuardParseError(f"results[{i}] is not an object")
        where = f"AIG results[{i}]"
        risk_type = _risk_type(f, where)

        mapping = RISK_TYPE_TO_ASI.get(risk_type)
        if mapping is None:
            unmapped.add(risk_type)
            continue
        asi, _reason = mapping

        title = str(f.get("title") or "").strip()
        if not title:
            # A finding with no title is unreadable evidence; C-1 applies to observations too.
            raise AiInfraGuardParseError(
                f"{where} ({risk_type}) carries no title — a finding with nothing to show is "
                "not reportable"
            )
        level = str(f.get("level") or "unknown").upper()
        file = str(f.get("file") or "unknown")
        span = f"{file}:{f.get('line_start', '?')}-{f.get('line_end', '?')}"
        description = str(f.get("description") or "").strip()

        attempts.append(
            Attempt.from_scanner(
                scanner=SCANNER,
                # The control was violated. NOT an attack having succeeded — see ASR_KIND / D-021.
                scanner_label=True,
                polarity=Polarity.ATTACK_SUCCEEDED,
                category=asi,
                # NO scanner prefix here: Attempt.from_scanner() adds it. The KIND prefix is what
                # keeps these separable from real attacks in any rollup.
                technique=f"{TECHNIQUE_PREFIX}{risk_type}",
                observed=(
                    f"AI-Infra-Guard {version} · {span} · {level} · {risk_type} · {title} · "
                    f"{description}"
                )[:EVIDENCE_CHARS],
                payload=(title if title else description)[:EVIDENCE_CHARS],
                environment=(
                    f"AI-Infra-Guard {version} · mcp_scan · judge {llm} · doc score "
                    f"{result.get('score')} (ignored) · kind {ASR_KIND}"
                ),
                adapter_ref=f"ai_infra_guard:{file}:{risk_type}:{i}",
            )
        )

    if unmapped:
        raise AiInfraGuardParseError(
            "no ASI mapping for risk_type: "
            + ", ".join(sorted(unmapped))
            + ". Add each to RISK_TYPE_TO_ASI with a stated reason, derived from the category's "
            "meaning against a real run — not from the plan's prediction."
        )
    return attempts


register(
    AdapterSpec(
        scanner=SCANNER,
        version=VERSION,
        emits=("ASI02", "ASI05"),
        parse=parse_result,
        notes=(
            "Parses the saved result-endpoint response body. Findings are static CODE-AUDIT "
            f"results, not attacks: ASR_KIND={ASR_KIND} and every technique is prefixed "
            f"'{TECHNIQUE_PREFIX}' so these can never be silently blended into a client's "
            "attack-success rate (D-021). RAISES on an unmapped risk_type and on an incomplete "
            "scan rather than guessing."
        ),
    )
)
