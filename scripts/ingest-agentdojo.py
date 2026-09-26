"""Ingest AgentDojo's injection-task GOALs as a Kessler behaviour pack (D-026).

Run:  python scripts/ingest-agentdojo.py        (writes datasets/behaviors/agentdojo.json)

Why THIS corpus. AgentDojo's *injection tasks* are the attacker half of its benchmark: each one is
a goal an attacker wants a tool-holding agent to reach inside a realistic environment (a bank, a
Slack workspace, a travel agent, an office suite). That is our behaviour unit. The 629 figure
quoted for AgentDojo is its *security test cases* — user tasks crossed with injection tasks — not
the number of distinct attacker goals, which is what we ingest here. We compose our own crossing;
importing theirs would double-count the same objective.

Licence: MIT (verified against the GitHub API at ingest time, never assumed). The notice travels
with the data, and every GOAL is carried verbatim.

Extraction: the GOALs live in Python class bodies, most as f-strings over class-level constants
(`_ATTACKER_IBAN`, `_RECIPIENT`). We parse with `ast` and resolve ONLY plain class-level string
constants. A GOAL that cannot be fully resolved is REPORTED and skipped, never guessed at — a
paraphrased attacker objective is a fabricated test case (AGENTS.md rule 2).
"""
from __future__ import annotations

import ast
import json
import sys
import urllib.request
from datetime import date
from pathlib import Path

REPO = "ethz-spylab/agentdojo"
RAW = f"https://raw.githubusercontent.com/{REPO}/main/src/agentdojo/default_suites/v1/"
OUT = Path(__file__).resolve().parent.parent / "datasets" / "behaviors" / "agentdojo.json"

#: Suite -> the ASI categories its tool surface can honestly carry. This is a claim about what the
#: suite's tools DO (move money, message people, book travel, read mail and files), not a guess
#: about each individual sentence. ASI04/ASI05/ASI07 are absent: no suite ships a supply-chain,
#: code-execution or agent-to-agent surface, and padding the mapping would inflate coverage.
SUITES = {
    "banking": ("ASI02", "ASI03", "ASI09", "ASI10"),
    "slack": ("ASI01", "ASI02", "ASI06", "ASI09"),
    "travel": ("ASI02", "ASI03", "ASI06", "ASI09"),
    "workspace": ("ASI01", "ASI02", "ASI03", "ASI06"),
}


def fetch(suite: str) -> str:
    with urllib.request.urlopen(f"{RAW}{suite}/injection_tasks.py", timeout=30) as resp:
        if resp.status != 200:
            raise SystemExit(f"{suite}: HTTP {resp.status}")
        return resp.read().decode("utf-8")


def _class_string_constants(cls: ast.ClassDef) -> dict[str, str]:
    out: dict[str, str] = {}
    for stmt in cls.body:
        targets = (stmt.targets if isinstance(stmt, ast.Assign)
                   else [stmt.target] if isinstance(stmt, ast.AnnAssign) else [])
        value = getattr(stmt, "value", None)
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            for t in targets:
                if isinstance(t, ast.Name):
                    out[t.id] = value.value
    return out


def goal_of(cls: ast.ClassDef) -> tuple[bool, str | None]:
    """(declares a GOAL, the resolved text or None when it could not be resolved)."""
    consts = _class_string_constants(cls)
    for stmt in cls.body:
        if not (isinstance(stmt, ast.Assign)
                and any(getattr(t, "id", "") == "GOAL" for t in stmt.targets)):
            continue
        value = stmt.value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            return True, value.value
        if isinstance(value, ast.JoinedStr):
            parts: list[str] = []
            for piece in value.values:
                if isinstance(piece, ast.Constant) and isinstance(piece.value, str):
                    parts.append(piece.value)
                elif (isinstance(piece, ast.FormattedValue)
                      and isinstance(piece.value, ast.Name)
                      and piece.value.id in consts):
                    parts.append(consts[piece.value.id])
                else:
                    return True, None  # an expression we will not evaluate
            return True, "".join(parts)
        return True, None
    return False, None


def licence_of(repo: str) -> str:
    req = urllib.request.Request(
        f"https://api.github.com/repos/{repo}",
        headers={"User-Agent": "kessler-ingest", "Accept": "application/vnd.github+json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        meta = json.load(resp)
    spdx = ((meta.get("license") or {}).get("spdx_id") or "").strip()
    if not spdx or spdx in {"NOASSERTION", "NONE"}:
        raise SystemExit(f"{repo}: licence is {spdx!r} — no licence, no ingest (D-026)")
    return spdx


def main() -> int:
    spdx = licence_of(REPO)
    behaviors: list[dict] = []
    skipped: list[str] = []
    for suite, cats in SUITES.items():
        tree = ast.parse(fetch(suite))
        seen = 0
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            declares, goal = goal_of(node)
            if not declares:
                continue
            seen += 1
            if goal is None or not goal.strip():
                skipped.append(f"{suite}.{node.name}")
                continue
            behaviors.append({
                "id": f"B-AD-{suite[:4].upper()}-{seen:03d}",
                "text": goal.strip(),
                "applies_to": list(cats),
            })
        print(f"  {suite}: {seen} injection task(s)")
    if not behaviors:
        raise SystemExit("no GOALs parsed — the upstream layout changed")
    if skipped:
        # Honest, loud, and not fatal: a GOAL we cannot resolve is reported, never paraphrased.
        print(f"SKIPPED {len(skipped)} unresolvable GOAL(s): {', '.join(skipped)}", file=sys.stderr)

    doc = {
        "schema": "kessler/behaviors/v1",
        "name": "agentdojo-injection-goals",
        "description": (
            "Injection-task GOALs from AgentDojo (Debenedetti et al.), carried VERBATIM. Each row "
            "is an attacker objective inside a realistic tool environment (banking, Slack, travel, "
            "workspace), mapped to ASI categories by what that suite's tools can actually do. "
            "ASI04/ASI05/ASI07 are absent: no suite ships those surfaces. This is the attacker "
            "half of AgentDojo only — we compose our own crossing, so importing their 629 "
            f"security test cases would double-count. Regenerate with scripts/ingest-agentdojo.py "
            f"({len(behaviors)} rows"
            + (f", {len(skipped)} skipped as unresolvable)." if skipped else ").")
        ),
        "version": "1.0.0",
        "updated": date.today().isoformat(),
        "provenance": {
            "source": f"AgentDojo, {REPO}, src/agentdojo/default_suites/v1/*/injection_tasks.py",
            "url": f"https://github.com/{REPO}",
            "licence": spdx,
            "retrieved": date.today().isoformat(),
            "notice": ("MIT License, Copyright (c) 2024 Edoardo Debenedetti, Jie Zhang, Mislav "
                       "Balunovic and the AgentDojo authors. GOALs are reproduced verbatim under "
                       "that licence; this repository adds only the ASI mapping."),
            "verified_by": f"GitHub API repos/{REPO} license.spdx_id at ingest time",
        },
        "behaviors": behaviors,
    }
    OUT.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"WROTE {OUT}  {len(behaviors)} behaviours, licence {spdx}")
    print("NEXT  python -m kessler.cli corpus   # the count is printed, never claimed (D-026)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
