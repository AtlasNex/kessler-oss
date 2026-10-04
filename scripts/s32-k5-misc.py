"""K5 misc edits (asserted, atomic): manifest links, log links, kx v5 bumps, verify badge
section, deploy chain additions."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
H = Path("E:/Sanjay Files/StartUp/AtlasNex/atlasnex-hq")


def edit(path: Path, pairs: list[tuple[str, str]]) -> None:
    t = path.read_text(encoding="utf-8")
    for old, new in pairs:
        cnt = t.count(old)
        if cnt != 1:
            raise SystemExit(f"ANCHOR FAIL {path.name}: {cnt} for {old[:80]!r}")
        t = t.replace(old, new, 1)
    path.write_text(t, encoding="utf-8", newline="")
    print(f"edited {path.name} ({len(pairs)} edits)")


# 1) build-reports: manifest + log footer link + v5 bumps
edit(ROOT / "scripts" / "build-reports.py", [
    ('<meta name="theme-color" content="#060E22">',
     '<meta name="theme-color" content="#060E22">\n'
     '<link rel="manifest" href="/manifest.webmanifest">'),
    (' · <a href="https://atlasnex.com">atlasnex.com</a></div>',
     ' · <a href="/log/">log</a> · <a href="https://atlasnex.com">atlasnex.com</a></div>'),
    ('<link rel="stylesheet" href="/kx.css?v=4">', '<link rel="stylesheet" href="/kx.css?v=5">'),
    ('<script src="/kx.js?v=4" defer></script>', '<script src="/kx.js?v=5" defer></script>'),
])

# 2) index: manifest + v5 + footer col log link
edit(ROOT / "site" / "index.html", [
    ('<meta name="theme-color" content="#060E22">',
     '<meta name="theme-color" content="#060E22">\n'
     '<link rel="manifest" href="/manifest.webmanifest">'),
    ('<link rel="stylesheet" href="/kx.css?v=4">', '<link rel="stylesheet" href="/kx.css?v=5">'),
    ('<script src="/kx.js?v=4" defer></script>', '<script src="/kx.js?v=5" defer></script>'),
    ('<a href="g2/">Live scoreboard</a>',
     '<a href="g2/">Live scoreboard</a><a href="log/">Night Shift log</a>'),
])

# 3) serve.py: manifest + v5 + badge section on /verify/
edit(ROOT / "site" / "serve.py", [
    ('<meta name="theme-color" content="#060E22">',
     '<meta name="theme-color" content="#060E22">\n'
     '<link rel="manifest" href="/manifest.webmanifest">'),
    ('<link rel="stylesheet" href="/kx.css?v=4">', '<link rel="stylesheet" href="/kx.css?v=5">'),
    ('<script src="/kx.js?v=4" defer></script>', '<script src="/kx.js?v=5" defer></script>'),
])

# The serve.py badge: insert VERIFY_BADGE constant + splice it after the widget line
t = (ROOT / "site" / "serve.py").read_text(encoding="utf-8")
BADGE = '''VERIFY_BADGE = """
<h3 class="kx-badge-h">The embeddable badge</h3>
<p class="kx-note">For any engagement whose capsule is anchored here: embed the badge. It
links to the recomputable number, never to a verdict, and we do not issue badges for
findings - only for capsules that recompute.</p>
<div class="kx-badge-preview">
<img src="/badge/kx-verified.svg" alt="Kessler: checkable measurement" width="340" height="84">
</div>
<pre class="kx-embed">&lt;a href="https://kessler.atlasnex.com/verify/"&gt;&lt;img
 src="https://kessler.atlasnex.com/badge/kx-verified.svg"
 alt="Kessler: checkable measurement" width="340" height="84"&gt;&lt;/a&gt;</pre>
"""


'''
anchor = "def verify_page() -> str:"
cnt = t.count(anchor)
if cnt != 1:
    raise SystemExit(f"serve.py verify_page anchor: {cnt}")
t = t.replace(anchor, BADGE + anchor, 1)

anchor2 = "            + widget\n"
cnt = t.count(anchor2)
if cnt != 1:
    raise SystemExit(f"serve.py widget splice: {cnt}")
t = t.replace(anchor2, "            + widget\n            + VERIFY_BADGE\n", 1)
(ROOT / "site" / "serve.py").write_text(t, encoding="utf-8", newline="")
print("serve.py: badge section installed")

# 4) deploy chain: log + icons after playground
edit(H / "scripts" / "deploy_kessler_site.sh", [
    ('(cd "$K" && uv run --no-project --with markdown python scripts/build-playground-page.py) || '
     '{ echo "playground build failed"; exit 1; }',
     '(cd "$K" && uv run --no-project --with markdown python scripts/build-playground-page.py) || '
     '{ echo "playground build failed"; exit 1; }\n'
     '(cd "$K" && uv run --no-project --with markdown python scripts/build-log-page.py) || '
     '{ echo "log build failed"; exit 1; }\n'
     '(cd "$K" && python scripts/build-pwa-icons.py) || echo "warning: icon render skipped"'),
])

print("K5 misc edits applied")
