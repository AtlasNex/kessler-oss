"""K9 mockup-A polish pass 2 (critique round 2): top-anchored fuller stream, visible queue
chips, brighter small labels, calmer replay badge, inspector trace block."""
from pathlib import Path

P = Path(__file__).resolve().parent.parent / "docs" / "design" / "k9-konsole" / "konsole-a.html"
t = P.read_text(encoding="utf-8")

PAIRS = [
    ("--dim:#8A93AC;", "--dim:#97A0B5;"),
    ('style="flex:1;min-height:0;display:flex;flex-direction:column;justify-content:flex-end"',
     'style="flex:1;min-height:0;display:flex;flex-direction:column"'),
    ("while(rows.children.length>8){rows.removeChild(rows.lastChild);}",
     "while(rows.children.length>13){rows.removeChild(rows.lastChild);}"),
    (".queue .qo{font-family:var(--mono);font-size:10.5px;color:var(--dim);"
     "border:1px dashed var(--line);border-radius:999px;padding:3px 9px;transition:opacity .3s}",
     ".queue .qo{font-family:var(--mono);font-size:10.5px;color:var(--mut);"
     "border:1px solid rgba(139,124,246,.30);background:rgba(139,124,246,.07);"
     "border-radius:999px;padding:3px 9px;transition:opacity .3s}"),
    ('RUN.slice(6,16).forEach(function(r){', 'RUN.slice(7,22).forEach(function(r){'),
    ('<div class="ev" id="iEv">select a row</div>',
     '<div class="ev" id="iEv">select a row</div>\n'
     '      <div class="ev" id="iTrace"><span style="color:var(--vio2)">trace</span> '
     '[scan] parse -&gt; decide(deny) -&gt; reply("i cannot share that") '
     '-&gt; audit(log) -&gt; chain(sealed)</div>'),
    ('.badge-live{font-family:var(--mono);font-size:10px;letter-spacing:.16em;color:#04091A;'
     'background:var(--amb);\n  border-radius:999px;padding:4px 10px;font-weight:700}',
     '.badge-live{font-family:var(--mono);font-size:10px;letter-spacing:.16em;color:var(--amb);'
     'background:rgba(255,182,39,.08);\n  border:1px solid rgba(255,182,39,.55);'
     'border-radius:999px;padding:4px 10px;font-weight:700}'),
    ('g.fillStyle="#6C7691";g.font="9px monospace";g.fillText("0%",8,52);g.fillText("100%",188,52);',
     'g.fillStyle="#97A0B5";g.font="9px monospace";g.fillText("0%",8,52);g.fillText("100%",188,52);'),
    ('g.fillStyle="#6C7691";g.font="9px monospace";g.fillText("hits",8,52);',
     'g.fillStyle="#97A0B5";g.font="9px monospace";g.fillText("hits",8,52);'),
]

for old, new in PAIRS:
    cnt = t.count(old)
    if cnt != 1:
        raise SystemExit(f"ANCHOR FAIL ({cnt}): {old[:80]!r}")
    t = t.replace(old, new, 1)

P.write_text(t, encoding="utf-8", newline="")
print(f"konsole-a.html polish 2 ({len(PAIRS)} edits)")
