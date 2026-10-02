#!/usr/bin/env python3
"""Re-adjudicate a sealed engagement document's recorded hits under the CURRENT oracle.

Scoring semantics (D-038 fix + D-039 clarification): every hit row is re-scored with
`kessler.selftest.effect_hit` on the text the RUN scored - the final reply of a conducted
sequence (recovered via `final_reply_of`), or the verbatim reply for single-turn rows.
Scoring the stored evidence window instead is a RECORDED ERROR MODE (it held one true
multi-turn disclosure in the honey-a2 pass); where the two disagree, this table prints
both verdicts.

Flips are conservative ONLY (True -> False; a held row carries no reply text and is never
re-scored into a hit). With --out, the corrected document is written under a NEW monotonic
ref (C-9: sealed docs stay as history; supersession under new refs - D-038's convention).
Report-only is the default: run it first, read the table, then decide.

Usage:
  python scripts/adjudicate-sealed.py <doc.json>                        # report only
  python scripts/adjudicate-sealed.py <doc.json> --ref REF --out NEW.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from kessler.datasets import load_all  # noqa: E402
from kessler.selftest import effect_hit, final_reply_of  # noqa: E402


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="adjudicate-sealed")
    p.add_argument("document", help="engagement JSON document (the sealed run)")
    p.add_argument("--ref", help="new ref for the corrected document (required with --out)")
    p.add_argument("--out", help="write the corrected document here (only when rows flip)")
    args = p.parse_args(argv)

    techs = {t.id: t for ts in load_all().values() for t in ts}
    doc = json.loads(Path(args.document).read_text(encoding="utf-8"))
    rows = doc["attempts"]
    hits = [r for r in rows if r.get("succeeded")]
    print(f"{args.document}: {len(rows)} attempts, {len(hits)} recorded hit(s)")
    print("-" * 96)
    flips = []
    for r in hits:
        tid = r["technique"].split(":", 1)[1]
        t = techs.get(tid)
        assert t is not None, f"technique {tid!r} not found in datasets/ - re-score impossible"
        text, conducted = final_reply_of(r["observed"])
        now = effect_hit(t, text)
        variant = effect_hit(t, r["observed"])  # what evidence-window scoring would say
        note = ""
        if variant != now:
            note = f"  [evidence-window variant: {variant} - recorded error mode, D-039]"
        print(f"{r['technique']} | {r['category']} | final-reply scored: {now}"
              f"{'  FLIPS -> held' if now is False else ''}{note}")
        if now != r.get("succeeded"):
            flips.append(r)
    print("-" * 96)
    print(f"{len(flips)} row(s) would flip under the current oracle "
          f"(final-reply semantics; conservative direction only)")
    if not args.out:
        print("(report only - pass --ref and --out to write the corrected document)")
        return 0
    if not args.ref:
        print("REFUSED: --out requires --ref (supersession registers under a new ref, C-9)",
              file=sys.stderr)
        return 2
    doc["engagement"]["ref"] = args.ref
    for r in flips:
        assert r.get("succeeded") is True
        r["succeeded"] = False
    text = json.dumps(doc, indent=2, ensure_ascii=False) + "\n"
    from kessler.schema import loads  # validate: the corrected doc still constructs
    eng = loads(text)
    assert len(eng.attempts) == len(rows), "row count drifted while adjudicating"
    hits_after = sum(1 for a in eng.attempts if a.succeeded)
    Path(args.out).write_bytes(text.encode("utf-8"))
    print(f"WROTE {args.out}: ref={args.ref}, {len(flips)} flip(s), "
          f"{hits_after} hit(s) remain (validated through the loader's C-1 gate)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
