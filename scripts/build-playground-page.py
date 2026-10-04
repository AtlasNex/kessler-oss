#!/usr/bin/env python3
"""Build site/playground/index.html (S-9, s32/K3): the "what a rate means" playground.

Server-side default state = the A7 example (1 of 25) computed by the kernel's own
wilson_interval; the JS layer adds live sliders. Educational only: zero claims about any
real target. no-JS readers get the computed example table."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import importlib.util as _ilu
_spec = _ilu.spec_from_file_location("_br", ROOT / "scripts" / "build-reports.py")
_br = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_br)

from kessler.asi import wilson_interval

EXAMPLES = [
    ("A7 self-test", 25, 1, "the run we publish"),
    ("baseline BASE-001", 158, 0, "0 hits over 158 attempts"),
    ("honeypot BENCH-G2A-001", 1065, 3, "3 hits over 1,065 attempts"),
    ("the classic", 9, 7, '"78% of 9 attempts" without an interval'),
]


def pct(x):
    return f"{x * 100:.1f}%"


def band(k, n):
    lo, hi = wilson_interval(k, n)
    return f"[{pct(lo)}, {pct(hi)}]"


def svg_for(k, n, big=False):
    lo, hi = wilson_interval(k, n)
    p = k / n if n else 0
    h = 40
    y = 20 if not big else 20
    return (
        f'<svg viewBox="0 0 100 {h}" role="img" aria-label="rate {pct(p)}, 95% band '
        f'{band(k, n)}" style="width:100%;height:auto">'
        '<line x1="0" y1="20" x2="100" y2="20" stroke="#DDD9CF" stroke-width="0.5"/>'
        + "".join(
            f'<line x1="{t}" y1="17" x2="{t}" y2="23" stroke="#DDD9CF" stroke-width="0.4"/>'
            f'<text x="{t}" y="31" font-size="3.6" text-anchor="middle" fill="#545D6B">{t}%</text>'
            for t in (0, 25, 50, 75, 100))
        + f'<rect x="{lo * 100:.2f}" y="12" width="{max(0.7, (hi - lo) * 100):.2f}" '
          'height="16" rx="2" fill="#8B7CF6" opacity="0.30"/>'
          f'<circle cx="{p * 100:.2f}" cy="20" r="3.2" fill="#5B45D6"/>'
          f'<text x="{min(96, max(4, p * 100)):.2f}" y="7" font-size="4.4" '
          f'text-anchor="middle" fill="#0A1631" font-weight="600">{pct(p)}</text></svg>')


def row_html(name, n, k, note):
    return (f"<tr><td>{name}</td><td class='kx-nowrap'>{k} / {n}</td>"
            f"<td class='kx-nowrap'>{pct(k / n if n else 0)}</td>"
            f"<td class='kx-nowrap'>{band(k, n)}</td><td>{note}</td></tr>")


widget = f"""
<section class="kx-play" data-wilson>
<h2 id="move-the-sliders">Move the sliders</h2>
<div class="kx-play-grid">
<div class="kx-play-controls">
<label>attempts (N)
<input type="range" data-wilson-n min="1" max="400" value="25" aria-label="attempts">
<output data-wilson-n-out>25</output></label>
<label>successes (hits)
<input type="range" data-wilson-hits min="0" max="25" value="1" aria-label="successes">
<output data-wilson-hits-out>1</output></label>
<div class="kx-presets">
<button type="button" data-wilson-preset="25,1">A7: 1 of 25</button>
<button type="button" data-wilson-preset="9,7">"78% of 9 attempts"</button>
<button type="button" data-wilson-preset="158,0">0 of 158 (baseline)</button>
<button type="button" data-wilson-preset="1065,3">3 of 1,065 (honeypot)</button>
</div>
</div>
<div class="kx-play-viz" data-wilson-svg-wrap>
{svg_for(1, 25)}
<p class="kx-play-note">rate <b data-wilson-rate>4.0%</b> · 95% band
<b data-wilson-band>[0.7%, 19.5%]</b></p>
</div>
</div>
<p class="kx-plain" data-wilson-plain>We are 95% sure the true rate is between <b>0.7%</b>
and <b>19.5%</b>.</p>
<p class="ax-sub">Same arithmetic as the kernel (<code>kessler.asi.wilson_interval</code>,
z=1.959963984540054) - the harness uses it on every published rate. This page makes no claim about any
real target; it exists to make one sentence obvious: <b>a bare percentage without N and an
interval is false precision.</b></p>
</section>
"""

body = f"""
<h1>What a rate means</h1>
<p class="ax-sub" style="max-width:64ch">Nearly every AI-security number you will be shown
this quarter is a percentage with no denominator. Move the sliders: the dot is the rate, the
band is where the truth is 95% likely to sit given that N. Watch what happens to the band
when N is small - that band is the honest part of every number we publish.</p>
{widget}
<h2 id="worked-examples">Worked examples from our own published numbers</h2>
<div class="kx-scroll"><table class="ax-table">
<thead><tr><th>Case</th><th>hits / N</th><th>rate</th><th>95% band</th><th>note</th></tr></thead>
<tbody>{"".join(row_html(*e) for e in EXAMPLES)}</tbody>
</table></div>
<p class="ax-sub">Computed at build time by the same kernel function the harness runs; the
sliders run the same formula in your browser. Neither is a verdict about anything.</p>
"""

html = _br.html_for("What a rate means: the interval playground | Kessler by AtlasNex",
                    body, og="playground", kind="Interactive · measurement")
assert "\u2014" not in html, "em dash in shipped copy"
out = ROOT / "site" / "playground"
out.mkdir(exist_ok=True)
(out / "index.html").write_text(html, encoding="utf-8")
print(f"built site/playground/index.html ({len(html)} bytes)")
