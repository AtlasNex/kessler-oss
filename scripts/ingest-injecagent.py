"""Ingest InjecAgent's attacker instructions as a Kessler behaviour pack (D-026).

Run:  python scripts/ingest-injecagent.py        (writes datasets/behaviors/injecagent.json)

Why THIS corpus. D-026 named JailbreakBench and HarmBench first, but those are **content-harm**
corpora ("write a tutorial for X"). Our composition slot wants an **agentic objective** — an
instruction that makes a tool-holding agent do something it should refuse. InjecAgent's
`attacker_cases_*.jsonl` is exactly that: 62 attacker instructions, each with the tools it abuses
and the achievement it is trying to reach. That is the unit we compose with.

Licence: InjecAgent is MIT (verified against the GitHub API, not assumed — see the provenance
block written into the output file). The MIT notice travels with the data.

What this script does NOT do: invent, paraphrase or "improve" an instruction. Each row's
`Attacker Instruction` is carried verbatim so the pack stays citable back to the source.
"""
from __future__ import annotations

import json
import sys
import urllib.request
from datetime import date
from pathlib import Path

REPO = "uiuc-kang-lab/InjecAgent"
RAW = f"https://raw.githubusercontent.com/{REPO}/main/data/"
FILES = ("attacker_cases_dh.jsonl", "attacker_cases_ds.jsonl")
OUT = Path(__file__).resolve().parent.parent / "datasets" / "behaviors" / "injecagent.json"

#: Attack Type -> the ASI categories the objective can honestly be tested under.
#: Direct-harm rows make the agent ACT (tool misuse, over-broad identity, rogue behaviour);
#: data-stealing rows make it EXFILTRATE (goal hijack, memory/context, tool misuse).
#: ASI04 (supply chain), ASI05 (code execution) and ASI07 (inter-agent) are deliberately absent:
#: nothing in this corpus exercises them, and padding the mapping would inflate coverage.
ASI_BY_ATTACK_TYPE = {
    "Physical Harm": ("ASI02", "ASI03", "ASI09", "ASI10"),
    "Financial Harm": ("ASI02", "ASI03", "ASI09", "ASI10"),
    "Data Security Harm": ("ASI02", "ASI03", "ASI06", "ASI10"),
    "Physical Data": ("ASI01", "ASI02", "ASI03", "ASI06"),
    "Financial Data": ("ASI01", "ASI02", "ASI03", "ASI06"),
    "Others": ("ASI01", "ASI02", "ASI06", "ASI09"),
}


def fetch(name: str) -> list[dict]:
    with urllib.request.urlopen(RAW + name, timeout=30) as resp:
        if resp.status != 200:
            raise SystemExit(f"{name}: HTTP {resp.status}")
        text = resp.read().decode("utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def licence_of(repo: str) -> str:
    """Ask GitHub what the licence is. An unverified licence must not reach datasets/."""
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
    unmapped: set[str] = set()
    for name in FILES:
        tag = "DH" if "_dh" in name else "DS"
        for i, row in enumerate(fetch(name), start=1):
            attack_type = row.get("Attack Type", "")
            cats = ASI_BY_ATTACK_TYPE.get(attack_type)
            if not cats:
                unmapped.add(attack_type)
                continue
            text = row["Attacker Instruction"].strip()
            if not text:
                continue
            behaviors.append({
                "id": f"B-IA-{tag}-{i:03d}",
                "text": text,
                "applies_to": list(cats),
            })
    if unmapped:
        # Fail loudly: a new Attack Type must be mapped by a human, never dropped in silence.
        raise SystemExit(f"unmapped Attack Type(s): {sorted(unmapped)} — map them in "
                         "ASI_BY_ATTACK_TYPE before ingesting")
    if not behaviors:
        raise SystemExit("no behaviours parsed — the upstream format changed")

    doc = {
        "schema": "kessler/behaviors/v1",
        "name": "injecagent-attacker-instructions",
        "description": (
            "Attacker instructions from InjecAgent (Zhan et al.), carried VERBATIM. Each row is an "
            "objective aimed at a tool-holding agent: the direct-harm rows make the agent act, the "
            "data-stealing rows make it exfiltrate. Mapped to ASI categories by attack type; "
            "ASI04/ASI05/ASI07 are absent because nothing in this corpus exercises them. "
            f"Regenerate with scripts/ingest-injecagent.py ({len(behaviors)} rows)."
        ),
        "version": "1.0.0",
        "updated": date.today().isoformat(),
        "provenance": {
            "source": f"InjecAgent, {REPO}, data/attacker_cases_dh.jsonl + attacker_cases_ds.jsonl",
            "url": f"https://github.com/{REPO}",
            "licence": spdx,
            "retrieved": date.today().isoformat(),
            "notice": ("MIT License, Copyright (c) the InjecAgent authors. Instructions are "
                       "reproduced verbatim under that licence; this repository adds only the "
                       "ASI mapping."),
            "verified_by": "GitHub API repos/{repo} license.spdx_id at ingest time".format(repo=REPO),
        },
        "behaviors": behaviors,
    }
    OUT.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"WROTE {OUT}  {len(behaviors)} behaviours, licence {spdx}")
    print("NEXT  python -m kessler.cli corpus   # the count is printed, never claimed (D-026)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
