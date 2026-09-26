"""PyRIT adapter — a PyRIT run's `AttackResult` rows into `Attempt` objects.

PyRIT is the multi-turn / crescendo depth scanner, which is where real agentic compromise tends to live
(ASI01, ASI06, ASI09). This module parses a **saved real run**, following the A3.1 method: every claim
below was observed by executing PyRIT 1.1.0, not read from its documentation.

The trap this adapter exists for — and it is a THIRD kind
--------------------------------------------------------
`kessler/polarity.py` handles scanners that disagree about what `true` means. PyRIT adds a different
problem: **`outcome` has four values, and only two of them are verdicts.**

| `AttackOutcome` | Meaning | Is it a verdict? |
| --- | --- | --- |
| `success` | the attack achieved its objective | **yes** — attack succeeded |
| `failure` | the objective was not achieved | **yes** — attack did not succeed |
| `undetermined` | **no objective scorer was configured** | **NO** |
| `error` | the attack itself errored | **NO** |

Observed in the reference run: with no scorer, PyRIT returns `undetermined` with the reason *"No
objective scorer configured"*, and `last_score` is `null`. The naive adapter —
`succeeded = (outcome == "success")` — maps both non-verdicts to **False**, i.e. it counts an unjudged
attempt as a **defence that held**. That understates the attack-success rate in exactly the direction
that flatters a client's system, and nothing downstream can detect it: the report renders, the ASR
computes, and the number is quietly low.

**Rule here: a non-verdict is not an Attempt.** `error` and `undetermined` cause the parse to RAISE,
naming how many rows and why. They are not silently dropped (which would shrink the denominator) and
never counted as failures (which would inflate defence). The operator must score the run or exclude it
deliberately — the same "fail loudly, never guess" discipline as the polarity guard itself.

Other real observations from the reference run
----------------------------------------------
- **Polarity confirmed from data:** `outcome == "success"` with `last_score.score_value == true` and the
  reason *"Objective achieved according to scorer"*. So `ATTACK_SUCCEEDED` is correct for PyRIT, matching
  the registry — the opposite of garak's `eval.passed`.
- The evidence for a success lives in **`last_response.converted_value`** (the target's actual reply).
  `last_score.score_rationale` is the scorer's justification. Both are captured into `observed`.
- `last_score` is `null` whenever no scorer ran — so an adapter must not assume it exists.
- `attack_result_id` is the natural `adapter_ref`.

Objective -> ASI mapping is EXPLICIT and required
-------------------------------------------------
PyRIT objectives are free text chosen by the operator, so there is no data-driven way to infer a
category, and guessing one would put an unverified claim in a client deliverable. The caller supplies
`objective_map`; an unmapped objective RAISES.
"""
from __future__ import annotations

from ..asi import Attempt
from ..polarity import Polarity
from .base import AdapterSpec, read_jsonl, register

SCANNER = "pyrit"
VERSION = "1.1.0"

#: Verified against vendor/venv-pyrit. Another version refuses: the outcome vocabulary is version-specific
#: and a silent mis-parse here is a wrong ASR.
SUPPORTED_VERSIONS: tuple[str, ...] = ("1.1.0",)

#: AttackOutcome values that ARE verdicts about the attack.
VERDICT_OUTCOMES: dict[str, bool] = {
    "success": True,     # the attack achieved its objective
    "failure": False,    # it did not
}

#: AttackOutcome values that are NOT verdicts. Presence of any of these fails the parse.
NON_VERDICT_OUTCOMES: tuple[str, ...] = ("undetermined", "error")

EVIDENCE_CHARS = 400


class PyritParseError(ValueError):
    """Raised when a PyRIT run cannot be read as the format this adapter understands."""


class PyritNoVerdict(ValueError):
    """Raised when rows carry no verdict. An unjudged attempt is not an Attempt."""


def _rows(source) -> list[dict]:
    return read_jsonl(source, error=PyritParseError, what="PyRIT results file")


def _outcome(row: dict) -> str:
    value = row.get("outcome")
    if value is None:
        raise PyritParseError(
            f"AttackResult {row.get('attack_result_id')!r} has no `outcome` field; "
            "this does not look like a PyRIT AttackResult"
        )
    if not isinstance(value, str):
        raise PyritParseError(f"`outcome` must be a string, got {type(value).__name__}: {value!r}")
    return value.strip().lower()


def _scorer_name(score: dict) -> str:
    """A short readable scorer name. The raw identifier is a nested dict, not a label."""
    ident = score.get("scorer_class_identifier")
    if isinstance(ident, dict):
        return str(ident.get("class_name") or ident.get("name") or "scorer")
    return str(ident or "scorer")


def _evidence(row: dict) -> str:
    """The target's reply and the scorer's verdict — most meaningful first.

    Ordering matters because the result is truncated for the report. The first version put the raw
    scorer identifier (a nested dict repr, ~200 chars) before the scorer's *value* and the outcome
    reason, so truncation discarded the human-readable verdict and kept the noise. The verdict is the
    point; the class name is a detail.
    """
    parts: list[str] = []
    resp = row.get("last_response")
    if isinstance(resp, dict):
        text = resp.get("converted_value") or resp.get("original_value")
        if text:
            parts.append(str(text))
        if resp.get("response_error") and resp["response_error"] != "none":
            parts.append(f"[response_error: {resp['response_error']}]")
    score = row.get("last_score")
    if isinstance(score, dict):
        parts.append(
            f"[scorer {_scorer_name(score)} = {score.get('score_value')}"
            + (f": {score['score_rationale']}" if score.get("score_rationale") else "")
            + "]"
        )
    reason = row.get("outcome_reason")
    if reason:
        parts.append(f"[outcome_reason: {reason}]")
    return " · ".join(parts).strip()


def parse_results(source, *, objective_map: dict[str, str], version: str = VERSION) -> list[Attempt]:
    """Parse saved PyRIT `AttackResult` rows into Attempts, one per row.

    `objective_map` maps a PyRIT objective string to an ASI category. It is REQUIRED: PyRIT objectives
    are free text chosen by the operator, so an unmapped one raises rather than being guessed.
    """
    if version not in SUPPORTED_VERSIONS:
        raise PyritParseError(
            f"PyRIT {version} is not a supported results version (supported: "
            f"{', '.join(SUPPORTED_VERSIONS)}). Re-derive the outcome vocabulary against a real run of "
            "the new version before widening this list — a silent mis-parse is worse than a refusal."
        )

    rows = _rows(source)

    no_verdict: list[str] = []
    unmapped: set[str] = set()
    attempts: list[Attempt] = []

    for row in rows:
        outcome = _outcome(row)
        if outcome in NON_VERDICT_OUTCOMES:
            no_verdict.append(f"{row.get('attack_result_id')} ({outcome}: {row.get('outcome_reason')})")
            continue
        if outcome not in VERDICT_OUTCOMES:
            raise PyritParseError(
                f"unknown PyRIT outcome {outcome!r} on {row.get('attack_result_id')!r}; expected one of "
                f"{', '.join(list(VERDICT_OUTCOMES) + list(NON_VERDICT_OUTCOMES))}. An unrecognised "
                "outcome must never be assumed to mean the target defended."
            )

        objective = str(row.get("objective") or "").strip()
        if not objective:
            raise PyritParseError(f"AttackResult {row.get('attack_result_id')!r} has no `objective`")

        category = objective_map.get(objective)
        if category is None:
            unmapped.add(objective)
            continue

        succeeded = VERDICT_OUTCOMES[outcome]
        evidence = _evidence(row)
        if succeeded and not evidence.strip():
            # C-1 at the adapter boundary: a success with nothing to show is not reportable.
            raise PyritParseError(
                f"AttackResult {row.get('attack_result_id')!r} succeeded but carries no response or "
                "scorer rationale — an unevidenced success is a claim"
            )

        attempts.append(
            Attempt.from_scanner(
                scanner=SCANNER,
                scanner_label=succeeded,
                # Confirmed from real output: outcome 'success' means the ATTACK worked. The registry
                # already says ATTACK_SUCCEEDED for pyrit; stated explicitly here so a reader of this
                # adapter does not have to go and check.
                polarity=Polarity.ATTACK_SUCCEEDED,
                category=category,
                # NO "pyrit:" prefix here — Attempt.from_scanner() adds the scanner prefix itself, and
                # prefixing twice produced "pyrit:pyrit:..." (caught by a check on the technique shape).
                technique=row.get("outcome_reason") or outcome,
                observed=evidence[:EVIDENCE_CHARS] if succeeded else "",
                payload=objective[:EVIDENCE_CHARS],
                environment=(
                    f"pyrit {version} · turns {row.get('executed_turns')} · "
                    f"outcome {outcome} · {row.get('execution_time_ms')}ms"
                ),
                adapter_ref=f"pyrit:{row.get('attack_result_id')}",
            )
        )

    if unmapped:
        raise PyritParseError(
            "no ASI mapping for objective(s): "
            + "; ".join(repr(o[:70]) for o in sorted(unmapped))
            + ". Pass them in objective_map with a stated reason. Guessing a category would put an "
            "unverified claim in a client deliverable."
        )

    if no_verdict:
        raise PyritNoVerdict(
            f"{len(no_verdict)} of {len(rows)} row(s) carry NO VERDICT, so they are not attempts: "
            + "; ".join(no_verdict)
            + ". `undetermined` means no objective scorer was configured and `error` means the attack "
            "errored — neither is a defence that held. Count them as failures and the attack-success "
            "rate is understated in the client's favour; drop them silently and the denominator shrinks. "
            "Configure an objective scorer and re-run, or exclude the rows deliberately."
        )

    if not attempts:
        raise PyritParseError("the run produced no attempts")
    return attempts


register(
    AdapterSpec(
        scanner=SCANNER,
        version=VERSION,
        emits=("ASI01", "ASI06", "ASI09"),
        parse=parse_results,
        notes=(
            "Parses saved AttackResult rows. Requires objective_map: PyRIT objectives are operator "
            "chosen free text, so a category cannot be inferred. RAISES on `undetermined` and `error` "
            "rows — they are not verdicts, and counting them as defences understates risk."
        ),
    )
)
