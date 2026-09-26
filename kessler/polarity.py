"""Polarity: the single most dangerous silent error in this codebase.

The trap
--------
Different scanners report *opposite* things under the same-looking field name:

| Scanner   | Field        | True means                    |
| --------- | ------------ | ----------------------------- |
| garak     | `passed`     | the ATTACK FAILED (target defended) |
| DeepTeam  | `score > 0`  | "Passed" = the MODEL DEFENDED      |
| promptfoo | `pass: true` | the target REFUSED (attack failed)  |
| PyRIT     | `outcome`    | `success` = the ATTACK SUCCEEDED    |

Copying a scanner's boolean straight into our `succeeded` field inverts the finding, and the failure
is silent: the report renders, the ASR table computes, and it says **0% attack success** for a system
that is fully compromised. A number that is confidently wrong about the one thing the client paid for.

The fix
-------
An adapter may not hand us a boolean. It must hand us the scanner's own label plus an explicit
declaration of what that label means. Conversion is then a pure function in one place, tested, so no
adapter can invent its own convention.

ponytail: two polarities cover every scanner surveyed in docs/research/01. If a third appears, add a
member here rather than letting an adapter special-case it.
"""
from __future__ import annotations

from enum import Enum


class Polarity(str, Enum):
    """What a scanner's TRUE/success label means about the ATTACK.

    Naming is deliberately about the attack, never about the scanner's own vocabulary, because the
    scanner's vocabulary is what misleads.
    """

    #: True/success means the attack worked. (PyRIT `outcome == "success"`.)
    ATTACK_SUCCEEDED = "attack_succeeded"

    #: True/success means the attack FAILED because the target defended itself.
    #: (garak `passed`, DeepTeam `score > 0` == "Passed", promptfoo `pass: true`.)
    DEFENCE_HELD = "defence_held"


class PolarityError(ValueError):
    """Raised when a scanner label cannot be converted. Never guessed."""


#: The scanner -> polarity mapping, verified against each tool's actual output in
#: docs/research/01-scanner-tool-ecosystem.md. Kept here so the table is reviewable in one glance.
KNOWN_SCANNER_POLARITY: dict[str, Polarity] = {
    "pyrit": Polarity.ATTACK_SUCCEEDED,
    "garak": Polarity.DEFENCE_HELD,
    "deepteam": Polarity.DEFENCE_HELD,
    "promptfoo": Polarity.DEFENCE_HELD,
    "mcp_audit": Polarity.ATTACK_SUCCEEDED,   # a reported finding is an attack that succeeded
    "mcp_scanner": Polarity.ATTACK_SUCCEEDED,
    "ai_infra_guard": Polarity.ATTACK_SUCCEEDED,
}


def polarity_for(scanner: str) -> Polarity:
    """Look up a known scanner's polarity.

    Unknown scanners MUST be declared explicitly by their adapter rather than assumed — an assumed
    polarity is exactly how the inversion happens.
    """
    key = (scanner or "").strip().lower()
    try:
        return KNOWN_SCANNER_POLARITY[key]
    except KeyError as exc:
        raise PolarityError(
            f"unknown scanner {scanner!r} has no declared polarity. "
            f"Known: {', '.join(sorted(KNOWN_SCANNER_POLARITY))}. "
            "An adapter for a new scanner must declare its polarity explicitly — guessing it "
            "silently inverts the report."
        ) from exc


def attack_succeeded(scanner_label: bool, polarity: Polarity) -> bool:
    """Convert a scanner's own boolean into 'did the ATTACK succeed'.

    This is the only place that conversion happens. `polarity` may be a `Polarity` or its string
    value; an unrecognised value raises rather than falling through to a default.
    """
    if not isinstance(scanner_label, bool):
        raise PolarityError(
            f"scanner label must be a bool, got {type(scanner_label).__name__}. "
            "If the scanner returns a string verdict, map it to a bool in the adapter first."
        )
    if isinstance(polarity, str):
        try:
            polarity = Polarity(polarity)
        except ValueError as exc:
            raise PolarityError(
                f"unknown polarity {polarity!r}; expected one of "
                f"{', '.join(p.value for p in Polarity)}"
            ) from exc
    if polarity is Polarity.ATTACK_SUCCEEDED:
        return scanner_label
    return not scanner_label
