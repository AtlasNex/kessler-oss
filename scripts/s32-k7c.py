"""K7 wave-2 pin move (asserted, atomic): corpus 6,022 -> 6,443 across tests, README, HANDOVER,
the methodology report, plus the D-044 ledger entry."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def edit(path: Path, pairs: list[tuple[str, str]]) -> None:
    t = path.read_text(encoding="utf-8")
    for old, new in pairs:
        cnt = t.count(old)
        if cnt != 1:
            raise SystemExit(f"ANCHOR FAIL {path.name}: {cnt} for {old[:90]!r}")
        t = t.replace(old, new, 1)
    path.write_text(t, encoding="utf-8", newline="")
    print(f"edited {path.name} ({len(pairs)} edits)")


edit(ROOT / "tests" / "test_corpus.py", [(
    "Moved 25 Sep 2026 (883 -> 1101) by the memory-attack pack + multi_session channel\n"
    "    (PLAN-v4 Phase 4). The AgentHarm wave (26 Sep, corpus 3,671 -> 6,022) landed ONLY in\n"
    "    manual-oracle techniques — this mass must NOT move from it; if it does, investigate.",
    "Moved 25 Sep 2026 (883 -> 1101) by the memory-attack pack + multi_session channel\n"
    "    (PLAN-v4 Phase 4); the AgentHarm wave (26 Sep, corpus 3,671 -> 6,022) landed ONLY in\n"
    "    manual-oracle techniques. Moved again 4 Oct (1101 -> 1173; ASI01 648 -> 696, ASI06\n"
    "    450 -> 474) by the K7 wave-2 first-party packs (dedicated ASI03 + workstation), both\n"
    "    of which carry automated-oracle objectives; recorded in D-044.",
), (
    'assert ac["total"] == 1101, ac',
    'assert ac["total"] == 1173, ac',
), (
    'assert ac["by_category"]["ASI01"] == 648, ac',
    'assert ac["by_category"]["ASI01"] == 696, ac',
), (
    'assert ac["by_category"]["ASI06"] == 450, ac',
    'assert ac["by_category"]["ASI06"] == 474, ac',
), (
    '"corpus: automated-oracle mass is 1101 (648/3/450) and pinned (review F-6; moved by the "',
    '"corpus: automated-oracle mass is 1173 (696/3/474) and pinned (review F-6; moved by the "',
), (
    '"memory pack + multi_session channel)", t_automated_oracle_mass_is_pinned),',
    '"K7 ASI03 + workstation packs)", t_automated_oracle_mass_is_pinned),',
)])

edit(ROOT / "tests" / "test_synth.py", [(
    "the 6,022 regression;",
    "the 6,443 regression;",
), (
    "counts moved 3,118 -> 3,671 -> 6,022 only for the stated PLAN-v4 corpus waves",
    "counts moved 3,118 -> 3,671 -> 6,022 -> 6,443 only for stated corpus waves (PLAN-v4; D-044)",
), (
    "# Pin history: 3,118 -> 3,671 (25 Sep, memory pack + multi_session channel) -> 6,022\n"
    "    # (26 Sep, AgentHarm wave-2 ingest, D3) — deliberate, stated corpus changes (PLAN-v4),\n"
    "    # not synthesis. Any other movement is the bug this check exists for.",
    "# Pin history: 3,118 -> 3,671 (25 Sep, memory pack + multi_session channel) -> 6,022\n"
    "    # (26 Sep, AgentHarm wave-2 ingest, D3) -> 6,443 (04 Oct, K7 wave-2 ASI03 + workstation\n"
    "    # packs, D-044) — deliberate, stated corpus changes, not synthesis. Any other movement\n"
    "    # is the bug this check exists for.",
), (
    'assert len(cases) == 6022, f"default corpus drifted: {len(cases)} (expected 6022)"',
    'assert len(cases) == 6443, f"default corpus drifted: {len(cases)} (expected 6443)"',
)])

edit(ROOT / "README.md", [(
    "**Corpus v2: 6,022 test cases**",
    "**Corpus v2: 6,443 test cases**",
), (
    "334 behaviours from six packs (first-party, InjecAgent, AgentDojo, memory-attacks,",
    "356 behaviours from eight packs (first-party, ASI03 identity/privilege, workstation, "
    "InjecAgent, AgentDojo, memory-attacks,",
)])

edit(ROOT / "docs" / "HANDOVER.md", [(
    "**6,022 cases** (pin history 3,118 -> 3,671 -> 6,022: memory pack + multi_session channel, "
    "then the AgentHarm wave-2 ingest closing D3) from 25 techniques x 334 behaviours x 7 channels",
    "**6,443 cases** (pin history 3,118 -> 3,671 -> 6,022 -> 6,443: memory + multi_session, "
    "AgentHarm wave-2 D3, then the K7 wave-2 dedicated ASI03 + workstation packs closing "
    "#10/#7) from 25 techniques x 356 behaviours x 7 channels",
)])

edit(ROOT / "docs" / "publish" / "05-methodology.md", [(
    "**6,022 test cases**",
    "**6,443 test cases**",
)])

D044 = """

## D-044 (04 Oct 2026, session 32) - corpus pin 6,022 -> 6,443: the dedicated ASI03 + workstation packs

Decided: the K7 wave-2 batch (docs 21/22c; #10 the ASI03 identity/privilege pack, #7 the
coding-agent workstation lane) adds two FIRST-PARTY packs: kessler-asi03 (12 objectives;
ASI03 carried crossovers but had no dedicated pack) and kessler-workstation (10 workstation
objectives, the lane's corpus). Counts: 6,022 -> 6,443 cases, 334 -> 356 behaviours; every
category stays non-empty; the automated-oracle mass moves 1,101 -> 1,173 and its F-6 pin
moves with it (tests/test_corpus.py). The workstation scope example
(scopes/workstation-audit.json) plans cleanly offline (5,367 cases, 10,734 attempts).

Honest note: PLAN-v5 froze the corpus pin pending a first invoice or pilot. The owner-ordered
s32 program (docs 21/22c) schedules this exact gap-fill, so the exception is recorded here
explicitly rather than broken silently. No third-party content entered; both packs are
first-party MIT under the safe-auditing mandate (proof-of-viability objectives only). The
licence gate and provenance requirements are unchanged.
"""

edit(ROOT / "docs" / "DECISIONS.md", [(
    "the practice, not the person.",
    "the practice, not the person.\n" + D044,
)])

print("K7 wave-2 pin move applied")
