"""K9 mockup v4 polish 2 (reviewer gripes): clock box, lanehead baseline, badge column,
highlighter overshoot, tag uniformity, seq alignment, chain wording, CTA weight, note, playhead."""
from pathlib import Path

P = Path(__file__).resolve().parent.parent / "docs" / "design" / "k9-konsole" / "konsole-v4.html"
t = P.read_text(encoding="utf-8")

PAIRS = [
    (".clock{font:500 14px var(--mono);letter-spacing:.08em;font-variant-numeric:tabular-nums}",
     ".clock{font:500 14px var(--mono);letter-spacing:.08em;font-variant-numeric:tabular-nums;"
     "border:2px solid var(--ink);padding:6px 11px;background:var(--card)}"),
    (".lanehead{display:flex;align-items:center;gap:20px;padding:16px 22px 15px}",
     ".lanehead{display:flex;align-items:flex-end;gap:20px;padding:16px 22px 15px}"),
    (".lanehead h2{font:700 26px/1 var(--disp);letter-spacing:-.04em}",
     ".lanehead h2{font:700 26px/1 var(--disp);letter-spacing:-.04em;margin-bottom:4px}"),
    (".clause{font:700 15px var(--disp);color:var(--green-ink);border:2px solid currentColor;"
     "padding:3px 9px;rotate:-2deg;white-space:nowrap}",
     ".clause{font:700 15px var(--disp);color:var(--green-ink);border:2px solid currentColor;"
     "padding:4px 10px;rotate:-2deg;white-space:nowrap;margin-bottom:6px}"),
    (".hudchip{font:500 10px var(--mono);letter-spacing:.13em;text-transform:uppercase;"
     "border:2px solid var(--ink);padding:5px 10px;background:var(--paper2)}",
     ".hudchip{font:500 10px var(--mono);letter-spacing:.13em;text-transform:uppercase;"
     "border:2px solid var(--ink);padding:5px 10px;background:var(--paper2);margin-bottom:5px}"),
    (".counters{margin-left:auto;display:flex;gap:30px;text-align:right}",
     ".counters{margin-left:auto;display:flex;gap:30px;text-align:right;align-items:flex-end;"
     "padding-bottom:1px}"),
    (".row .seq{color:var(--lunar)}",
     ".row .seq{color:var(--lunar);text-align:right}"),
    (".st{justify-self:start;font:700 10px var(--mono);letter-spacing:.09em;text-transform:uppercase;\n"
     "  border:1.5px solid var(--paper);padding:4px 9px;animation:stampin .4s var(--ease) both;"
     "transform-origin:left center}",
     ".st{justify-self:start;font:700 10px var(--mono);letter-spacing:.09em;text-transform:uppercase;\n"
     "  border:1.5px solid var(--paper);padding:4px 8px;animation:stampin .4s var(--ease) both;"
     "transform-origin:left center;min-width:126px;text-align:center}"),
    ("var target=10+Math.min(82,(H/N*100)*1.4);",
     "var target=8+Math.min(70,(H/N*100)*1.3);"),
    ("<b>chain</b>line 13 of 27 &middot; hash ok &middot; link ok &middot; head 00d525c4&hellip;",
     "<b>chain</b>capsule link 13 of 27 &middot; hash ok &middot; head 00d525c4&hellip;"),
    (".act.mag{background:var(--cta);color:var(--paper)}",
     ".act.mag{background:var(--paper);color:var(--ink)}"),
    (".act.mag i{background:var(--paper);color:var(--ink)}",
     ".act.mag i{background:var(--cta);color:#FFFFFF}"),
    (".note{background:#FFD85A;border:1.5px solid var(--ink);box-shadow:3px 3px 0 var(--ink);"
     "padding:10px 12px 8px;\n  font-family:var(--hand);font-size:14.5px;line-height:1.35;"
     "rotate:-1.2deg;margin-top:auto}",
     ".note{background:#FFD85A;border:1.5px solid var(--ink);box-shadow:3px 3px 0 var(--ink);"
     "padding:10px 13px 8px;\n  font-family:var(--hand);font-size:15px;line-height:1.35;"
     "rotate:-1deg;margin:14px 3px 3px}"),
    (".head2{position:absolute;top:5px;width:5px;height:24px;background:var(--amber);"
     "border:1.5px solid var(--ink);transition:left .55s linear}",
     ".head2{position:absolute;top:5px;width:6px;height:24px;background:var(--amber);"
     "border:2px solid var(--ink);transition:left .55s linear}"),
]

for old, new in PAIRS:
    cnt = t.count(old)
    if cnt != 1:
        raise SystemExit(f"ANCHOR FAIL ({cnt}): {old[:80]!r}")
    t = t.replace(old, new, 1)

P.write_text(t, encoding="utf-8", newline="")
print(f"konsole-v4 polish2 applied ({len(PAIRS)} edits)")
