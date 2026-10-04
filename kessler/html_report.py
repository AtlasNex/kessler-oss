"""The HTML render layer (BUILD B4) — D-024's static HTML report.

Why this exists
---------------
D-002 made markdown canonical; D-024 (v2.1) adds the HTML render as the client-facing surface:
the dominant shipped pattern in the category (garak, mcp-scan) is a **static, self-contained HTML
report** the tool itself generates — zero runtime dependency beyond the Python package, which is
what C-2 demands. `render_html_report(engagement)` produces exactly that: one file, no external
assets, no JavaScript requirement (progressive enhancement only), brand styling inline.

Brand rules (D-022) encoded here:
* terminal-realism in the chrome (prompt line, amber, grid, mono for IDs/evidence), but the client
  reads prose in a readable sans at 15px — session 18 fixed the squint;
* evidence-trace: every finding carries its raw evidence block verbatim;
* measured voice: numbers with their intervals — and the ASR chart DRAWS the 95% band, because a
  point without its band overstates precision.

This module is deliverable-side (HTML is an *output*); the engagement document remains the single
source of truth (markdown stays canonical for the file artefact).

Session 18 (GUI rehaul): the design system lives in `kessler/ui.py` (one shell for report, viewer,
workbench; print stylesheet for the client's PDF path). CSS/_esc/... are re-exported here so the
import paths the other surfaces use stayed stable — the old in-module CSS block is deleted, not
kept in parallel (ui.py is the single source of truth).
"""
from __future__ import annotations

from .asi import Severity, compute_asr, retest_delta
from .report import _SEVERITY_RANK, _STANDARDS, assert_emittable
from .ui import (  # noqa: F401  (re-export of the helpers render_html_report itself calls)
    _asr_bar,
    _asr_chart,
    _esc,
    _interval,
    _pct,
    _sev_badge,
    masthead,
    page,
)

#: Report sections: (anchor, TOC title, heading title). The headings below render THESE strings,
#: so TOC and body cannot drift apart silently (the B-5/V-18 lesson, applied to markup).
_SECTIONS = [
    ("cover", "Engagement", "01 · engagement"),
    ("summary", "Summary in plain words", "02 · summary in plain words"),
    ("scope", "Scope and method", "03 · scope and method"),
    ("asr", "Attack-success rates", "04 · attack-success rates"),
    ("findings", "Findings · case files", "05 · findings · case files"),
    ("blast", "Blast radius", "06 · blast radius"),
    ("chains", "Chained attacks", "07 · chained attacks"),
    ("retest", "Retest", "08 · retest"),
    ("coverage", "Coverage (the denominator)", "09 · coverage (the denominator)"),
]

#: Progressive enhancement only: scroll-spy for the TOC + a back-to-top button. The report is
#: fully readable and fully navigable (anchor links) with JavaScript disabled.
_REPORT_JS = """
<script>
(function(){
  var links=[].slice.call(document.querySelectorAll('nav.toc a'));
  var byId={};links.forEach(function(a){byId[a.hash.slice(1)]=a;});
  if('IntersectionObserver' in window){
    var io=new IntersectionObserver(function(es){es.forEach(function(e){
      var l=byId[e.target.id];if(!l)return;
      if(e.isIntersecting){links.forEach(function(x){x.classList.remove('active');});
        l.classList.add('active');}});},{rootMargin:'-10% 0px -80% 0px'});
    [].slice.call(document.querySelectorAll('main section[id]'))
      .forEach(function(s){io.observe(s);});
  }
  var top=document.querySelector('.top-link');
  if(top){addEventListener('scroll',function(){
    top.classList.toggle('show',scrollY>600);},{passive:true});
    top.addEventListener('click',function(ev){ev.preventDefault();
      scrollTo({top:0,behavior:'smooth'});});}
})();
</script>
"""


def _toc() -> str:
    items = "".join(f'<li><a href="#{a}">{t}</a></li>' for a, t, _ in _SECTIONS)
    return f'<nav class="toc"><div class="label">contents</div><ol>{items}</ol></nav>'


def _h2(section_id: str) -> str:
    """Heading for a section, looked up from _SECTIONS so TOC titles are the only source."""
    for aid, _toc_title, heading in _SECTIONS:
        if aid == section_id:
            no, _, rest = heading.partition(" · ")
            return f'<h2><span class="no">{no} ·</span> {rest}</h2>'
    raise KeyError(section_id)  # a section without a TOC entry is a bug, loudly


def render_html_report(engagement) -> str:
    """The single-file client-facing report. Every figure computed, never hand-written."""
    assert_emittable(engagement)   # C-4: the HTML surface is an emission surface (review F-3)
    asr = compute_asr(engagement.attempts)
    overall = asr["__overall__"]
    ranked = sorted(engagement.findings, key=lambda f: _SEVERITY_RANK[f.severity])
    rows = engagement.coverage()
    missing = [r["category"] for r in rows if r["status"] == "missing"]

    o: list[str] = []
    o.append(masthead(
        engagement.client or engagement.ref,
        [f"engagement <code>{_esc(engagement.ref)}</code> · "
         f"{_esc(engagement.start)} → {_esc(engagement.end)} · "
         f"testers {_esc(', '.join(engagement.testers) or '[UNNAMED]')} · "
         "generated by Kessler · adversarial testing of agentic AI"],
        f"report --engagement {_esc(engagement.ref)} ... done"))
    o.append(_toc())

    # ---- headline measurement (above the fold; id anchors the back-to-top link)
    o.append('<section class="card" id="headline">')
    o.append('<div class="label">overall attack-success rate</div>')
    o.append(f'<div class="big">{_pct(overall["asr"])}</div>')
    o.append(f'<div class="kv">95% Wilson interval <b>{_interval(overall)}</b> · '
             f'{overall["successes"]} of {overall["attempts"]} attempts achieved their objective '
             f'· {len(engagement.findings)} finding(s)</div>')
    o.append(_asr_bar(overall))
    o.append('</section>')

    # ---- 01 cover
    o.append('<section id="cover">')
    o.append(_h2("cover"))
    o.append('<table class="kv-table">')
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
    o.append("</table></section>")

    # ---- 02 exec summary (plain words, as the brief demands)
    o.append('<section id="summary">')
    o.append(_h2("summary"))
    if ranked:
        o.append("<p>We attacked "
                 f"{overall['attempts']} times. The attacks worked "
                 f"{overall['successes']} times ({_pct(overall['asr'])} overall). "
                 "The three worst problems:</p><ol>")
        for f in ranked[:3]:
            o.append(f"<li><b>{_esc(f.title)}</b> · {_esc(f.impact)} "
                     f"(<a href='#{_esc(f.finding_id)}'>{_esc(f.finding_id)}</a>, "
                     f"{_esc(f.severity.value.upper())})</li>")
        o.append("</ol>")
        o.append("<p>Fix the first one first. Each finding below says exactly how.</p>")
    else:
        o.append("<p>We attacked "
                 f"{overall['attempts']} times; none succeeded. That is a measurement, not a "
                 "guarantee — the interval above is the honest part of that statement. No findings "
                 "were raised in this engagement.</p>")
    o.append('</section>')

    # ---- 03 scope & method
    o.append('<section id="scope">')
    o.append(_h2("scope"))
    o.append("<ul>")
    for t in engagement.targets:
        reaches = ", ".join(f"<code>{_esc(r)}</code>" for r in (t.get("reaches") or []))
        o.append(f"<li><code>{_esc(t['id'])}</code> ({_esc(t['kind'])}) · "
                 f"reaches: {reaches or 'nothing recorded'}</li>")
    o.append("</ul>")
    import re as _re
    o.append("<pre>" + _re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", _esc(_STANDARDS))
             + "</pre>")
    o.append("</section>")

    # ---- 04 ASR: chart (the interval drawn) + the precise table underneath
    o.append('<section id="asr">')
    o.append(_h2("asr"))
    o.append('<div class="kv" style="margin-bottom:.4rem">bar = 95% Wilson interval · '
             'tick = point estimate · a rate without its band is a claim, not a measurement</div>')
    o.append(_asr_chart(asr))
    o.append("<table><tr><th>category</th><th class='num'>attempts</th>"
             "<th class='num'>ASR</th><th>95% interval</th>"
             "<th>worst finding</th><th>visual</th></tr>")
    for cid, row in asr.items():
        if cid == "__overall__" or not row["attempts"]:
            continue
        sev = _worst(ranked, cid)
        o.append(
            f"<tr id='{_esc(cid)}'><td><code>{cid}</code></td>"
            f"<td class='num'>{row['attempts']}</td>"
            f"<td class='num'>{_pct(row['asr'])}</td>"
            f"<td>{_interval(row)}</td>"
            f"<td class='sep-center'>{_sev_badge(sev) if sev else '—'}</td>"
            f"<td style='width:26%'>{_asr_bar(row)}</td></tr>")
    o.append(f"<tr><td><code><b>overall</b></code></td>"
             f"<td class='num'><b>{overall['attempts']}</b></td>"
             f"<td class='num'><b>{_pct(overall['asr'])}</b></td>"
             f"<td><b>{_interval(overall)}</b></td><td class='sep-center'>—</td>"
             f"<td>{_asr_bar(overall)}</td></tr>")
    o.append("<div class='kv' style='margin-top:.4rem'>A 0% row over its N is a "
             "measurement, not a guarantee: read the interval\u2019s upper bound at that "
             "N.</div>")
    o.append("</table></section>")

    # ---- 05 findings (the case files)
    o.append('<section id="findings">')
    o.append(_h2("findings"))
    if not ranked:
        o.append("<p class='kv'>No findings were recorded. The measurement above is the result.</p>")
    for f in ranked:
        ia = f.impact_analysis
        o.append(f"<div class='finding {f.severity.value}' id='{_esc(f.finding_id)}'>")
        o.append(f"<h3><code>{_esc(f.finding_id)}</code> · {_esc(f.title)}</h3>")
        o.append(f"<div class='kv'><b>{_esc(f.category)}</b> · {_sev_badge(f.severity)} · "
                 f"C-I-A: <b>{_esc(ia.get('confidentiality', 'NONE'))}</b>/"
                 f"<b>{_esc(ia.get('integrity', 'NONE'))}</b>/"
                 f"<b>{_esc(ia.get('availability', 'NONE'))}</b>"
                 + (f" · CVSS v4 <code>{_esc(f.cvss_v4_vector)}</code>" if f.cvss_v4_vector else "")
                 + (f" · chains with <b>{'</b>, <b>'.join(_esc(c) for c in f.chained_with)}</b>"
                    if f.chained_with else "")
                 + "</div>")
        o.append(f"<div class='label'>what the flaw is</div><p>{_esc(f.description)}</p>")
        o.append(f"<div class='label'>what an attacker needs first</div>"
                 f"<p>{_esc(f.preconditions)}</p>")
        o.append("<div class='label'>the attack path</div>")
        o.append(f"<pre>{_esc(f.threat_scenario)}</pre>")
        o.append(f"<div class='label'>how it reproduces</div><p>{_esc(f.reproduction)}</p>")
        o.append("<div class='label'>evidence (verbatim)</div>")
        o.append(f"<pre>{_esc(f.evidence)}</pre>")
        o.append(f"<div class='label'>observed vs expected</div><p>{_esc(f.expected)}</p>")
        o.append(f"<div class='label'>what it costs you</div><p>{_esc(f.impact)}</p>")
        o.append("<div class='label'>how to fix it</div>")
        o.append("<div class='card'>"
                 f"<div class='label'>architectural fix</div>"
                 f"<p>{_esc(f.remediation_architectural_fix)}</p>"
                 f"<div class='label'>guardrail config</div>"
                 f"<p>{_esc(f.remediation_guardrail_config)}</p>"
                 f"<div class='label'>code-level patch</div>"
                 f"<pre>{_esc(f.remediation_code_patch)}</pre>"
                 "</div>")
        o.append("</div>")
    o.append("</section>")

    # ---- 06 blast radius
    o.append('<section id="blast">')
    o.append(_h2("blast"))
    union: list[str] = []
    for t in engagement.targets:
        union += list(t.get("reaches") or [])
    total = sorted(set(union))
    o.append("<p>If one agent is compromised, everything in the <em>union</em> of its reach is "
             "within an attacker's grasp — the union, not the smallest part:</p>")
    o.append("<p>" + (" ".join(f"<code>{_esc(r)}</code>" for r in total) or "nothing recorded")
             + "</p>")
    o.append("<p class='kv'>This is the page a CTO reads twice. A defence that holds per agent can "
             "still fail as an estate.</p>")
    o.append("</section>")

    # ---- 07 chains (from data)
    chained = [(f.finding_id, f.chained_with) for f in engagement.findings if f.chained_with]
    o.append('<section id="chains">')
    o.append(_h2("chains"))
    if chained:
        for fid, with_ in chained:
            o.append(f"<p><code>{_esc(fid)}</code> composes with "
                     f"{', '.join(f'<code>{_esc(w)}</code>' for w in with_)}.</p>")
    else:
        o.append("<p class='kv'>No chained path was demonstrated in this engagement · a statement "
                 "about what was attempted, not a claim that no chain exists.</p>")
    o.append("</section>")

    # ---- 08 retest
    o.append('<section id="retest">')
    o.append(_h2("retest"))
    if engagement.retest is not None:
        delta = retest_delta(engagement.attempts, engagement.retest["attempts"])
        o.append("<table><tr><th>category</th><th class='num'>before</th>"
                 "<th class='num'>after</th><th class='num'>delta</th>"
                 "<th>fix demonstrated?</th></tr>")
        for cid, d in delta.items():
            if not d["before_attempts"] and not d["after_attempts"]:
                continue
            name = "<code><b>overall</b></code>" if cid == "__overall__" \
                else f"<code>{cid}</code>"
            dt = "n/a" if d["delta"] is None else f"{d['delta'] * 100:+.1f} pp"
            after = (f"{d['after_attempts']} / {_pct(d['after_asr'])}" if d["after_attempts"]
                     else "— not retested")
            if d["fix_demonstrated"]:
                fix = '<span class="ok">yes</span>'
            elif d.get("rate_reduced"):
                fix = '<span class="warn">rate down, not demonstrated</span>'
            else:
                fix = '<span class="warn">not demonstrated</span>'
            o.append(f"<tr><td>{name}</td><td class='num'>{d['before_attempts']} / "
                     f"{_pct(d['before_asr'])}</td>"
                     f"<td class='num'>{after}</td><td class='num'>{dt}</td><td>{fix}</td></tr>")
        o.append("</table>")
    else:
        o.append("<p class='kv'>No retest was performed for this engagement.</p>")
    o.append("</section>")

    # ---- 09 coverage (the denominator, always)
    o.append('<section id="coverage">')
    o.append(_h2("coverage"))
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
    o.append("</section>")

    o.append("<footer>Kessler · adversarial testing of agentic AI · findings are <b>mapped to</b> "
             "OWASP ASI01–ASI10 (no accredited certification body exists; nothing here is a "
             "certification) · every figure on this page is computed from the engagement document, "
             "never hand-written.</footer>")
    o.append('<a class="top-link" href="#headline">↑ top</a>')
    o.append(_REPORT_JS)

    return page(f"Kessler · {_esc(engagement.ref)}", "", "".join(o))


def _worst(ranked, category: str):
    order = (Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW, Severity.INFO)
    cands = [f.severity for f in ranked if f.category == category]
    return min(cands, key=order.index) if cands else None
