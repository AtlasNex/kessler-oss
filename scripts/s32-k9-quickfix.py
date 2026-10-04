"""K9 quickfix (owner-reported): real navigation on every surface + the log chip glue bug.
Also bumps kx.css v6 -> v7 (the file changes again; the audit already cached v6)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NEW_NAV = ('<nav class="ax-nav" aria-label="Main"><a href="/#method">Method</a>'
           '<a href="/#shell">Try it</a><a href="/verify/">Verify</a><a href="/log/">Log</a>'
           '<a href="/register/">Register</a><a href="/playground/">Playground</a>'
           '<a href="/pricing/">Pricing</a><a href="/reports/">Writeups</a>'
           '<a class="ax-btn primary" href="https://github.com/AtlasNex/kessler-oss">'
           'Get the harness</a></nav>')

OLD_INDEX = ('<nav class="ax-nav" aria-label="Main"><a href="#method">Method</a>'
             '<a href="#shell">Try it</a><a href="pricing/">Pricing</a>'
             '<a href="#writeups">Writeups</a><a href="#claims">Claims</a>'
             '<a href="#doors">Commission</a><a class="ax-btn primary" '
             'href="https://github.com/AtlasNex/kessler-oss">Get the harness</a></nav>')
OLD_SUB = ('<nav class="ax-nav" aria-label="Main"><a href="/#writeups">Writeups</a>'
           '<a class="ax-btn primary" href="https://github.com/AtlasNex/kessler-oss">'
           'Get the harness</a></nav>')
OLD_SERVE = ('<nav class="ax-nav" aria-label="Main"><a href="/reports/">Writeups</a>'
             '<a class="ax-btn primary" href="https://github.com/AtlasNex/kessler-oss">'
             'Get the harness</a></nav>')

CHIP_RULE = ('\n/* K9 quickfix: the log chips had NO styling - kind and title rendered glued. */\n'
             '.kx-log-item .kx-chip{font-family:var(--ax-mono);font-size:.7rem;'
             'letter-spacing:.05em;text-transform:uppercase;border:1px solid var(--ax-line);'
             'border-radius:999px;padding:3px 9px;color:var(--ax-muted);margin-right:10px;'
             'vertical-align:2px}\n'
             '.kx-log-item:hover{background:rgba(139,124,246,.05)}\n')


def edit(path: Path, pairs: list[tuple[str, str]]) -> None:
    t = path.read_text(encoding="utf-8")
    for old, new in pairs:
        cnt = t.count(old)
        if cnt != 1:
            raise SystemExit(f"ANCHOR FAIL {path.name}: {cnt} for {old[:80]!r}")
        t = t.replace(old, new, 1)
    path.write_text(t, encoding="utf-8", newline="")
    print(f"edited {path.name} ({len(pairs)} edits)")


edit(ROOT / "site" / "index.html", [(OLD_INDEX, NEW_NAV)])
edit(ROOT / "scripts" / "build-reports.py", [(OLD_SUB, NEW_NAV)])
edit(ROOT / "site" / "serve.py", [(OLD_SERVE, NEW_NAV)])

# kx.css: chip fix + v7 bump across the four referencing files
css = ROOT / "site" / "kx.css"
t = css.read_text(encoding="utf-8")
if ".kx-log-item .kx-chip" in t:
    raise SystemExit("chip rule already present")
css.write_text(t + CHIP_RULE, encoding="utf-8", newline="")
print("kx.css: chip rule + hover added")
for p in ("site/index.html", "scripts/build-reports.py", "site/serve.py", "site/sw.js"):
    f = ROOT / p
    t = f.read_text(encoding="utf-8")
    n = t.count("kx.css?v=6")
    if n != 1:
        raise SystemExit(f"v6 anchor {p}: {n}")
    f.write_text(t.replace("kx.css?v=6", "kx.css?v=7"), encoding="utf-8", newline="")
    print("v7 bump:", p)

print("K9 quickfix applied")
