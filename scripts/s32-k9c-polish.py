"""K9 mockup-A polish 3 (final micro-pass): hit-badge readability, inspector gap fill, queue
breathing room."""
from pathlib import Path

P = Path(__file__).resolve().parent.parent / "docs" / "design" / "k9-konsole" / "konsole-a.html"
t = P.read_text(encoding="utf-8")

PAIRS = [
    (".st.hit{color:var(--red);background:rgba(255,92,92,.12);",
     ".st.hit{color:#FF9E9E;background:rgba(255,92,92,.14);"),
    ('<div class="ev" id="iTrace"><span style="color:var(--vio2)">trace</span> '
     '[scan] parse -&gt; decide(deny) -&gt; reply("i cannot share that") '
     '-&gt; audit(log) -&gt; chain(sealed)</div>',
     '<div class="ev" id="iTrace"><span style="color:var(--vio2)">trace</span> '
     '[scan] parse -&gt; decide(deny) -&gt; reply("i cannot share that") '
     '-&gt; audit(log) -&gt; chain(sealed)</div>\n'
     '      <div class="ev"><span style="color:var(--vio2)">chain</span> link 13/27 '
     '&middot; hash ok &middot; prev ok &middot; head 00d525c4&hellip;</div>'),
    (".queue{display:flex;gap:12px;align-items:center;border-top:1px solid var(--line2);"
     "padding:10px 16px}",
     ".queue{display:flex;gap:12px;align-items:center;border-top:1px solid var(--line2);"
     "padding:12px 16px 14px}"),
]

for old, new in PAIRS:
    cnt = t.count(old)
    if cnt != 1:
        raise SystemExit(f"ANCHOR FAIL ({cnt}): {old[:80]!r}")
    t = t.replace(old, new, 1)

P.write_text(t, encoding="utf-8", newline="")
print(f"konsole-a.html polish 3 ({len(PAIRS)} edits)")
