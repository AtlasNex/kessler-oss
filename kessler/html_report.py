"""The HTML render layer (BUILD B4) — D-024's static HTML report + the viewer's shared markup.

Why this exists
---------------
D-002 made markdown canonical; D-024 (v2.1) adds the HTML render as the client-facing surface:
the dominant shipped pattern in the category (garak, mcp-scan) is a **static, self-contained HTML
report** the tool itself generates — zero runtime dependency beyond the Python package, which is
what C-2 demands. `render_html_report(engagement)` produces exactly that: one file, no external
assets, no JavaScript requirement (a progressive-enhancement toggle only), brand styling inline.

Brand rules (D-022) encoded here:
* terminal-realism: amber-on-black, monospace, the report reads like an operator's console;
* evidence-trace: every finding carries its raw evidence block verbatim;
* measured voice: numbers with their intervals; no decorative claims.

This module is deliverable-side (HTML is an *output*); the engagement document remains the single
source of truth (markdown stays canonical for the file artefact).
"""
from __future__ import annotations

import html

from .asi import compute_asr, retest_delta
from .report import _SEVERITY_RANK, _STANDARDS, assert_emittable

#: Brand palette (D-022): BugHunter-lineage terminal realism, Kessler amber.
CSS = """
:root {
  --bg: #0b0d10; --bg2: #11151b; --border: #1c1c1c; --border2: #2a2a2a;
  --text: #e8e8e8; --dim: #8b949e; --muted: #555;
  --amber: #ffb627; --amber2: #ffc752;
  --crit: #ff4a5f; --high: #ff7a4a; --med: #ffb627; --low: #5fa8ff; --info: #5fd97a;
  --ok: #5fd97a; --mono: ui-monospace, 'JetBrains Mono', Menlo, Consolas, monospace;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body { background: var(--bg); color: var(--text); font-family: var(--mono);
       font-size: 14px; line-height: 1.65; padding: 2.5rem 1.5rem 5rem; }
main { max-width: 980px; margin: 0 auto; }
.grid-bg { position: fixed; inset: 0; pointer-events: none; z-index: 0;
  background-image: linear-gradient(rgba(255,255,255,.012) 1px, transparent 1px),
                    linear-gradient(90deg, rgba(255,255,255,.012) 1px, transparent 1px);
  background-size: 48px 48px; }
main { position: relative; z-index: 1; }
h1 { color: var(--amber); font-size: 1.5rem; letter-spacing: -0.02em; margin-bottom: .25rem; }
h2 { color: var(--amber); font-size: 1.05rem; margin: 2.2rem 0 .8rem; padding-bottom: .35rem;
     border-bottom: 1px solid var(--border2); }
h3 { color: var(--text); font-size: .95rem; margin: 1.4rem 0 .4rem; }
a { color: var(--amber2); }
.meta { color: var(--dim); font-size: .85rem; margin-bottom: 1.5rem; }
.prompt { color: var(--muted); } .prompt b { color: var(--amber); font-weight: 600; }
table { width: 100%; border-collapse: collapse; margin: .8rem 0 1.2rem; font-size: .85rem; }
th { color: var(--dim); text-align: left; font-weight: 600; border-bottom: 1px solid var(--border2);
     padding: .45rem .6rem; }
td { border-bottom: 1px solid var(--border); padding: .45rem .6rem; vertical-align: top; }
tr:hover td { background: var(--bg2); }
code, pre { font-family: var(--mono); font-size: .84rem; }
code { color: var(--amber2); }
pre { background: var(--bg2); border: 1px solid var(--border); border-radius: 6px;
      padding: .8rem 1rem; overflow-x: auto; margin: .5rem 0 1rem; color: var(--dim); }
.sev { display: inline-block; font-weight: 700; font-size: .72rem; letter-spacing: .08em;
       padding: .1rem .5rem; border-radius: 3px; border: 1px solid; }
.sev.critical { color: var(--crit); border-color: var(--crit); }
.sev.high { color: var(--high); border-color: var(--high); }
.sev.medium { color: var(--med); border-color: var(--med); }
.sev.low { color: var(--low); border-color: var(--low); }
.sev.info { color: var(--info); border-color: var(--info); }
.card { background: var(--bg2); border: 1px solid var(--border); border-radius: 8px;
        padding: 1rem 1.2rem; margin: 1rem 0; }
.finding { border-left: 3px solid var(--border2); padding-left: 1rem; margin: 1.8rem 0; }
.finding.critical { border-left-color: var(--crit); }
.finding.high { border-left-color: var(--high); }
.finding.medium { border-left-color: var(--med); }
.finding.low { border-left-color: var(--low); }
.finding.info { border-left-color: var(--info); }
.kv { color: var(--dim); font-size: .82rem; } .kv b { color: var(--text); font-weight: 600; }
.big { font-size: 2rem; color: var(--amber); font-weight: 700; letter-spacing: -0.03em; }
.ok { color: var(--ok); } .warn { color: var(--crit); }
.label { color: var(--muted); text-transform: uppercase; font-size: .68rem;
         letter-spacing: .14em; margin: 1rem 0 .3rem; }
details summary { cursor: pointer; color: var(--amber2); font-size: .82rem; margin: .4rem 0; }
footer { margin-top: 4rem; color: var(--muted); font-size: .75rem; border-top:
         1px solid var(--border); padding-top: 1rem; }
.bar { height: 6px; background: var(--bg2); border-radius: 3px; overflow: hidden;
       display: flex; margin: .3rem 0 .8rem; }
.bar i { display: block; height: 100%; }
/* MOTION (shared by report + viewer; each rule has a reason) */
/* ASR bars fill once on load. Reason: the bar is the measurement; animating its width ties
   the eye to the number it visualises. Duration is short so it never delays reading. */
.bar i { animation: barfill .7s ease-out both; }
.bar i + i { animation-delay: .25s; }
@keyframes barfill { from { width: 0 !important; } }
/* Severity badge hover: border brightens. Reason: affordance for the evidence <details>. */
.sev { transition: filter .15s ease; }
.sev:hover { filter: brightness(1.25); }
@media (prefers-reduced-motion: reduce) {
  .bar i { animation: none; }
  .sev { transition: none; }
}
"""


def _esc(text: str) -> str:
    # Control characters (except tab/newline/CR) are stripped BEFORE escaping: a NUL or ESC byte
    # in evidence would otherwise pass through into the deliverable verbatim (found by the
    # stress suite). Everything else is escaped, so hostile markup renders inert.
    cleaned = "".join(
        ch for ch in str(text) if ch in "\t\n\r" or not (ord(ch) < 32 or ord(ch) == 127)
    )
    return html.escape(cleaned, quote=True)


def _pct(v) -> str:
    return "n/a" if v is None else f"{v * 100:.1f}%"


def _interval(row: dict) -> str:
    if row["ci_low"] is None or row["ci_high"] is None:
        return "n/a"
    return f"[{_pct(row['ci_low'])}, {_pct(row['ci_high'])}]"


def _sev_badge(severity: Severity) -> str:
    return f'<span class="sev {severity.value}">{severity.value.upper()}</span>'


def _asr_bar(row: dict) -> str:
    """Visual ASR bar: attack success vs the interval's uncertainty band."""
    asr = row["asr"]
    lo, hi = row["ci_low"] or 0.0, row["ci_high"] or 0.0
    return (
        '<div class="bar" title="attack success rate with 95% interval">'
        f'<i style="width:{hi * 100:.1f}%; background:var(--border2)"></i>'
        f'<i style="width:{max(asr - lo, 0) * 100:.1f}%; background:var(--amber)"></i>'
        "</div>"
    )


def render_html_report(engagement) -> str:
    """The single-file client-facing report. Every figure computed, never hand-written."""
    assert_emittable(engagement)   # C-4: the HTML surface is an emission surface (review F-3)
    asr = compute_asr(engagement.attempts)
    overall = asr["__overall__"]
    ranked = sorted(engagement.findings, key=lambda f: _SEVERITY_RANK[f.severity])
    rows = engagement.coverage()
    missing = [r["category"] for r in rows if r["status"] == "missing"]

    o: list[str] = []
    o.append("<!doctype html>")
    o.append('<html lang="en"><head><meta charset="utf-8">')
    o.append('<meta name="viewport" content="width=device-width, initial-scale=1">')
    o.append(f"<title>Kessler · {_esc(engagement.ref)}</title>")
    o.append(f"<style>{CSS}</style></head>")
    o.append('<body><div class="grid-bg"></div><main>')

    # ---- header: console opening
    o.append('<div class="prompt"><b>kessler</b> report --engagement '
             f"{_esc(engagement.ref)} ... done</div>")
    o.append(f"<h1>{_esc(engagement.client)}</h1>")
    o.append(
        f'<div class="meta">engagement <code>{_esc(engagement.ref)}</code> · '
        f"{_esc(engagement.start)} → {_esc(engagement.end)} · scope "
        f"<code>{_esc(engagement.scope_sha256[:16])}…</code> · "
        f"testers {_esc(', '.join(engagement.testers) or '[UNNAMED]')} · generated by Kessler</div>"
    )

    # ---- headline measurement
    o.append('<section>')
    o.append('<div class="label">overall attack-success rate</div>')
    o.append(f'<div class="big">{_pct(overall["asr"])}</div>')
    o.append(f'<div class="kv">95% Wilson interval <b>{_interval(overall)}</b> · '
             f'{overall["successes"]} of {overall["attempts"]} attempts achieved their objective '
             f'· {len(engagement.findings)} finding(s)</div>')
    o.append(_asr_bar(overall))
    o.append('</section>')

    # ---- 1. cover
    o.append("<h2>01 · engagement</h2>")
    o.append('<table>')
    for k, v in (
        ("Client", engagement.client),
        ("Reference", engagement.ref),
        ("Window", f"{engagement.start} → {engagement.end}"),
        ("Scope document", f"signed · sha256 {engagement.scope_sha256}"),
        ("Systems", f"{len(engagement.targets)} in scope · "
                    + ", ".join(t["id"] for t in engagement.targets)),
        ("Testers", ", ".join(engagement.testers) or "[UNNAMED]"),
        ("Versions", "; ".join(f"{t['id']} {t['version']}" for t in engagement.targets
                               if t.get("version")) or "not recorded"),
    ):
        o.append(f"<tr><th>{_esc(k)}</th><td>{_esc(v)}</td></tr>")
    o.append("</table>")

    # ---- 2. exec summary (plain words, as the brief demands)
    o.append("<h2>02 · summary in plain words</h2>")
    if ranked:
        o.append("<p>We attacked "
                 f"{overall['attempts']} times. The attacks worked "
                 f"{overall['successes']} times ({_pct(overall['asr'])} overall). "
                 "The three worst problems:</p><ol>")
        for f in ranked[:3]:
            o.append(f"<li><b>{_esc(f.title)}</b> · {_esc(f.impact)} "
                     f"({_esc(f.finding_id)}, {_esc(f.severity.value.upper())})</li>")
        o.append("</ol>")
        o.append("<p>Fix the first one first. Each finding below says exactly how.</p>")
    else:
        o.append("<p>We attacked "
                 f"{overall['attempts']} times; none succeeded. That is a measurement, not a "
                 "guarantee — the interval above is the honest part of that statement. No findings "
                 "were raised in this engagement.</p>")

    # ---- 3. scope & method
    o.append("<h2>02b · scope and method</h2>")
    o.append("<ul>")
    for t in engagement.targets:
        reaches = ", ".join(f"<code>{_esc(r)}</code>" for r in (t.get("reaches") or []))
        o.append(f"<li><code>{_esc(t['id'])}</code> ({_esc(t['kind'])}) · reaches: {reaches or 'nothing recorded'}</li>")
    o.append("</ul>")
    o.append(f"<pre>{_esc(_STANDARDS)}</pre>")

    # ---- 4. ASR table
    o.append("<h2>03 · attack-success rates</h2>")
    o.append("<table><tr><th>category</th><th>attempts</th><th>ASR</th><th>95% interval</th>"
             "<th>worst finding</th><th></th></tr>")
    for cid, row in asr.items():
        if cid == "__overall__":
            continue
        sev = _worst(ranked, cid)
        o.append(
            f"<tr><td><code>{cid}</code></td><td>{row['attempts']}</td>"
            f"<td>{_pct(row['asr']) if row['attempts'] else 'n/a'}</td>"
            f"<td>{_interval(row)}</td><td>{_sev_badge(sev) if sev else '—'}</td>"
            f"<td style='width:30%'>{_asr_bar(row) if row['attempts'] else ''}</td></tr>"
        )
    o.append(f"<tr><td><b>overall</b></td><td><b>{overall['attempts']}</b></td>"
             f"<td><b>{_pct(overall['asr'])}</b></td><td><b>{_interval(overall)}</b></td>"
             f"<td>·</td><td>{_asr_bar(overall)}</td></tr>")
    o.append("</table>")

    # ---- 5. findings (the case files)
    o.append("<h2>04 · findings · case files</h2>")
    if not ranked:
        o.append("<p class='kv'>No findings were recorded. The measurement above is the result.</p>")
    for f in ranked:
        ia = f.impact_analysis
        o.append(f"<div class='finding {f.severity.value}'>")
        o.append(f"<h3><code>{_esc(f.finding_id)}</code> · {_esc(f.title)}</h3>")
        o.append(f"<div class='kv'><b>{_esc(f.category)}</b> · {_sev_badge(f.severity)} · "
                 f"C-I-A: <b>{_esc(ia.get('confidentiality', 'NONE'))}</b>/"
                 f"<b>{_esc(ia.get('integrity', 'NONE'))}</b>/"
                 f"<b>{_esc(ia.get('availability', 'NONE'))}</b>"
                 + (f" · CVSS v4 <code>{_esc(f.cvss_v4_vector)}</code>" if f.cvss_v4_vector else "")
                 + (f" · chains with {'</b>, <b>'.join(_esc(c) for c in f.chained_with)}"
                    if f.chained_with else "")
                 + "</div>")
        o.append(f"<div class='label'>what the flaw is</div><p>{_esc(f.description)}</p>")
        o.append(f"<div class='label'>what an attacker needs first</div><p>{_esc(f.preconditions)}</p>")
        o.append("<div class='label'>the attack path</div>")
        o.append(f"<pre>{_esc(f.threat_scenario)}</pre>")
        o.append(f"<div class='label'>how it reproduces</div><p>{_esc(f.reproduction)}</p>")
        o.append("<div class='label'>evidence (verbatim)</div>")
        o.append(f"<pre>{_esc(f.evidence)}</pre>")
        o.append(f"<div class='label'>observed vs expected</div><p>{_esc(f.expected)}</p>")
        o.append(f"<div class='label'>what it costs you</div><p>{_esc(f.impact)}</p>")
        o.append("<div class='label'>how to fix it</div>")
        o.append("<div class='card'>"
                 f"<div class='label'>architectural fix</div><p>{_esc(f.remediation_architectural_fix)}</p>"
                 f"<div class='label'>guardrail config</div><p>{_esc(f.remediation_guardrail_config)}</p>"
                 f"<div class='label'>code-level patch</div><pre>{_esc(f.remediation_code_patch)}</pre>"
                 "</div>")
        o.append("</div>")

    # ---- 6. blast radius
    o.append("<h2>05 · blast radius</h2>")
    union: list[str] = []
    for t in engagement.targets:
        union += list(t.get("reaches") or [])
    total = sorted(set(union))
    o.append("<p>If one agent is compromised, everything in the <em>union</em> of its reach is "
             "within an attacker's grasp — the union, not the smallest part:</p>")
    o.append(" ".join(f"<code>{_esc(r)}</code>" for r in total) or "<p>nothing recorded</p>")
    o.append("<p class='kv'>This is the page a CTO reads twice. A defence that holds per agent can "
             "still fail as an estate.</p>")

    # ---- 7. chains (from data)
    chained = [(f.finding_id, f.chained_with) for f in engagement.findings if f.chained_with]
    o.append("<h2>06 · chained attacks</h2>")
    if chained:
        for fid, with_ in chained:
            o.append(f"<p><code>{_esc(fid)}</code> composes with "
                     f"{', '.join(f'<code>{_esc(w)}</code>' for w in with_)}.</p>")
    else:
        o.append("<p class='kv'>No chained path was demonstrated in this engagement · a statement "
                 "about what was attempted, not a claim that no chain exists.</p>")

    # ---- 8. retest
    o.append("<h2>07 · retest</h2>")
    if engagement.retest is not None:
        delta = retest_delta(engagement.attempts, engagement.retest["attempts"])
        o.append("<table><tr><th>category</th><th>before</th><th>after</th><th>delta</th>"
                 "<th>fix demonstrated?</th></tr>")
        for cid, d in delta.items():
            if not d["before_attempts"] and not d["after_attempts"]:
                continue
            name = "<b>overall</b>" if cid == "__overall__" else f"<code>{cid}</code>"
            dt = "n/a" if d["delta"] is None else f"{d['delta'] * 100:+.1f} pp"
            after = (f"{d['after_attempts']} / {_pct(d['after_asr'])}" if d["after_attempts"]
                     else "— not retested")
            if d["fix_demonstrated"]:
                fix = '<span class="ok">yes</span>'
            elif d.get("rate_reduced"):
                fix = '<span class="warn">rate down, not demonstrated</span>'
            else:
                fix = '<span class="warn">not demonstrated</span>'
            o.append(f"<tr><td>{name}</td><td>{d['before_attempts']} / {_pct(d['before_asr'])}</td>"
                     f"<td>{after}</td><td>{dt}</td><td>{fix}</td></tr>")
        o.append("</table>")
    else:
        o.append("<p class='kv'>No retest was performed for this engagement.</p>")

    # ---- coverage footer (the denominator, always)
    o.append("<h2>08 · coverage (the denominator)</h2>")
    o.append("<table><tr><th>category</th><th>status</th><th>reason</th></tr>")
    for r in rows:
        reason = _esc(r["reason"]) if r["reason"] else ("—" if r["status"] == "tested"
                                                       else "<b>NO REASON RECORDED</b>")
        o.append(f"<tr><td><code>{r['category']}</code> {_esc(r['name'])}</td>"
                 f"<td>{r['status']}</td><td>{reason}</td></tr>")
    o.append("</table>")
    if missing:
        o.append(f"<p class='warn'>REFUSAL STATE: {len(missing)} category(ies) missing · "
                 "the markdown artefact pipeline would have refused to emit this report "
                 "(C-4). This HTML render exists only because the caller rendered a "
                 "complete document.</p>")

    o.append("<footer>Kessler · adversarial testing of agentic AI · findings are <b>mapped to</b> "
             "OWASP ASI01–ASI10 (no accredited certification body exists; nothing here is a "
             "certification) · every figure on this page is computed from the engagement document, "
             "never hand-written.</footer>")
    o.append("</main></body></html>")
    return "\n".join(o)


def _worst(ranked, category: str):
    from .asi import Severity as S
    order = (S.CRITICAL, S.HIGH, S.MEDIUM, S.LOW, S.INFO)
    cands = [f.severity for f in ranked if f.category == category]
    return min(cands, key=order.index) if cands else None
