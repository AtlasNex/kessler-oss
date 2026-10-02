#!/usr/bin/env python3
"""Score Drill #01's conducted runs and render the timeline artifact (local step).

Inputs:  drill-topology/runs/prep/plan.json (+ runs/drill-01-runs.json pulled from the host)
Outputs: drill-topology/runs/drill-01-artifact.md (the rendered drill), stdout summary.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from kessler.drill import render_drill_md, score_drill  # noqa: E402

plan = json.loads((HERE / "runs/prep/plan.json").read_text(encoding="utf-8"))
runs = json.loads((HERE / "runs/drill-01-runs.json").read_text(encoding="utf-8"))
score = score_drill(runs)
md = render_drill_md(plan, score, topology_name="Drill #01: the owned g2 estate")
(HERE / "runs/drill-01-artifact.md").write_text(md, encoding="utf-8")

print(f"runs={len(runs)} chains={len(score['chains'])}")
for c in score["chains"]:
    rate = "n/a" if c["completion_rate"] is None else f"{c['completion_rate']*100:.1f}%"
    print(f"  {c['chain']}: {c['demonstrated']}/{c['attempts']} complete ({rate})")
for h in score["hops"]:
    rate = "n/a" if h["rate"] is None else f"{h['rate']*100:.1f}%"
    print(f"  hop {h['hop']} via {h['node']}: {h['succeeded']}/{h['reached']} ({rate})")
print(f"wrote {HERE / 'runs/drill-01-artifact.md'} ({len(md)} chars)")
