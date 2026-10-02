"""The engagement schema: the single source of truth every other component consumes.

Why this exists
---------------
One engagement is one versioned JSON document (`kessler.json`, schema `kessler/engagement/v1`).
Scope, targets, attempts, findings, exclusions and any retest all live in it, so every deliverable is
a **pure function of the document** rather than a hand-edited artefact. That is what makes a retest
after a fix a **re-run instead of a rewrite** — the largest single labour saving in the practice
(`docs/IMPLEMENTATION-PLAN.md` section 1), and the honest commercial justification for the harness.

Two properties matter more than convenience
-------------------------------------------
1. **C-2, stdlib only.** This has to load on a locked-down client laptop with no package manager.
   Validation is therefore hand-written here. `schemas/engagement-v1.json` is the versioned *interop
   contract* for other tools; it is deliberately **not** the validator, because using it as one would
   require a JSON-Schema dependency the core may not have. `tests/test_schema.py` asserts the two
   cannot drift apart.
2. **C-1 is re-asserted at the boundary.** A file is untrusted input. Checking the JSON *shape* alone
   would let a document smuggle in an unevidenced success that the kernel itself refuses to construct,
   so every attempt is rebuilt through `Attempt(...)` and every finding through `build_finding(...)`.
   A shape-valid document is not necessarily an acceptable one.

Failures name the path
----------------------
Every error identifies the offending field (`$.attempts[3].observed`) and the rule it broke. A
silently-skipped field in a client deliverable is worse than a crash, so unknown keys are rejected
rather than ignored.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from .asi import ALL_IDS, Attempt, Finding, Severity, build_finding, coverage

#: The one schema this code understands. Anything else is refused rather than best-effort parsed.
SCHEMA_ID = "kessler/engagement/v1"

#: Target kinds, from IMPLEMENTATION-PLAN.md section 1.
TARGET_KINDS: tuple[str, ...] = ("agent", "mcp_server", "tool", "memory", "model")

#: Document keys, in dump order. Also the drift contract with schemas/engagement-v1.json.
TOP_LEVEL_KEYS: tuple[str, ...] = (
    "schema", "engagement", "targets", "attempts", "findings", "exclusions", "retest",
)
ATTEMPT_FIELDS: tuple[str, ...] = (
    "category", "technique", "succeeded", "observed", "payload", "environment", "at", "adapter_ref",
)
FINDING_FIELDS: tuple[str, ...] = (
    "category", "title", "severity", "description", "preconditions", "expected", "impact",
    "reproduction", "evidence", "remediation_architectural_fix", "remediation_guardrail_config",
    "remediation_code_patch", "threat_scenario", "impact_analysis", "finding_id",
    "cvss_v4_vector", "chained_with",
)
#: PLAN-v5 #16 additions (CRA clock class + ATLAS mapping state). Optional on load — sealed
#: v1 documents predate them and stay valid; dumped ONLY when set, so a document without the
#: fields round-trips byte-identically and adding a field never rewrites history.
OPTIONAL_FINDING_FIELDS: tuple[str, ...] = ("cra_class", "atlas_mapping")
ENGAGEMENT_FIELDS: tuple[str, ...] = ("ref", "client", "window", "scope_sha256", "testers")
RETEST_FIELDS: tuple[str, ...] = ("baseline_sha256", "attempts")

_HEX = frozenset("0123456789abcdef")


class SchemaError(ValueError):
    """An engagement document this code will not accept. Raised before anything is applied."""


# --------------------------------------------------------------------------- primitives

def _fail(path: str, message: str) -> None:
    raise SchemaError(f"{path}: {message}")


def _obj(value, path: str) -> dict:
    if not isinstance(value, dict):
        _fail(path, f"expected an object, got {type(value).__name__}")
    return value


def _keys(value: dict, path: str, required: tuple[str, ...], *, optional: tuple[str, ...] = ()) -> None:
    """Require exactly this key set — missing is a gap, unknown is drift."""
    missing = [k for k in required if k not in value]
    if missing:
        _fail(path, f"missing required key(s): {', '.join(missing)}")
    unknown = sorted(set(value) - set(required) - set(optional))
    if unknown:
        _fail(
            path,
            f"unknown key(s): {', '.join(unknown)} — an unreadable field in a deliverable is worse "
            "than a crash, so unrecognised keys are refused rather than ignored",
        )


def _str(value, path: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        _fail(path, f"expected a string, got {type(value).__name__}")
    if not allow_empty and not value.strip():
        _fail(path, "must be non-empty")
    return value


def _bool(value, path: str) -> bool:
    if not isinstance(value, bool):  # checked before any numeric branch: bool is an int subclass
        _fail(path, f"expected true or false, got {type(value).__name__}")
    return value


def _list(value, path: str) -> list:
    if not isinstance(value, list):
        _fail(path, f"expected a list, got {type(value).__name__}")
    return value


def _asi(value, path: str) -> str:
    if value not in ALL_IDS:
        _fail(path, f"unknown ASI category {value!r}; expected one of {', '.join(ALL_IDS)}")
    return value


def _sha256_hex(value, path: str) -> str:
    s = _str(value, path)
    if len(s) != 64 or any(c not in _HEX for c in s):
        _fail(path, f"expected a 64-character lowercase sha256 digest, got {s[:24]!r}")
    return s


def _iso_day(value, path: str) -> str:
    s = _str(value, path)
    try:
        date.fromisoformat(s)
    except ValueError:
        _fail(path, f"expected an ISO date (YYYY-MM-DD), got {s!r}")
    return s


def _iso_timestamp(value, path: str) -> str:
    s = _str(value, path)
    try:
        datetime.fromisoformat(s)
    except ValueError:
        _fail(path, f"expected an ISO 8601 timestamp, got {s!r}")
    return s


# --------------------------------------------------------------------------- parts

def _attempt(raw, path: str) -> Attempt:
    """Rebuild an attempt through the kernel constructor so C-1 is re-asserted on load."""
    _obj(raw, path)
    _keys(raw, path, ATTEMPT_FIELDS)
    _iso_timestamp(raw["at"], f"{path}.at")
    try:
        return Attempt(
            category=raw["category"],
            technique=raw["technique"],
            succeeded=_bool(raw["succeeded"], f"{path}.succeeded"),
            observed=_str(raw["observed"], f"{path}.observed", allow_empty=True),
            payload=_str(raw["payload"], f"{path}.payload", allow_empty=True),
            environment=_str(raw["environment"], f"{path}.environment", allow_empty=True),
            at=raw["at"],
            adapter_ref=_str(raw["adapter_ref"], f"{path}.adapter_ref", allow_empty=True),
        )
    except (KeyError, ValueError) as exc:
        raise SchemaError(f"{path}: {exc}") from exc


def _finding(raw, path: str) -> Finding:
    """Rebuild a finding through `build_finding` so the fail-closed field guard also applies.

    KES contract (D-025) is enforced twice on load: here (shape + presence) and again inside
    `Finding.__post_init__` (format — KES-YYYY-NNN, C-I-A levels, CVSS structure). Shape-valid is
    not acceptable; both gates must pass.
    """
    _obj(raw, path)
    _keys(raw, path, FINDING_FIELDS,
           optional=OPTIONAL_FINDING_FIELDS)   # v5 #16 fields: optional on load
    severity = raw["severity"]
    if isinstance(severity, str):
        try:
            severity = Severity(severity)
        except ValueError:
            _fail(
                f"{path}.severity",
                f"unknown severity {severity!r}; expected one of "
                f"{', '.join(s.value for s in Severity)}",
            )
    _str(raw["finding_id"], f"{path}.finding_id")
    _str(raw["threat_scenario"], f"{path}.threat_scenario")
    ia = raw["impact_analysis"]
    if not isinstance(ia, dict):
        _fail(f"{path}.impact_analysis", "expected an object")
    cvss = _str(raw["cvss_v4_vector"], f"{path}.cvss_v4_vector", allow_empty=True)
    chained = [
        _asi(c, f"{path}.chained_with[{i}]")
        for i, c in enumerate(_list(raw["chained_with"], f"{path}.chained_with"))
    ]
    try:
        return build_finding(
            category=raw["category"], title=raw["title"], severity=severity,
            description=raw["description"], preconditions=raw["preconditions"],
            expected=raw["expected"], impact=raw["impact"],
            reproduction=raw["reproduction"], evidence=raw["evidence"],
            threat_scenario=raw["threat_scenario"],
            impact_analysis=ia,
            remediation_architectural_fix=raw["remediation_architectural_fix"],
            remediation_guardrail_config=raw["remediation_guardrail_config"],
            remediation_code_patch=raw["remediation_code_patch"],
            finding_id=raw["finding_id"],
            cvss_v4_vector=cvss,
            chained_with=chained,
            cra_class=raw.get("cra_class", ""),
            atlas_mapping=raw.get("atlas_mapping", ""),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise SchemaError(f"{path}: {exc}") from exc


def _finding_list(raw, path: str) -> list[Finding]:
    """Findings with the cross-finding rule the per-item validator cannot see: KES IDs unique.

    Two findings sharing a finding_id break retest tracking and SARIF ruleId — the same class of
    defect as a duplicated adapter_ref (double-counting), so it is refused at the same boundary.
    """
    findings = [_finding(f, f"{path}[{i}]") for i, f in enumerate(_list(raw, path))]
    seen: dict[str, int] = {}
    for i, f in enumerate(findings):
        if f.finding_id in seen:
            _fail(f"{path}[{i}].finding_id",
                  f"duplicate finding_id {f.finding_id!r} (first at index {seen[f.finding_id]}) "
                  "— a KES ID names one finding across retests and SARIF")
        seen[f.finding_id] = i
    return findings


def validate_targets(raw, path: str = "$.targets") -> list[dict]:
    """Validate the target inventory. Public because the scope parser uses the same rules.

    Single-sourcing this matters: a scope file and an engagement document describe the same targets,
    and two validators would drift until a target valid in one was refused by the other.
    """
    seen: set[str] = set()
    targets: list[dict] = []
    for i, item in enumerate(_list(raw, path)):
        where = f"{path}[{i}]"
        _obj(item, where)
        _keys(item, where, ("id", "kind", "version", "reaches", "notes"), optional=("endpoint",))
        endpoint = item.get("endpoint", False)
        if not isinstance(endpoint, bool):
            _fail(f"{where}.endpoint",
                  "endpoint must be a boolean (the target is directly callable over HTTP)")
        tid = _str(item["id"], f"{where}.id")
        if tid in seen:
            _fail(
                f"{where}.id",
                f"duplicate target id {tid!r} — coverage is counted per target, so ids must be unique",
            )
        seen.add(tid)
        kind = _str(item["kind"], f"{where}.kind")
        if kind not in TARGET_KINDS:
            _fail(f"{where}.kind", f"unknown kind {kind!r}; expected one of {', '.join(TARGET_KINDS)}")
        targets.append({
            "id": tid,
            "kind": kind,
            "version": _str(item["version"], f"{where}.version", allow_empty=True),
            "reaches": [
                _str(r, f"{where}.reaches[{j}]")
                for j, r in enumerate(_list(item["reaches"], f"{where}.reaches"))
            ],
            "notes": _str(item["notes"], f"{where}.notes", allow_empty=True),
            "endpoint": endpoint,
        })
    return targets


def validate_exclusions(raw, path: str = "$.exclusions") -> dict[str, str]:
    """C-4 in the document: a category is excluded only with a written reason."""
    _obj(raw, path)
    out: dict[str, str] = {}
    for cid, reason in raw.items():
        _asi(cid, f"{path}.{cid}")
        out[cid] = _str(reason, f"{path}.{cid}")
    return out


def _retest(raw, path: str) -> dict | None:
    if raw is None:
        return None
    _obj(raw, path)
    _keys(raw, path, RETEST_FIELDS)
    return {
        "baseline_sha256": _sha256_hex(raw["baseline_sha256"], f"{path}.baseline_sha256"),
        "attempts": [
            _attempt(a, f"{path}.attempts[{i}]")
            for i, a in enumerate(_list(raw["attempts"], f"{path}.attempts"))
        ],
    }


# --------------------------------------------------------------------------- document

@dataclass
class Engagement:
    """One engagement. The only object the report generator needs."""

    ref: str
    client: str
    start: str
    end: str
    scope_sha256: str
    targets: list[dict] = field(default_factory=list)
    attempts: list[Attempt] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    testers: list[str] = field(default_factory=list)
    exclusions: dict[str, str] = field(default_factory=dict)
    retest: dict | None = None

    @property
    def schema(self) -> str:
        return SCHEMA_ID

    def coverage(self) -> list[dict[str, str]]:
        """Per-category tested / excluded / missing rows — the denominator the report must show."""
        return coverage(self.attempts, self.exclusions)


def parse(doc) -> Engagement:
    """Validate a decoded document and build an Engagement. Raises before applying anything."""
    _obj(doc, "$")
    _keys(doc, "$", TOP_LEVEL_KEYS)
    got = doc["schema"]
    if got != SCHEMA_ID:
        raise SchemaError(
            f"$.schema: expected {SCHEMA_ID!r}, got {got!r} — refusing to best-effort parse a "
            "document this code does not know"
        )

    meta = _obj(doc["engagement"], "$.engagement")
    _keys(meta, "$.engagement", ENGAGEMENT_FIELDS)
    window = _obj(meta["window"], "$.engagement.window")
    _keys(window, "$.engagement.window", ("start", "end"))
    testers = [_str(t, f"$.engagement.testers[{i}]")
               for i, t in enumerate(_list(meta["testers"], "$.engagement.testers"))]
    if not testers:
        _fail("$.engagement.testers", "at least one named tester is required (REPORT-SPEC section 1)")

    return Engagement(
        ref=_str(meta["ref"], "$.engagement.ref"),
        client=_str(meta["client"], "$.engagement.client"),
        start=_iso_day(window["start"], "$.engagement.window.start"),
        end=_iso_day(window["end"], "$.engagement.window.end"),
        scope_sha256=_sha256_hex(meta["scope_sha256"], "$.engagement.scope_sha256"),
        testers=testers,
        targets=validate_targets(doc["targets"], "$.targets"),
        attempts=[
            _attempt(a, f"$.attempts[{i}]")
            for i, a in enumerate(_list(doc["attempts"], "$.attempts"))
        ],
        findings=_finding_list(doc["findings"], "$.findings"),
        exclusions=validate_exclusions(doc["exclusions"], "$.exclusions"),
        retest=_retest(doc["retest"], "$.retest"),
    )


def _attempt_doc(a: Attempt) -> dict:
    return {k: getattr(a, k) for k in ATTEMPT_FIELDS}


def _finding_doc(f: Finding) -> dict:
    out = {k: getattr(f, k) for k in FINDING_FIELDS if k != "chained_with"}
    out["impact_analysis"] = dict(f.impact_analysis)
    out["severity"] = f.severity.value
    out["chained_with"] = list(f.chained_with)
    # v5 #16: the optional fields ride only when set, so a document written before them
    # round-trips byte-identically (the identity contract in the module docstring).
    if f.cra_class:
        out["cra_class"] = f.cra_class
    if f.atlas_mapping:
        out["atlas_mapping"] = f.atlas_mapping
    return out


def to_document(eng: Engagement) -> dict:
    """Render the canonical document. `parse(to_document(e))` is the identity."""
    return {
        "schema": SCHEMA_ID,
        "engagement": {
            "ref": eng.ref,
            "client": eng.client,
            "window": {"start": eng.start, "end": eng.end},
            "scope_sha256": eng.scope_sha256,
            "testers": list(eng.testers),
        },
        "targets": [
            {"id": t["id"], "kind": t["kind"], "version": t.get("version", ""),
             "reaches": list(t["reaches"]), "notes": t["notes"],
             # endpoint=True is evidence-truth: a round-trip must not drop it (review F-8).
             # False is the parser default and stays omitted so existing documents round-trip.
             **({"endpoint": True} if t.get("endpoint") else {})}
            for t in eng.targets
        ],
        "attempts": [_attempt_doc(a) for a in eng.attempts],
        "findings": [_finding_doc(f) for f in eng.findings],
        "exclusions": dict(eng.exclusions),
        "retest": None if eng.retest is None else {
            "baseline_sha256": eng.retest["baseline_sha256"],
            "attempts": [_attempt_doc(a) for a in eng.retest["attempts"]],
        },
    }


def loads(text: str) -> Engagement:
    """Parse an engagement from JSON text."""
    try:
        doc = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SchemaError(f"not valid JSON: {exc}") from exc
    return parse(doc)


def load(path) -> Engagement:
    """Read and validate an engagement document from disk."""
    return loads(Path(path).read_text(encoding="utf-8"))


def dumps(eng: Engagement) -> str:
    """Serialise to canonical JSON text."""
    return json.dumps(to_document(eng), indent=2, ensure_ascii=False) + "\n"


def save(eng: Engagement, path) -> None:
    """Write the canonical document to disk."""
    Path(path).write_text(dumps(eng), encoding="utf-8")
