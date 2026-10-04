"""K1: wire kx.css + kx.js + font preloads + the one magnetic CTA into site/index.html.
Asserted anchors, ASCII-only insertions."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
p = ROOT / "site" / "index.html"
t = p.read_text(encoding="utf-8")

A_old = '<link rel="stylesheet" href="https://atlasnex.com/ui/v1/atlasnex-ui.css">'
A_new = (
    A_old + "\n"
    '<link rel="preload" href="/assets/fonts/sora-latin-700-normal.woff2" as="font" '
    'type="font/woff2" crossorigin>\n'
    '<link rel="preload" href="/assets/fonts/hanken-grotesk-latin-400-normal.woff2" as="font" '
    'type="font/woff2" crossorigin>\n'
    '<link rel="stylesheet" href="/kx.css?v=1">'
)
assert t.count(A_old) == 1, "house css link anchor"
t = t.replace(A_old, A_new, 1)

B_old = "</body>"
B_new = '<script src="/kx.js?v=1" defer></script>\n</body>'
assert t.count(B_old) == 1, "body close anchor"
t = t.replace(B_old, B_new, 1)

C_old = '<a class="ax-btn primary" data-cta="commission-r1" href="start/r1/">Commission an R1'
C_new = '<a class="ax-btn primary" data-mag data-cta="commission-r1" href="start/r1/">Commission an R1'
assert t.count(C_old) == 1, "hero CTA anchor"
t = t.replace(C_old, C_new, 1)

for frag in (A_new, B_new, C_new):
    assert all(ord(c) < 128 for c in frag), "non-ascii insertion"
p.write_text(t, encoding="utf-8", newline="")
print("index.html wired: kx.css + kx.js + 2 font preloads + data-mag on hero CTA")
