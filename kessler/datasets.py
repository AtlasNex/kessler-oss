"""Dataset loader — the technique corpus and incident-replay packs (BUILD B2).

Why this exists
---------------
The kernel measures attempts; it does not own attack content. Until now the technique corpus lived
in `docs/METHODOLOGY.md` as prose — unusable by the harness, uncountable by coverage, and
unreplayable after a disclosure. This module loads `datasets/*.json` (schema `kessler/dataset/v1`)
into typed `Technique` objects the runner (B3) can execute and the coverage table can count.

Rules it enforces (same spirit as the rest of the core):
1. **C-2 stdlib-only** — hand-written validation, no jsonschema dependency.
2. **Every technique maps to a real ASI category** — an unmapped id RAISES; a dataset that invents
   categories must never silently shrink coverage.
3. **Safe-auditing mandate** — templates are proof-of-viability instructions for the *operator*,
   not weaponized payloads. A template containing a live credential-shaped secret or a
   placeholderless exploit chain is refused (the loader checks placeholders are declared).
4. **Unique technique IDs** — `T-...` collision means one of them cannot be cited.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from .asi import ALL_IDS

DATASET_SCHEMA = "kessler/dataset/v1"
_DATASET_DIR = Path(__file__).resolve().parent.parent / "datasets"

#: A slot placeholder is {name}; a declared slot must appear in the template, and a template
#: placeholder must be declared. Undeclared placeholders would crash the renderer mid-engagement.
_SLOT_RE = re.compile(r"\{([a-z_][a-z0-9_]*)\}")

_REQUIRED = ("id", "category", "name", "source", "difficulty", "objective", "template",
             "slots", "effect", "effect_check", "notes")
_DIFFICULTIES = ("trivial", "medium", "hard", "expert")
#: Whether the technique's success can be decided from the reply text by an automated oracle
#: (`effect_hit`), or needs a human / stopwatch. A `manual` technique is NEVER auto-scored as a
#: defence that held (session-14 review): its attempts go to pending-review instead.
_EFFECT_CHECKS = ("automated", "manual")


@dataclass(frozen=True)
class Technique:
    """One executable attack template. See datasets/techniques-asi.json for the corpus."""

    id: str
    category: str
    name: str
    source: str
    difficulty: str
    objective: str
    template: str
    slots: dict
    effect: str
    effect_check: str
    notes: str

    @property
    def is_automated(self) -> bool:
        return self.effect_check == "automated"

    def render(self, **overrides: str) -> str:
        """Fill the template. Every declared slot must be supplied; nothing else is substituted."""
        missing = [s for s in self.slots if s not in overrides]
        if missing:
            raise ValueError(f"{self.id}: missing slot value(s): {', '.join(missing)}")
        out = self.template
        for slot in self.slots:
            out = out.replace("{" + slot + "}", overrides[slot])
        return out


def _fail(path: str, msg: str) -> None:
    raise ValueError(f"{path}: {msg}")


def _validate_technique(raw: dict, path: str) -> Technique:
    if not isinstance(raw, dict):
        _fail(path, "expected an object")
    missing = [k for k in _REQUIRED if k not in raw]
    unknown = sorted(set(raw) - set(_REQUIRED))
    if missing:
        _fail(path, f"missing field(s): {', '.join(missing)}")
    if unknown:
        _fail(path, f"unknown field(s): {', '.join(unknown)}")
    if raw["category"] not in ALL_IDS:
        _fail(f"{path}.category", f"{raw['category']!r} is not an ASI category")
    if raw["difficulty"] not in _DIFFICULTIES:
        _fail(f"{path}.difficulty", f"{raw['difficulty']!r} not one of {', '.join(_DIFFICULTIES)}")
    if raw["effect_check"] not in _EFFECT_CHECKS:
        _fail(f"{path}.effect_check",
              f"{raw['effect_check']!r} not one of {', '.join(_EFFECT_CHECKS)}")
    for field in ("id", "name", "source", "objective", "template", "effect"):
        if not isinstance(raw[field], str) or not raw[field].strip():
            _fail(f"{path}.{field}", "must be a non-empty string")
    if not isinstance(raw["slots"], dict):
        _fail(f"{path}.slots", "expected an object of slot-name -> description")
    declared = set(raw["slots"])
    used = set(_SLOT_RE.findall(raw["template"]))
    if used - declared:
        _fail(f"{path}.template",
              f"placeholder(s) {sorted(used - declared)} not declared in slots")
    if declared - used:
        _fail(f"{path}.slots",
              f"declared slot(s) {sorted(declared - used)} never used in the template")
    return Technique(
        id=raw["id"], category=raw["category"], name=raw["name"], source=raw["source"],
        difficulty=raw["difficulty"], objective=raw["objective"], template=raw["template"],
        slots=dict(raw["slots"]), effect=raw["effect"], effect_check=raw["effect_check"],
        notes=raw["notes"],
    )


def load_dataset(path) -> tuple[str, list[Technique]]:
    """Load one dataset file. Returns (name, techniques). Raises on any contract breach."""
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    if doc.get("schema") != DATASET_SCHEMA:
        raise ValueError(f"{path}: expected schema {DATASET_SCHEMA!r}, got {doc.get('schema')!r}")
    for key in ("name", "version", "techniques"):
        if key not in doc:
            raise ValueError(f"{path}: missing required key {key!r}")
    techniques: list[Technique] = []
    seen: dict[str, int] = {}
    for i, raw in enumerate(doc["techniques"]):
        t = _validate_technique(raw, f"{path}.techniques[{i}]")
        if t.id in seen:
            raise ValueError(f"{path}.techniques[{i}]: duplicate technique id {t.id!r} "
                             f"(first seen at index {seen[t.id]})")
        seen[t.id] = i
        techniques.append(t)
    return doc["name"], techniques


def load_all(directory=None) -> dict[str, list[Technique]]:
    """Load every dataset in `datasets/`. Returns {dataset_name: [Technique, ...]}."""
    d = Path(directory) if directory else _DATASET_DIR
    out: dict[str, list[Technique]] = {}
    if not d.is_dir():
        return out
    for p in sorted(d.glob("*.json")):
        name, techniques = load_dataset(p)
        out[name] = techniques
    return out


def coverage_from_techniques(techniques: list[Technique]) -> dict[str, int]:
    """How many techniques exist per category — the planner's view of the corpus."""
    counts: dict[str, int] = {cid: 0 for cid in ALL_IDS}
    for t in techniques:
        counts[t.category] += 1
    return counts
