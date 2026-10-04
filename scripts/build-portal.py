#!/usr/bin/env python3
"""Build the client portal (A7/B1, s32/K6 wave-2): /portal/ + /portal/<ref>/.

Access-gated at the edge (CF Access app on kessler.atlasnex.com/portal; the origin is
loopback-only, so the edge gate is the only public path). Static pages generated from
docs/portal/engagements.json - the registry that grows one entry per delivered engagement.
Private by design: noindex, no og/twitter metas, no social card; the artifacts linked here
are the same files the client receives. This portal replaces the email attachment, not the
gate.
"""
import json
import re
import sys
from pathlib import Path
from xml.sax.saxutils import escape as xesc

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import importlib.util as _ilu
_spec = _ilu.spec_from_file_location("_br", ROOT / "scripts" / "build-reports.py")
_br = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_br)

from kessler.asi import wilson_interval


def pct(x) -> str:
    return " -" if x is None else f"{x * 100:.2f}%"


def trend_block(runs: list[dict]) -> str:
    rows = "".join(
        f'<tr><td class="kx-nowrap">{xesc(r["date"])}</td>'
        f'<td class="kx-nowrap">{r["attempts"]}</td>'
        f'<td class="kx-nowrap">{r["successes"]}</td>'
        f'<td class="kx-nowrap">{pct(r["successes"] / r["attempts"]) if r["attempts"] else " -"}</td>'
        f'<td class="kx-nowrap">{pct(wilson_interval(r["successes"], r["attempts"])[0]) if r["attempts"] else " -"}'
        f' to {pct(wilson_interval(r["successes"], r["attempts"])[1]) if r["attempts"] else " -"}</td></tr>'
        for r in runs)
    table = ('<table class="ax-table" style="margin-top:10px"><thead><tr><th>Run</th><th>N</th>'
             '<th>Hits</th><th>ASR</th><th>95% interval</th></tr></thead><tbody>'
             + rows + "</tbody></table>")
    if len(runs) < 2:
        return ("<p>Trend: one run so far. The trend line begins at the second run - it is not "
                "simulated in advance.</p>" + table)
    cur, prev = runs[-1], runs[-2]
    w_cur = wilson_interval(cur["successes"], cur["attempts"])
    w_prev = wilson_interval(prev["successes"], prev["attempts"])
    a_cur = cur["successes"] / cur["attempts"] if cur["attempts"] else None
    a_prev = prev["successes"] / prev["attempts"] if prev["attempts"] else None
    verdict = ""
    if None not in (a_cur, a_prev):
        overlap = not (w_cur[0] > w_prev[1] or w_prev[0] > w_cur[1])
        delta = (a_cur - a_prev) * 100
        verdict = (
            f'<p style="margin-top:10px"><b>Delta:</b> {delta:+.2f} percentage points '
            f'({pct(a_prev)} to {pct(a_cur)}) - and the 95% intervals '
            + ("overlap, so no difference is claimed. That is how intervals work."
               if overlap else
               "do NOT overlap: a change worth a closer read, not a causation claim.") + "</p>")
    return ("<p>Trend: compare consecutive runs at the same corpus version; a different corpus "
            "makes cells not comparable (stated, not hidden).</p>" + table + verdict)


def page_for(eng: dict) -> str:
    slug = eng["ref"].lower()
    facts = [
        ("Client", eng.get("client", "")), ("Kind", eng.get("kind", "")),
        ("Delivered", eng.get("delivered", "")), ("Scope", eng.get("scope", "")),
        ("Attestation", eng.get("attestation", "")), ("Next retest", eng.get("next_retest", "")),
    ]
    facts_html = "".join(
        f'<div class="kx-desk-meta"><span class="kx-chip">{xesc(k)}</span>'
        f"<span>{xesc(str(v))}</span></div>" for k, v in facts if v)
    arts = " ".join(
        f'<a class="kx-copy" style="text-decoration:none" href="{xesc(a["href"])}">'
        f'{xesc(a["label"])}</a>' for a in eng.get("artifacts", []))
    body = (
        f'<h1>{xesc(eng["client"])}</h1>\n'
        f'<p class="kx-note">{xesc(eng["ref"])} - the delivery surface for this engagement. '
        'Everything here is the same artifact set the client receives; nothing is edited for '
        'the portal.</p>\n'
        + facts_html
        + '<h2 id="artifacts">Artifacts</h2>\n'
        f'<div class="kx-toolbar">{arts}</div>\n'
        f'<h2 id="verify">Recompute the evidence</h2>\n'
        f'<p>The evidence capsule <code>{xesc(str(eng.get("capsule", "")))}</code> anchors every '
        'figure above. Recompute its SHA-256 chain and the verdict block in the browser at '
        '<a href="/verify/">/verify/</a> - same arithmetic the CLI runs.</p>\n'
        '<h2 id="trend">Run history and trend</h2>\n'
        + trend_block(eng.get("runs", []))
        + '<h2 id="honesty">What this portal is not</h2>\n'
        '<ul><li>not a certification: no accredited body certifies against OWASP ASI01-ASI10, '
        'and certificates belong to accredited auditors;</li>'
        '<li>not a score: every rate carries its n and its 95% Wilson interval, and empty cells '
        'stay stated;</li>'
        '<li>not public: this page is behind the AtlasNex access gate; the origin serves '
        'loopback only.</li></ul>\n'
    )
    html = _br.html_for(f'{eng["ref"]} - client portal', body, og="sample", kind="Portal",
                        extra_head='<meta name="robots" content="noindex">')
    # private pages carry no social meta at all
    html = re.sub(r'<meta (?:property="og:|name="twitter:)[^>]*>\s*', "", html)
    if 'property="og:' in html or 'name="twitter:' in html:
        raise SystemExit("og meta survived the strip")
    return html


def main() -> int:
    reg = json.loads((ROOT / "docs" / "portal" / "engagements.json").read_text(encoding="utf-8"))
    engs = reg.get("engagements", [])
    if not engs:
        raise SystemExit("portal registry is empty")
    out_root = ROOT / "site" / "portal"
    out_root.mkdir(parents=True, exist_ok=True)

    items = "".join(
        f'<li class="kx-log-item"><span class="kx-log-date">{xesc(e["delivered"])}</span>'
        f'<span class="kx-chip">{xesc(e["kind"])}</span>'
        f'<a href="{e["ref"].lower()}/">{xesc(e["client"])}</a>'
        f'<p class="kx-log-blurb">{xesc(e["ref"])} - {xesc(e["scope"])}</p></li>'
        for e in engs)
    index_body = (
        '<h1>Client portal</h1>\n'
        '<p class="kx-note">One page per engagement: artifacts, capsule verification, run '
        'history. Access-gated at the edge; the origin serves loopback only.</p>\n'
        f'<ul class="kx-log">{items}</ul>\n')
    index_html = _br.html_for("Client portal | Kessler by AtlasNex", index_body, og="sample",
                              kind="Portal",
                              extra_head='<meta name="robots" content="noindex">')
    index_html = re.sub(r'<meta (?:property="og:|name="twitter:)[^>]*>\s*', "", index_html)
    (out_root / "index.html").write_text(index_html, encoding="utf-8")

    for e in engs:
        p = out_root / e["ref"].lower()
        p.mkdir(exist_ok=True)
        html = page_for(e)
        if "\u2014" in html:
            raise SystemExit(f"em dash in portal page {e['ref']}")
        (p / "index.html").write_text(html, encoding="utf-8")
        print(f"built portal/{e['ref'].lower()}/index.html ({len(html)} bytes)")
    print(f"portal: {len(engs)} engagement(s); noindex; og stripped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
