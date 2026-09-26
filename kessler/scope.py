"""Scope parsing: a signed scope file -> targets, exclusions, and the coverage denominator.

Why this module exists (step A2)
--------------------------------
C-7 says no request leaves the machine against a target without a **signed scope on disk**, and that
document is cited in every finding and in the attestation letter. So the scope is not paperwork — it is
the authorisation the whole engagement rests on. A2 turns it into the machine-readable target
inventory and exclusion list that the coverage denominator comes from.

The format decision (D-018), and why it is not YAML
--------------------------------------------------
`MASTER-PLAN.md` D1 recommended **`scope.yaml`**. Implementing it exposed a conflict with **C-2** (the
core stays stdlib-only, so it runs on a locked-down client laptop): **there is no YAML parser in the
standard library.** The options were:

1. add PyYAML — **rejected**: it is exactly the dependency C-2 exists to forbid, and it would put a
   third-party install between the client and their own authorisation document;
2. hand-roll a YAML subset — **rejected**: YAML's implicit typing (`no` -> False, `1.0` -> float,
   Norway problem) is a footgun, and a subtle mis-parse here would silently alter the scope;
3. **JSON, with TOML where the interpreter supports it — chosen.** `json` is stdlib everywhere and
   works at the project's declared floor (`requires-python = ">=3.10"`); `tomllib` is stdlib from 3.11
   and is accepted opportunistically because TOML is far nicer to hand-write.

The hash is computed, never typed
---------------------------------
`scope_sha256` is the SHA-256 of the **scope file's actual bytes**, computed on load. It is not a field
a human fills in, so it cannot be wrong. `verify_scope()` re-checks it later, which is what makes the
"C-7 signed scope on disk" claim checkable rather than asserted.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from .asi import ALL_IDS
from .schema import (  # private helpers reused deliberately: one validator, no drift
    Engagement,
    SchemaError,
    _fail,
    _iso_day,
    _obj,
    _str,
    validate_exclusions,
    validate_targets,
)

#: Keys a scope document must carry.
REQUIRED_KEYS: tuple[str, ...] = ("ref", "client", "window", "targets", "exclusions")

#: Keys it may carry. `note` is allowed so a human can annotate the file they are signing.
#: `testers` is allowed (and validated when present) so the engagement document the runner builds
#: can satisfy D-020's "testers named" without a second source of truth.
OPTIONAL_KEYS: tuple[str, ...] = ("note", "testers")


class ScopeError(ValueError):
    """A scope document this code will not accept. Raised before anything is applied."""


def scope_digest(data: bytes) -> str:
    """SHA-256 of a scope document's content, with line endings normalised to LF.

    **Line endings are a checkout artefact, not part of the document's identity.** Hashing the raw
    bytes makes the digest depend on whichever platform happened to materialise the file — CRLF on
    Windows, LF on Linux/macOS and in CI — so a hash computed on one machine silently fails to verify
    on another.

    This was a real defect, caught only when CI first ran on Linux (recorded as B-8): the example
    engagement's `scope_sha256` matched on the authoring machine and failed everywhere else. Since the
    digest travels into a client deliverable and is meant to be checkable by a third party, that is
    exactly the portability it cannot lose.

    The normalisation is CRLF/CR -> LF and nothing else: content is otherwise hashed byte-for-byte, so
    any real edit — including whitespace inside the document — still changes the digest.
    """
    return hashlib.sha256(data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")).hexdigest()


def _check_keys(doc: dict, path: str) -> None:
    """Required present, unknown refused. Unknown keys are drift, not something to ignore."""
    missing = [k for k in REQUIRED_KEYS if k not in doc]
    if missing:
        _fail(path, f"missing required key(s): {', '.join(missing)}")
    unknown = sorted(set(doc) - set(REQUIRED_KEYS) - set(OPTIONAL_KEYS))
    if unknown:
        _fail(
            path,
            f"unknown key(s): {', '.join(unknown)} — an unreadable field in an authorisation "
            "document is worse than a crash",
        )


@dataclass
class Scope:
    """A validated scope document. The authorisation an engagement rests on."""

    ref: str
    client: str
    start: str
    end: str
    scope_sha256: str
    targets: list[dict] = field(default_factory=list)
    exclusions: dict[str, str] = field(default_factory=dict)
    testers: list[str] = field(default_factory=list)
    note: str = ""
    source: str = ""

    def coverage_denominator(self) -> list[str]:
        """Every category that must be accounted for, tested or excluded with a reason."""
        return list(ALL_IDS)

    def to_engagement(self, attempts=(), findings=(), retest=None) -> Engagement:
        """Build the engagement document this scope authorises.

        The scope supplies ref, client, window, scope_sha256, targets and exclusions; the test run
        supplies attempts, findings and any retest.
        """
        return Engagement(
            ref=self.ref,
            client=self.client,
            start=self.start,
            end=self.end,
            scope_sha256=self.scope_sha256,
            targets=[dict(t) for t in self.targets],
            attempts=list(attempts),
            findings=list(findings),
            testers=list(self.testers),
            exclusions=dict(self.exclusions),
            retest=retest,
        )


def parse_scope(doc, *, digest: str, source: str = "") -> Scope:
    """Validate a decoded scope document. `digest` is the SHA-256 of the source bytes.

    Every failure surfaces as `ScopeError`, never as the underlying `SchemaError`: the shared
    validators raise the latter, and a caller catching the documented exception type must not have a
    different failure slip past it. One module, one error type.
    """
    try:
        _obj(doc, "$")
        _check_keys(doc, "$")
        window = _obj(doc["window"], "$.window")
        if set(window) != {"start", "end"}:
            _fail("$.window", f"expected exactly 'start' and 'end', got {sorted(window)}")
        return Scope(
            ref=_str(doc["ref"], "$.ref"),
            client=_str(doc["client"], "$.client"),
            start=_iso_day(window["start"], "$.window.start"),
            end=_iso_day(window["end"], "$.window.end"),
            scope_sha256=digest,
            targets=validate_targets(doc["targets"], "$.targets"),
            exclusions=validate_exclusions(doc["exclusions"], "$.exclusions"),
            testers=(
                [_str(t, f"$.testers[{i}]")
                 for i, t in enumerate(_list(doc["testers"], "$.testers"))]
                if "testers" in doc and doc["testers"] else []
            ),
            note=_str(doc.get("note", ""), "$.note", allow_empty=True),
            source=source,
        )
    except SchemaError as exc:
        raise ScopeError(str(exc)) from exc


def _decode(path: Path) -> dict:
    suffix = path.suffix.lower()
    raw = path.read_bytes()
    if suffix == ".json":
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ScopeError(f"{path.name}: not valid JSON ({exc.msg} at line {exc.lineno})") from exc
    if suffix == ".toml":
        try:
            import tomllib
        except ModuleNotFoundError as exc:
            raise ScopeError(
                f"{path.name}: TOML needs tomllib, which is stdlib from Python 3.11. This "
                "interpreter has it not — use a .json scope file instead."
            ) from exc
        try:
            return tomllib.loads(raw.decode("utf-8"))
        except tomllib.TOMLDecodeError as exc:
            raise ScopeError(f"{path.name}: not valid TOML ({exc})") from exc
    raise ScopeError(
        f"{path.name}: unsupported scope format {suffix!r}. Use .json (works everywhere) or .toml "
        "(Python 3.11+). YAML is deliberately NOT supported — see D-018: there is no YAML parser in "
        "the standard library, and C-2 forbids adding one to the core."
    )


def load_scope(path) -> Scope:
    """Read, validate and fingerprint a scope document."""
    p = Path(path)
    if not p.exists():
        raise ScopeError(f"no scope file at {p}")
    digest = scope_digest(p.read_bytes())
    return parse_scope(_decode(p), digest=digest, source=str(p))


def verify_scope(engagement, path) -> None:
    """Re-check that an engagement's `scope_sha256` is the digest of the scope file on disk.

    This is the check the report linter cannot perform (it has no file). It is what turns the C-7
    no-testing-without-a-signed-scope rule into something a third party can verify — on any platform,
    which is why the digest normalises line endings.
    """
    p = Path(path)
    if not p.exists():
        raise ScopeError(f"no scope file at {p}")
    actual = scope_digest(p.read_bytes())
    if actual != engagement.scope_sha256:
        raise ScopeError(
            f"scope mismatch: {p.name} hashes to {actual[:16]}... but the engagement records "
            f"{engagement.scope_sha256[:16]}... — the scope document changed after testing, or this "
            "is a different engagement's file. Do not report against it."
        )
