#!/usr/bin/env python3
"""Render the PWA icons (S-12) from the kit visual language: beacon dot + Sora K on midnight."""
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
ICONS = SITE / "icons"
CHROME = "C:/Program Files/Google/Chrome/Application/chrome.exe"

CARD = """<!doctype html><html><head><meta charset="utf-8"><style>
@font-face{{font-family:'Sora';font-weight:700;src:url(../assets/fonts/sora-latin-700-normal.woff2)}}
@font-face{{font-family:'JetBrains Mono';font-weight:500;src:url(../assets/fonts/jetbrains-mono-latin-500-normal.woff2)}}
*{{box-sizing:border-box;margin:0}}html,body{{width:{size}px;height:{size}px;overflow:hidden}}
body{{background:radial-gradient(circle at 68% 26%,#1A2F68 0,#0A1631 54%,#060E22 100%);
position:relative;display:flex;align-items:center;justify-content:center;
-webkit-font-smoothing:antialiased}}
.k{{font-family:'Sora',sans-serif;font-weight:700;font-size:{kfont}px;color:#F6F4EF;letter-spacing:-0.04em;line-height:1}}
.dot{{position:absolute;left:{dotx}px;top:{doty}px;width:{dots}px;height:{dots}px;border-radius:50%;background:#8B7CF6}}
.mono{{position:absolute;bottom:{mony}px;left:0;right:0;text-align:center;
font-family:'JetBrains Mono',monospace;font-weight:500;font-size:{monof}px;letter-spacing:.22em;color:#8C95AB}}
</style></head><body><span class="k">K</span><span class="dot"></span>
<div class="mono">KESSLER</div></body></html>"""

SPECS = [
    ("icon-192.png", 192, 104, 0.78, 13, 9.5),
    ("icon-512.png", 512, 278, 0.78, 34, 26),
    ("icon-512-maskable.png", 512, 196, 0.62, 60, 44),
]


def render(name: str, size: int, kfont: int, dot_frac: float, monof: float, mony: float) -> bool:
    ICONS.mkdir(exist_ok=True)
    tmp = ICONS / f"_tmp-{name}.html"
    k = size / 2
    dotx = k + kfont * 0.42
    doty = k - kfont * 0.62
    dots = size * 0.075
    tmp.write_text(CARD.format(size=size, kfont=kfont, dotx=dotx, doty=doty,
                               dots=dots, monof=monof, mony=mony), encoding="utf-8")
    out = ICONS / name
    url = "file:///" + quote(tmp.as_posix(), safe="/:")
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-first-run",
                    "--hide-scrollbars", f"--window-size={size},{size}",
                    "--virtual-time-budget=3000", f"--screenshot={out}", url],
                   capture_output=True, timeout=60, check=False)
    tmp.unlink(missing_ok=True)
    ok = out.exists() and out.stat().st_size > 1500
    print(("ok   " if ok else "FAIL ") + f"icons/{name} ({out.stat().st_size if out.exists() else 0}B)")
    return ok


if not Path(CHROME).exists():
    print("icons: chrome not found; keeping committed icons")
    sys.exit(2)
ok = all(render(*s) for s in SPECS)
sys.exit(0 if ok else 1)
