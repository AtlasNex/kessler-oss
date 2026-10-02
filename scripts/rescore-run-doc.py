#!/usr/bin/env python3
"""Re-score a run document's scored rows under the CURRENT oracle (report-first).

Same discipline as scripts/adjudicate-sealed.py: a re-score scores the text the run scored
(D-039) - here the stored `observed` field of each SUCCEEDED row (single-turn runs store the
verbatim reply; rows that did not succeed stored no reply, so this tool can only DEMOTE,
never promote - the conservative direction).

Born from V-33 (2026-10-02): the AnythingLLM bench run's hits were injections quoted inside
<think> blocks while the answers refused; the kernel oracle now strips tag-delimited CoT
before the refusal guard and the needles, and this tool re-applies it to stored rows.

Usage:
  python scripts/rescore-run-doc.py <doc.json>                  # report only
  python scripts/rescore-run-doc.py <doc.json> --out <new.json> # write the corrected doc
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from kessler.datasets import load_all  # noqa: E402
from kessler.selftest import effect_hit, final_reply_of  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("document")
    ap.add_argument("--out")
    args = ap.parse_args()

    doc = json.loads(Path(args.document).read_text(encoding="utf-8"))
    techs = {f"runner:{t.id}": t for ts in load_all().values() for t in ts}
    kept = demoted = 0
    demoted_rows: list[str] = []
    for x in doc["attempts"]:
        if not x.get("succeeded"):
            continue
        t = techs.get(x["technique"])
        # D-039: a re-score scores the text the RUN scored - the FINAL REPLY of a conducted
        # sequence, recovered from the stored transcript; the verbatim reply otherwise.
        scoring_text, _ = final_reply_of(x.get("observed") or "")
        if t is None or effect_hit(t, scoring_text):
            kept += 1
        else:
            x["succeeded"] = False
            x["observed"] = ""
            demoted_rows.append(x["technique"])
            demoted += 1

    total_scored = kept + demoted
    print(f"doc: {args.document}")
    print(f"scored rows re-checked: {total_scored} | kept: {kept} | demoted: {demoted}")
    for r in demoted_rows[:25]:
        print(f"  demoted: {r}")
    if args.out:
        Path(args.out).write_text(json.dumps(doc, ensure_ascii=False, indent=2),
                                  encoding="utf-8")
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
