"""K9 mockup-A polish pass (from the design critique): contrast, dead-void fill (queue strip),
flat button language, transport order, alignment fixes."""
from pathlib import Path

P = Path(__file__).resolve().parent.parent / "docs" / "design" / "k9-konsole" / "konsole-a.html"
t = P.read_text(encoding="utf-8")

PAIRS = [
    ("--dim:#6C7691;", "--dim:#8A93AC;"),
    ('<div id="rows" style="flex:1;min-height:0;display:flex;flex-direction:column"></div>',
     '<div id="rows" style="flex:1;min-height:0;display:flex;flex-direction:column;'
     'justify-content:flex-end"></div>'),
    (".viz{border-top:1px solid var(--line2);",
     ".queue{display:flex;gap:12px;align-items:center;border-top:1px solid var(--line2);padding:10px 16px}"
     ".queue .qo{font-family:var(--mono);font-size:10.5px;color:var(--dim);"
     "border:1px dashed var(--line);border-radius:999px;padding:3px 9px;transition:opacity .3s}"
     ".viz{border-top:1px solid var(--line2);"),
    ("      </div>\n    </section>\n  </main>",
     "      </div>\n      <div class=\"queue\"><span class=\"cap\">QUEUE</span>"
     "<div id=\"qrows\" style=\"display:flex;gap:8px;flex-wrap:wrap\"></div></div>\n"
     "    </section>\n  </main>"),
    ("background:linear-gradient(180deg,rgba(139,124,246,.16),rgba(139,124,246,.05));",
     "background:rgba(139,124,246,.09);border:1px solid rgba(139,124,246,.28);"),
    (".act.mag{background:linear-gradient(180deg,rgba(255,182,39,.16),rgba(255,182,39,.05));"
     "border-color:rgba(255,182,39,.35)}",
     ".act.mag{background:rgba(255,182,39,.10);border-color:rgba(255,182,39,.35)}"),
    ('      <button class="tbtn" id="btnStep" title="step">&#9197;</button>\n'
     '      <button class="tbtn on" id="btnPlay" title="play/pause">&#10074;&#10074;</button>',
     '      <button class="tbtn on" id="btnPlay" title="play/pause">&#10074;&#10074;</button>\n'
     '      <button class="tbtn" id="btnStep" title="step">&#9197;</button>'),
    ("grid-template-columns:44px 74px 86px 1fr 96px 64px",
     "grid-template-columns:44px 74px 86px 1fr 96px 74px"),
    (".kpi dd em{color:var(--grn);font-style:normal;font-size:11px}",
     ".kpi dd em{color:var(--grn);font-style:normal;font-size:11px;vertical-align:middle}"),
    (".nexcorner img{width:44px}", ".nexcorner img{width:52px}"),
    ('var hitMk=document.createElement("div"); hitMk.className="mk hit"; '
     'hitMk.style.left=(3/24*100)+"%"; track.appendChild(hitMk);',
     'var hitMk=document.createElement("div"); hitMk.className="mk hit"; '
     'hitMk.style.left=(3/24*100)+"%"; track.appendChild(hitMk);\n'
     'var qrows=document.getElementById("qrows");'
     'RUN.slice(6,16).forEach(function(r){var s=document.createElement("span");'
     's.className="qo";s.textContent=r[0];qrows.appendChild(s);});'),
    ("  el.click();bandDraw();sparkDraw();i++;",
     "  el.click();bandDraw();sparkDraw();\n"
     "  if(qrows&&qrows.firstChild){qrows.removeChild(qrows.firstChild);}i++;"),
]

for old, new in PAIRS:
    cnt = t.count(old)
    if cnt != 1:
        raise SystemExit(f"ANCHOR FAIL ({cnt}): {old[:80]!r}")
    t = t.replace(old, new, 1)

P.write_text(t, encoding="utf-8", newline="")
print(f"konsole-a.html polished ({len(PAIRS)} edits)")
