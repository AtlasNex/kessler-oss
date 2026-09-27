"""Kessler brand shell (session 18 GUI rehaul).

One design system for every surface — the client report, the viewer, the review workbench.
The old system had three problems this fixes:

1. **The CSS lived in html_report.py** and every surface bolted page-specific <style> on top,
   so the same badge/button/card drifted between pages.
2. **One font down to 0.68rem** — the report is a deliverable a CTO reads; long prose in mono at
   10px is why it read like a terminal dump instead of a paid engagement.
3. **Zero navigation on a 9-section document** — no TOC, no back-to-top, sections unnumbered in
   the DOM.

Design rules (D-022 lineage, evolved):
* terminal-realism kept in the *chrome* (prompt line, amber, grid, mono for IDs/payloads),
  but evidence is quoted from a source-of-record, not read as body copy — data prose is sans;
* every measured number carries its interval; a chart with a single point and no error band is
  a lie about precision — the ASR viz draws the 95% band explicitly;
* motion respects prefers-reduced-motion; nothing here is load-bearing for meaning (color is
  always accompanied by a text label — the severity badge says the word).
* pure CSS/HTML: no JS requirement (progressive enhancement only), C-2 stdlib-safe.
"""
from __future__ import annotations

from html import escape as _html_escape

#: Brand palette (D-022): Kessler amber on terminal black. Single source of truth.
TOKENS = """
:root {
  /* surfaces */
  --bg: #0b0d10; --bg2: #11151b; --bg3: #161c24;
  --border: #1c2128; --border2: #2a313c;
  /* type */
  --text: #e8e8e8; --fg: var(--text); --dim: #9ba6b1; --muted: #818b96;
  /* brand + semantics */
  --amber: #ffb627; --amber2: #ffc752; --amber-dim: rgba(255,182,39,.09);
  --crit: #ff4a5f; --high: #ff7a4a; --med: #ffb627; --low: #5fa8ff; --info: #5fd97a;
  --ok: #5fd97a; --violet: #b58cff;
  /* type scale (session 18: read at column width, not squinted at) */
  --mono: ui-monospace, 'JetBrains Mono', Menlo, Consolas, monospace;
  --sans: system-ui, -apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
  /* rhythm */
  --gap: 1rem; --radius: 8px; --maxw: 60rem;
}
"""

CSS = TOKENS + """
* { box-sizing: border-box; margin: 0; padding: 0; }
html { scroll-behavior: smooth; }
body { background: var(--bg); color: var(--text); font-family: var(--sans);
       font-size: 15px; line-height: 1.6; padding: 2.5rem 1.5rem 5rem; }
main { max-width: var(--maxw); margin: 0 auto; position: relative; z-index: 1; }
.grid-bg { position: fixed; inset: 0; pointer-events: none; z-index: 0;
  background-image: linear-gradient(rgba(255,255,255,.012) 1px, transparent 1px),
                    linear-gradient(90deg, rgba(255,255,255,.012) 1px, transparent 1px);
  background-size: 48px 48px; }

/* ---- masthead: the console opening (kept from D-022; it IS the brand voice) ---- */
header.masthead { border: 1px solid var(--border2); border-radius: var(--radius);
  background: linear-gradient(180deg, var(--bg2), var(--bg)); padding: 1.4rem 1.6rem;
  margin-bottom: 2rem; }
.prompt { color: var(--muted); font-family: var(--mono); font-size: .8rem; }
.prompt b { color: var(--amber); font-weight: 600; }
.prompt::before { content: "$ "; color: var(--amber); opacity: .6; }
h1 { color: var(--amber); font-family: var(--mono); font-size: 1.45rem;
     letter-spacing: -0.01em; margin: .45rem 0 .15rem; line-height: 1.35;
     overflow-wrap: anywhere; }
.meta { color: var(--dim); font-size: .82rem; font-family: var(--mono);
  overflow-wrap: anywhere; }
.meta code { padding: .14em .45em; }
h2 { color: var(--amber); font-family: var(--mono); font-size: 1.02rem;
     margin: 2.6rem 0 .9rem; padding-bottom: .35rem;
     border-bottom: 1px solid var(--border2); letter-spacing: -0.01em; }
h2 .no { color: var(--muted); margin-right: .5rem; }
h3 { color: var(--text); font-size: 1.05rem; margin: 1.2rem 0 .4rem; }
a { color: var(--amber2); }
.label { color: var(--muted); text-transform: uppercase; font-size: .72rem;
         letter-spacing: .14em; margin: 1rem 0 .3rem; font-family: var(--mono); }
code, pre { font-family: var(--mono); }
code { color: var(--amber2); font-size: .82em; background: var(--amber-dim);
       border-radius: 4px; padding: .02em .3em; line-height: 1.5; }
pre { background: var(--bg2); border: 1px solid var(--border); border-radius: 6px;
      padding: .8rem 1rem; overflow-x: auto; margin: .5rem 0 1rem; color: var(--dim);
      font-size: .8rem; white-space: pre-wrap; word-break: break-word; }
blockquote, p { max-width: 68ch; }
ol, ul { padding-left: 1.45rem; } li { margin: .22rem 0; }

/* ---- tables: aligned, readable, hairline rows ---- */
table { width: 100%; border-collapse: collapse; margin: .8rem 0 1.2rem; font-size: .85rem; }
th { color: var(--dim); text-align: left; font-weight: 600; font-family: var(--mono);
     font-size: .75rem; letter-spacing: .04em; text-transform: uppercase;
     border-bottom: 1px solid var(--border2); padding: .5rem .7rem; }
td { border-bottom: 1px solid var(--border); padding: .5rem .7rem; vertical-align: top; }
tr:hover td { background: var(--bg2); }
.mono-cells td { font-family: var(--mono); font-size: .82rem; }
.kv-table th { width: 10rem; vertical-align: top; }
td .sev { vertical-align: middle; }
td.sep-center { text-align: center; }
.kv-table td { overflow-wrap: anywhere; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums;
     font-family: var(--mono); }

/* ---- scrollbars: the native grey bar clashes with the dark theme ---- */
* { scrollbar-width: thin; scrollbar-color: var(--border2) var(--bg); }
::-webkit-scrollbar { width: 10px; height: 10px; }
::-webkit-scrollbar-thumb { background: var(--border2); border-radius: 5px; }
::-webkit-scrollbar-track { background: var(--bg); }

/* ---- severity: pill + word, never color alone ---- */
.sev { display: inline-block; font-weight: 700; font-size: .68rem; letter-spacing: .09em;
       font-family: var(--mono); padding: .12rem .55rem; border-radius: 999px;
       border: 1px solid; }
.sev.critical { color: var(--crit); border-color: var(--crit); background: rgba(255,74,95,.08); }
.sev.high { color: var(--high); border-color: var(--high); background: rgba(255,122,74,.08); }
.sev.medium { color: var(--med); border-color: var(--med); background: rgba(255,182,39,.08); }
.sev.low { color: var(--low); border-color: var(--low); background: rgba(95,168,255,.08); }
.sev.info { color: var(--info); border-color: var(--info); background: rgba(95,217,122,.08); }

.card { background: var(--bg2); border: 1px solid var(--border); border-radius: var(--radius);
        padding: 1rem 1.2rem; margin: 1rem 0; }
.kv { color: var(--dim); font-size: .82rem; } .kv b { color: var(--text); font-weight: 600; }
.ok { color: var(--ok); } .warn { color: var(--crit); }
details summary { cursor: pointer; color: var(--amber2); font-size: .82rem; margin: .4rem 0; }
footer { margin-top: 4rem; color: var(--muted); font-size: .78rem; border-top: 1px solid var(--border);
         padding-top: 1rem; max-width: 80ch; }

/* ---- headline stat + ASR bar ---- */
.big { font-size: 2.6rem; color: var(--amber); font-weight: 700; letter-spacing: -0.03em;
       font-family: var(--mono); line-height: 1.1; }
.bar { height: 8px; background: var(--bg3); border: 1px solid var(--border2);
       border-radius: 4px; overflow: hidden; display: flex; margin: .35rem 0 .8rem; }
.bar i { display: block; height: 100%; }

/* ---- ASR chart (session 18): the interval is drawn, not just written ----
   A point without its band overstates precision; the band is the honest part. */
.asr-chart { display: grid; grid-template-columns: 9.5rem 1fr 14.5rem; gap: .45rem .9rem;
             align-items: center; margin: 1rem 0 1.4rem; font-size: .82rem; }
a code { background: none; padding: 0; }   # links already carry the accent; chip-in-link
                                             # read as a dark block behind the text (audit R4)
.asr-chart .cid { font-family: var(--mono); }
.asr-chart .cid a code { color: inherit; }
.asr-chart .track { position: relative; height: 18px; background: var(--bg3);
                    border: 1px solid var(--border2); border-radius: 4px;
                    background-image: linear-gradient(90deg, transparent 0 24.7%,
                      var(--border2) 24.7% 25%, transparent 25% 49.7%, var(--border2) 49.7% 50%,
                      transparent 50% 74.7%, var(--border2) 74.7% 75%, transparent 75% 100%); }
.asr-chart .band { position: absolute; top: 0; bottom: 0; background: rgba(255,182,39,.28); }
.asr-chart .point { position: absolute; top: 0; bottom: 0; width: 3px; margin-left: -1.5px;
                    background: var(--amber2); border-radius: 1px;
                    box-shadow: 0 0 0 1px rgba(0,0,0,.55); }
.asr-chart .n { color: var(--dim); font-family: var(--mono); font-size: .78rem;
                text-align: right; white-space: nowrap; }

/* ---- TOC (report) / nav chips (viewer, workbench) ---- */
nav.toc { border: 1px solid var(--border2); border-radius: var(--radius);
          background: var(--bg2); padding: .9rem 1.2rem; margin: 1.4rem 0 2rem; }
nav.toc .label { margin: 0 0 .4rem; }
nav.toc ol { list-style: none; display: grid; grid-template-columns: 1fr 1fr;
  gap: .1rem 2rem; padding: 0; }
nav.toc a { color: var(--dim); text-decoration: none; font-size: .84rem;
            font-family: var(--mono); line-height: 1.9; }
nav.toc a:hover { color: var(--amber); }
nav.chips { display: flex; gap: .4rem; flex-wrap: wrap; margin: 1rem 0; }
nav.chips a, nav.chips button { font-size: .76rem; font-family: var(--mono);
  text-decoration: none; border: 1px solid var(--border2); background: var(--bg2);
  padding: .26rem .75rem; border-radius: 999px; color: var(--dim); cursor: pointer;
  line-height: 1.4; display: inline-flex; align-items: center; height: 1.9rem;
  box-sizing: border-box; white-space: nowrap; }
nav.chips a:hover, nav.chips button:hover { color: var(--amber); border-color: var(--amber); }
nav.chips .on { color: var(--amber); border-color: var(--amber); }

/* ---- findings ---- */
.finding { border-left: 3px solid var(--border2); padding-left: 1.1rem; margin: 2rem 0;
           scroll-margin-top: 1.5rem; }
.finding.critical { border-left-color: var(--crit); }
.finding.high { border-left-color: var(--high); }
.finding.medium { border-left-color: var(--med); }
.finding.low { border-left-color: var(--low); }
.finding.info { border-left-color: var(--info); }

/* ---- attempt stream (viewer) ---- */
.stream { font-size: .78rem; color: var(--dim); max-height: 420px; overflow-y: auto;
  background: var(--bg2); border: 1px solid var(--border); border-radius: 6px;
  padding: .6rem .9rem; font-family: var(--mono); }
.stream div { overflow-wrap: anywhere; padding: .05rem 0; }
.stream .hit { color: var(--crit); font-weight: 700; border: 1px solid var(--crit);
  background: rgba(255,74,95,.08); border-radius: 999px; padding: 0 .45em; font-size: .68rem;
  letter-spacing: .08em; }
.stream .held { color: var(--dim); }

/* ---- MOTION (each rule has a reason; all disabled under reduced-motion) ---- */
/* ASR bars fill once on load: the bar is the measurement; animating its width ties the eye to
   the number it visualises. Short so it never delays reading. */
.bar i { animation: barfill .7s ease-out both; }
.bar i + i { animation-delay: .25s; }
@keyframes barfill { from { width: 0 !important; } }
.sev { transition: filter .15s ease; }
.sev:hover { filter: brightness(1.25); }
/* scroll-spy: the active TOC entry gets a rule + color, so position in a long doc is visible */
nav.toc a.active { color: var(--amber); }
nav.toc a.active::before { content: "▸ "; }
.top-link { position: fixed; right: 1.2rem; bottom: 1.2rem; z-index: 3;
  background: var(--bg2); border: 1px solid var(--border2); border-radius: 999px;
  color: var(--dim); text-decoration: none; font-family: var(--mono); font-size: .75rem;
  padding: .45rem .8rem; opacity: 0; pointer-events: none; transition: opacity .2s ease; }
.top-link.show { opacity: 1; pointer-events: auto; }
.top-link:hover { color: var(--amber); border-color: var(--amber); }
@media (prefers-reduced-motion: reduce) {
  html { scroll-behavior: auto; }
  .bar i, .sev, .top-link { animation: none; transition: none; }
}

/* ---- print: the client's PDF path. 60 pages of black ink is not a deliverable. ---- */
@media print {
  :root { --bg: #fff; --bg2: #fff; --bg3: #f2f2f2; --text: #111; --dim: #444;
          --muted: #666; --border: #ccc; --border2: #999; --amber: #a06000;
          --amber2: #a06000; --amber-dim: #f6ecdc; }
  body { padding: 0; font-size: 11pt; }
  .grid-bg, nav.toc, .top-link { display: none; }
  main { max-width: none; }
  h2 { break-after: avoid; }
  .finding, .card, table { break-inside: avoid; }
  pre { color: #222; border-color: #ccc; background: #fafafa; }
}
"""


def _esc(text: str) -> str:
    # Control characters (except tab/newline/CR) are stripped BEFORE escaping: a NUL or ESC byte
    # in evidence would otherwise pass through into the deliverable verbatim (found by the
    # stress suite). Everything else is escaped, so hostile markup renders inert.
    cleaned = "".join(
        ch for ch in str(text) if ch in "\t\n\r" or not (ord(ch) < 32 or ord(ch) == 127)
    )
    return _html_escape(cleaned, quote=True)


def _pct(v) -> str:
    return "n/a" if v is None else f"{v * 100:.1f}%"


def _interval(row: dict) -> str:
    if row["ci_low"] is None or row["ci_high"] is None:
        return "n/a"
    return f"[{_pct(row['ci_low'])}, {_pct(row['ci_high'])}]"


def _sev_badge(severity) -> str:
    return f'<span class="sev {severity.value}">{severity.value.upper()}</span>'


def _asr_bar(row: dict) -> str:
    """Visual ASR bar: attack success vs the interval's uncertainty band."""
    asr = row["asr"]
    lo, hi = row["ci_low"] or 0.0, row["ci_high"] or 0.0
    return (
        '<div class="bar" title="attack success rate with 95% interval">'
        f'<i style="width:{hi * 100:.1f}%; background:rgba(255,182,39,.25)"></i>'
        f'<i style="width:{max(asr - lo, 0) * 100:.1f}%; background:var(--amber)"></i>'
        "</div>"
    )


def _asr_chart(asr: dict, skip_overall: bool = True, link: str = "#") -> str:
    """Per-category ASR as interval-drawn rows: band = 95% CI, tick = point estimate.

    `asr` is compute_asr's output. Categories with zero attempts are skipped (nothing to draw —
    the coverage table is where absence of evidence is stated honestly).
    """
    out = []
    for cid, row in asr.items():
        if skip_overall and cid == "__overall__":
            continue
        if not row["attempts"]:
            continue
        lo = row["ci_low"] or 0.0
        hi = row["ci_high"] or 0.0
        asr_v = row["asr"] or 0.0
        out.append(
            f'<div class="asr-chart">'
            f'<div class="cid"><a href="{link}{cid}"><code>{cid}</code></a></div>'
            '<div class="track" role="img" '
            f'title="{cid}: ASR {_pct(row["asr"])}, 95% interval {_interval(row)}, '
            f'{row["successes"]}/{row["attempts"]} attempts">'
            f'<span class="band" style="left:{lo * 100:.1f}%;width:{(hi - lo) * 100:.1f}%"></span>'
            f'<span class="point" style="left:{asr_v * 100:.1f}%"></span></div>'
            f'<div class="n">{_pct(row["asr"])} · {_interval(row)} · '
            f'{row["successes"]}/{row["attempts"]}</div>'
            "</div>"
        )
    return "".join(out)


def masthead(title: str, meta_lines: list[str], command: str) -> str:
    """The console-opening header shared by every surface (D-022's voice, one implementation)."""
    return (
        '<header class="masthead">'
        f'<div class="prompt"><b>kessler</b> {command}</div>'
        f"<h1><span class='brand'>{_esc(title)}</span></h1>"
        + "".join(f'<div class="meta">{line}</div>' for line in meta_lines)
        + "</header>"
    )


def page(title: str, head_extra: str, body: str) -> str:
    """Full document frame used by report + viewer + workbench."""
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{_esc(title)}</title>"
        f"<style>{CSS}</style>{head_extra}</head>"
        '<body><div class="grid-bg"></div><main>'
        f"{body}"
        "</main></body></html>"
    )
