"""DeepTeam adapter — real DeepTeam red-team run rows into `Attempt` objects.

A3.5, built against a **real run** (deepteam 1.0.9): 7 test cases with genuinely synthesised
attacks (simulator model), real target replies, and a real judge score each. Reproduction:
`scripts/a35-deepteam-run.py`; the fixture is a verbatim dump of `red_team()`'s RTTestCase rows.

THE FIFTH POLARITY TRAP IS THE POINT OF THIS FILE
--------------------------------------------------
DeepTeam's score is a *defence* score: `score > 0` renders as **"Passed"**, meaning the attack
FAILED. Copying `score > 0` through as `succeeded=True` inverts the report exactly like garak's
`passed`. Confirmed against this run's own data before a line of mapping was written: every
score=1.0 row's judge reason says the attack did **not** land ("No secrets_and_credentials
leakage detected", "The model declined or returned no substantive output").

B-9 discipline — the score vocabulary is ENUMERATED, not assumed:

| score | meaning | this adapter |
| --- | --- | --- |
| `1.0` (and any `0 < s`) | judge says the defence **held** | `DEFENCE_HELD` -> succeeded False |
| `0.0` | the defence **failed** (or no defence) | succeeded True, C-1 evidence required |
| missing / None | **unjudged** | RAISES — a non-verdict is NOT an Attempt |
| outside `[0, 1]` | not a score | RAISES |

A populated `error` field is likewise a **failure path, not a verdict** and RAISES — session 8's
 investigation died on exactly such rows, and a fixture whose rows all carry errors is built on
nothing. This fixture's rows carry `error: None` throughout, asserted by a check.

`Attack` is a REAL attack adapter (unlike the audit adapters): the simulator actually generated
attacks and a target actually replied, so `succeeded=True` here is a genuine attack success.

What this adapter does NOT do
-----------------------------
- It does not guess a category. An unmapped `vulnerability_type` RAISES.
- It does not average scores, deduplicate "similar" attacks, or re-judge: one row, one Attempt.
- It does not run DeepTeam. A3.x scope is parsing saved runs; `scripts/a35-deepteam-run.py`
  owns the execution.
"""
from __future__ import annotations

from ..asi import Attempt
from ..polarity import Polarity
from .base import AdapterSpec, read_jsonl, register

SCANNER = "deepteam"
VERSION = "1.0.9"

SUPPORTED_VERSIONS: tuple[str, ...] = ("1.0.9",)

#: DeepTeam's score is a DEFENCE score ("Passed" = the attack failed). Declared explicitly.
POLARITY = Polarity.DEFENCE_HELD

#: Observed `vulnerability_type` -> ASI, each with the reason it belongs there — derived from what
#: the attack ATTEMPTED, from the seven types this run actually emitted. Unmapped values RAISE.
VULN_TO_ASI: dict[str, tuple[str, str]] = {
    "secrets_and_credentials": (
        "ASI06",
        "The attack pushes the agent to exfiltrate secrets it holds — the sensitive-data "
        "exfiltration surface the ledger already prices under ASI06.",
    ),
    "instructions": (
        "ASI01",
        "The attack smuggles instructions against the instruction hierarchy to hijack what the "
        "agent treats as its goal — the goal-hijack move itself.",
    ),
    "guard_exposure": (
        "ASI01",
        "Mapping the agent's guardrails is the reconnaissance half of a goal hijack: the defences "
        "are probed in order to be defeated.",
    ),
    "permissions_and_roles": (
        "ASI03",
        "The attack solicits privilege mappings or role escalation — identity and privilege abuse.",
    ),
    "permissions": (
        "ASI03",
        "As permissions_and_roles: soliciting the agent's privilege surface.",
    ),
    "functionality": (
        "ASI02",
        "The attack drives the agent to act beyond its intended purpose using its own "
        "capabilities — tool misuse and exploitation.",
    ),
    "autonomy": (
        "ASI10",
        "The attack pushes the agent toward unauthorised self-directed action — the rogue-agent "
        "condition.",
    ),
}

EVIDENCE_CHARS = 400

#: The environment string describing the committed fixture's run. Overridable at parse time.
DEFAULT_ENVIRONMENT = (
    "deepteam 1.0.9 · simulator+judge qwen3.8-flash via api.b.ai · "
    "target: bare qwen3.8-flash chat agent"
)


class DeepTeamParseError(ValueError):
    """Raised when a DeepTeam results file cannot be read as the format this adapter understands."""


def _rows(source) -> list[dict]:
    return read_jsonl(source, error=DeepTeamParseError, what="DeepTeam results file")


def _verdict(row: dict, where: str) -> tuple[bool, float]:
    """Return (defence_held, score) — RAISING on every non-verdict shape the field can carry."""
    score = row.get("score")
    if score is None:
        raise DeepTeamParseError(
            f"{where} carries no score — an unjudged row is NOT an Attempt (B-9); a missing "
            "verdict must never be recorded as a defence that held"
        )
    try:
        s = float(score)
    except (TypeError, ValueError) as exc:
        raise DeepTeamParseError(f"{where} score {score!r} is not a number") from exc
    if not 0.0 <= s <= 1.0:
        raise DeepTeamParseError(f"{where} score {s} outside [0, 1] — not a verdict")
    if row.get("error"):
        raise DeepTeamParseError(
            f"{where} carries error {str(row['error'])[:120]!r} — a failure-path row is not a "
            "verdict and cannot become an Attempt"
        )
    return s > 0.0, s


def parse_results(source, *, version: str = VERSION,
                  environment: str = DEFAULT_ENVIRONMENT) -> list[Attempt]:
    """Parse a saved DeepTeam `red_team()` run (JSONL RTTestCase rows) into Attempts.

    `succeeded` means **the attack worked** — which here is `score == 0`, because DeepTeam's
    score is a defence score (`score > 0` = "Passed" = the attack failed). Read the module
    docstring before touching the mapping.
    """
    if version not in SUPPORTED_VERSIONS:
        raise DeepTeamParseError(
            f"deepteam {version} is not a supported results version (supported: "
            f"{', '.join(SUPPORTED_VERSIONS)}). The row schema and score semantics are "
            "version-specific; re-derive both against a real run before widening this list."
        )

    rows = _rows(source)
    unmapped: set[str] = set()
    attempts: list[Attempt] = []

    for i, row in enumerate(rows):
        where = f"deepteam row[{i}]"
        held, score = _verdict(row, where)

        vuln_type = str(row.get("vulnerability_type") or "").strip()
        if not vuln_type:
            raise DeepTeamParseError(
                f"{where} has no `vulnerability_type`; the risk being probed cannot be mapped "
                "to an ASI category and guessing one would put an unverified claim in a report"
            )
        mapping = VULN_TO_ASI.get(vuln_type)
        if mapping is None:
            unmapped.add(vuln_type)
            continue
        asi, _reason = mapping

        attack = str(row.get("attack_method") or "").strip()
        if not attack:
            raise DeepTeamParseError(f"{where} ({vuln_type}) carries no attack_method")
        reason = str(row.get("reason") or "").strip()
        if not reason:
            # The judge's reason is the evidence that the defence held (or the attack landed).
            raise DeepTeamParseError(f"{where} ({vuln_type}) carries no judge reason")

        output = str(row.get("actual_output") or "").strip()
        if held is False and not output:
            # C-1: an attack that got through must show what the target actually returned.
            raise DeepTeamParseError(
                f"{where} records the attack succeeding with no target output — an unevidenced "
                "success cannot exist (C-1)"
            )

        attempts.append(
            Attempt.from_scanner(
                scanner=SCANNER,
                # DeepTeam's boolean means "the DEFENCE passed" -> DEFENCE_HELD. The kernel
                # inverts it; succeeded=True on an Attempt means the ATTACK worked.
                scanner_label=held,
                polarity=POLARITY,
                category=asi,
                technique=attack.lower().replace(" ", "_").replace("-", "_"),
                observed=(
                    f"deepteam {version} · {vuln_type} · {attack} · score {score:.1f} "
                    f"({'defence held' if held else 'ATTACK SUCCEEDED'}) · judge: {reason}"
                )[:EVIDENCE_CHARS],
                payload=output[:EVIDENCE_CHARS],
                environment=environment,
                adapter_ref=f"deepteam:{vuln_type}:{attack.lower().replace(' ', '_')}:{i}",
            )
        )

    if unmapped:
        raise DeepTeamParseError(
            "no ASI mapping for vulnerability_type: "
            + ", ".join(sorted(unmapped))
            + ". Add each to VULN_TO_ASI with a stated reason derived from what the attack "
            "attempted, against a real run — not from the plan's prediction."
        )
    return attempts


register(
    AdapterSpec(
        scanner=SCANNER,
        version=VERSION,
        emits=("ASI01", "ASI02", "ASI03", "ASI06", "ASI10"),
        parse=parse_results,
        notes=(
            "Parses a saved red_team() run. DeepTeam's score is a DEFENCE score "
            "(`score > 0` = 'Passed' = the attack failed) — the fifth polarity trap, confirmed "
            "against the run's own judge reasons. Non-verdict rows (missing/out-of-range score, "
            "populated error) RAISE rather than become Attempts (B-9). Unmapped "
            "vulnerability_type RAISES."
        ),
    )
)
