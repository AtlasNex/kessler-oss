#!/usr/bin/env python3
"""Render og/*.png social cards (S-11) from the built pages themselves.

Source of truth: each built page carries <meta property="og:image" content=".../og/<slug>.png">,
< meta property="og:title"> and <meta name="kx:kind">. This tool scans site/**, renders one
1200x630 card per slug via headless Chrome (kit visual language: midnight gradient, orbit,
beacon dot), and REFUSES loudly if any page still carries the __OG__ placeholder - a builder
that forgot the fill must not ship a broken meta. Idempotent: re-renders every card."""
import re
import subprocess
import sys
from html import escape
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
OG = SITE / "og"
CHROME = "C:/Program Files/Google/Chrome/Application/chrome.exe"

OG_RE = re.compile(
    r'<meta property="og:image" content="https://kessler\.atlasnex\.com/og/([a-z0-9-]+)\.png">')
TITLE_RE = re.compile(r'<meta property="og:title" content="([^"]*)">')
KIND_RE = re.compile(r'<meta name="kx:kind" content="([^"]*)">')

CARD = """<!doctype html><html><head><meta charset="utf-8"><style>
@font-face{{font-family:'Sora';font-weight:600;src:url(../assets/fonts/sora-latin-600-normal.woff2)}}
@font-face{{font-family:'Sora';font-weight:700;src:url(../assets/fonts/sora-latin-700-normal.woff2)}}
@font-face{{font-family:'JetBrains Mono';font-weight:500;src:url(../assets/fonts/jetbrains-mono-latin-500-normal.woff2)}}
*{{box-sizing:border-box;margin:0}}html,body{{width:1200px;height:630px;overflow:hidden}}
body{{background:radial-gradient(1100px 700px at 72% 18%,#1A2F68 0,#0A1631 52%,#060E22 100%);
font-family:'Sora',sans-serif;color:#F6F4EF;position:relative;-webkit-font-smoothing:antialiased}}
.orbit{{position:absolute;left:46%;top:-32%;width:900px;height:520px;border:2px solid rgba(80,110,190,.30);border-radius:50%;transform:rotate(-14deg)}}
.orbit.o2{{left:38%;top:-56%;width:1300px;height:760px;border-color:rgba(80,110,190,.22)}}
.wrap{{position:absolute;inset:0;padding:60px 72px;display:flex;flex-direction:column;justify-content:space-between}}
.brand{{display:flex;align-items:center;gap:11px}}
.dot{{width:13px;height:13px;border-radius:50%;background:#8B7CF6}}
.brand b{{font-weight:700;font-size:27px;letter-spacing:-.02em}}
.brand span{{color:#A9B1C4;font-size:17px;margin-left:2px}}
.kind{{font-family:'JetBrains Mono',monospace;font-weight:500;font-size:15px;letter-spacing:.14em;text-transform:uppercase;color:#8B7CF6}}
h1{{font-weight:600;font-size:{size}px;line-height:1.1;letter-spacing:-.025em;margin:14px 0 22px;max-width:1020px}}
.foot{{font-family:'JetBrains Mono',monospace;font-size:15px;letter-spacing:.06em;color:#8C95AB}}
</style></head><body>
<div class="orbit"></div><div class="orbit o2"></div>
<div class="wrap">
<div class="brand"><span class="dot"></span><b>Kessler</b><span>by AtlasNex</span></div>
<div><div class="kind">{kind}</div><h1>{title}</h1><div class="foot">kessler.atlasnex.com &middot; measured, dated, scoped</div></div>
</div></body></html>"""


def card_for(title: str, kind: str) -> str:
    n = len(title)
    size = 58 if n <= 48 else 48 if n <= 90 else 40
    return CARD.format(size=size, kind=escape(kind), title=escape(title))


def render(slug: str, title: str, kind: str) -> tuple[bool, int]:
    OG.mkdir(exist_ok=True)
    tmp = OG / f"_card-{slug}.html"
    tmp.write_text(card_for(title, kind), encoding="utf-8")
    out = OG / f"{slug}.png"
    url = "file:///" + quote(tmp.as_posix(), safe="/:")
    try:
        subprocess.run(
            [CHROME, "--headless=new", "--disable-gpu", "--no-first-run", "--hide-scrollbars",
             "--virtual-time-budget=4000", "--window-size=1200,630",
             f"--screenshot={out}", url],
            capture_output=True, timeout=90, check=False)
    finally:
        tmp.unlink(missing_ok=True)
    ok = out.exists() and out.stat().st_size > 8000
    return ok, (out.stat().st_size if out.exists() else 0)


def main() -> int:
    if not Path(CHROME).exists():
        print("og render: chrome not found at", CHROME, "- cards not re-rendered")
        return 2
    want: dict[str, tuple[str, str]] = {}
    leaks = []
    for f in SITE.rglob("*.html"):
        t = f.read_text(encoding="utf-8", errors="replace")
        if "__OG__" in t:
            leaks.append(str(f.relative_to(SITE)))
        m = OG_RE.search(t)
        if not m:
            continue
        slug = m.group(1)
        tm = TITLE_RE.search(t)
        km = KIND_RE.search(t)
        if slug not in want:
            want[slug] = (tm.group(1) if tm else "Kessler by AtlasNex",
                          km.group(1) if km else "Published")
    if leaks:
        print("REFUSED: pages still carry the __OG__ placeholder (builders must fill it):")
        for l in leaks:
            print("  ", l)
        return 1
    bad = []
    for slug, (title, kind) in sorted(want.items()):
        ok, size = render(slug, title, kind)
        print(("ok   " if ok else "FAIL ") + f"og/{slug}.png ({size}B)")
        if not ok:
            bad.append(slug)
    print(f"og render: {len(want) - len(bad)}/{len(want)} cards, "
          f"{'ALL OK' if not bad else 'FAILURES: ' + ', '.join(bad)}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
