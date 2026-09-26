"""The adapter seam: one scanner in, `Attempt` objects out.

An adapter converts **one** scanner's native output into `Attempt` objects. Nothing downstream knows
which scanner produced an attempt, which is what makes swapping a scanner a one-file change.

Two rules bind every adapter, and both exist because breaking them fails *silently*:

1. **An adapter may not hand the kernel a boolean.** Scanners disagree about what `true` means —
   garak's `passed` means the attack FAILED while PyRIT's `outcome == "success"` means it worked.
   Copying a boolean straight through inverts the report and nothing downstream can catch it. Every
   adapter must go through `Attempt.from_scanner(...)` and **declare what its label means**.
2. **An adapter never computes ASR and never writes prose.** Measurement is single-sourced in
   `kessler/asi.py`; the report generator owns the words. An adapter that formats a finding has
   duplicated a decision that must live in one place.

Everything else — which fields to read, which entries to skip — is the adapter's business, and it
should be documented in the adapter itself, because that is where the real format traps live.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


class AdapterError(ValueError):
    """Raised when an adapter cannot be resolved or a scanner's format is not understood."""


@dataclass(frozen=True)
class AdapterSpec:
    """What a scanner adapter declares about itself."""

    scanner: str
    version: str
    emits: tuple[str, ...]
    parse: object  # callable(source, **kwargs) -> list[Attempt]
    notes: str = ""


#: Registered adapters, keyed by scanner name. Populated at import of each adapter module.
REGISTRY: dict[str, AdapterSpec] = {}


def register(spec: AdapterSpec) -> AdapterSpec:
    """Register an adapter. A duplicate scanner name is an error, not an overwrite.

    A silent overwrite would let two adapters claim the same scanner, so the one that ran last would
    win invisibly — exactly the class of failure this codebase refuses everywhere else.
    """
    if spec.scanner in REGISTRY:
        raise AdapterError(
            f"scanner {spec.scanner!r} is already registered by "
            f"{REGISTRY[spec.scanner].version!r}; refusing to overwrite"
        )
    REGISTRY[spec.scanner] = spec
    return spec


def read_jsonl(source, *, error, what: str) -> list[dict]:
    """Read a scanner's JSONL output, failing loudly **with the offending raw line**.

    Single-sourced because this is the anti-silent-skip guarantee every adapter depends on: a parser
    that quietly drops an unreadable line drops a finding with it, and nothing downstream can tell a
    short list from a complete one. Two adapters copying this logic would eventually differ in exactly
    the case that matters.

    `source` is a path or an iterable of lines. `error` is the adapter's own exception type — adapters
    keep distinct types so a caller can catch the scanner it is actually dealing with — and `what`
    names the expected artefact **without an article** ("garak report"), so the messages read correctly.
    """
    if isinstance(source, (str, Path)):
        p = Path(source)
        if not p.exists():
            raise error(f"no such {what}: {p}")
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    else:
        lines = list(source)

    out: list[dict] = []
    for n, line in enumerate(lines, 1):
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise error(
                f"line {n} is not valid JSON ({exc.msg}); raw line follows:\n{line[:300]}"
            ) from exc
    if not out:
        raise error(f"no JSONL entries found — not {what}")
    return out


def get(scanner: str) -> AdapterSpec:
    """Look up an adapter, failing loudly on an unknown scanner."""
    key = (scanner or "").strip().lower()
    try:
        return REGISTRY[key]
    except KeyError as exc:
        raise AdapterError(
            f"no adapter registered for scanner {scanner!r}; "
            f"available: {', '.join(sorted(REGISTRY)) or '(none)'}"
        ) from exc


def available() -> tuple[str, ...]:
    """Names of every registered adapter."""
    return tuple(sorted(REGISTRY))
