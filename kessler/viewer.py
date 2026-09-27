"""`kessler view` — the localhost interactive viewer (BUILD B4, D-024).

What it is
----------
The second shipped UI pattern in the category (promptfoo `view`, MCP Inspector): a local web
viewer over the engagement document. D-024 constrains it: **stdlib `http.server` only, bound to
127.0.0.1 always** — the viewer never listens on an external interface, because it renders
engagement documents that may carry unredacted evidence.

What interactive buys over the static HTML report: filtering findings by category/severity,
live ASR recomputation over a selected subset, and the attempt stream (the brand's "engine at
work" surface, D-022) — the nearest thing to watching the range console without a live run.

It reads ONLY the engagement document passed on the command line. It has no write path: a viewer
that could edit evidence would undermine the reason evidence exists.
"""
from __future__ import annotations

import json
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .asi import compute_asr, coverage
from .html_report import _esc, _interval, _pct, _sev_badge
from .report import _SEVERITY_RANK
from .schema import parse
from .ui import _asr_chart, masthead, page

_JSON_CT = "application/json; charset=utf-8"

#: Viewer chrome: the same shell as the report (session 18); page-specific layout only.
_VIEWER_CSS = """
<style>
nav.chips { position: sticky; top: 0; background: var(--bg); padding: .6rem 0;
  z-index: 4; border-bottom: 1px solid var(--border); }
/* reveal = slide only; opacity must never gate whether the evidence can be read
   (the old 0->1 fade rendered findings invisible mid-transition — two vision rounds
   flagged "near-black text" before the cause was found). */
.finding.will-reveal { transform:translateY(10px); }
.finding.in { transform:none; transition:transform .45s ease; }
.hidden { display:none !important; }
@media (prefers-reduced-motion: reduce){ .finding.will-reveal{transform:none;}
.finding.in{transition:none;} }
</style>"""


def _viewer_html(eng) -> str:
    asr = compute_asr(eng.attempts)
    overall = asr["__overall__"]
    rows = coverage(eng.attempts, eng.exclusions)

    # ---- headline
    body = [
        masthead(eng.ref,
                 [f"{_esc(eng.client)} · {_esc(eng.start)} → {_esc(eng.end)} · "
                  f"{len(eng.attempts)} attempts · {len(eng.findings)} findings · "
                  f"testers {_esc(', '.join(eng.testers))}"],
                 "view · localhost only"),
        '<section class="card" id="headline">',
        "<div class='label'>overall ASR</div>",
        f"<div class='big'>{_pct(overall['asr'])}</div>",
        f"<div class='kv'>95% interval <b>{_interval(overall)}</b></div>",
        "</section>",
        "<nav class='chips'>",
    ]
    body.append("<a href='#asr'>rates</a><a href='#findings'>findings</a>"
                "<a href='#stream'>attempt stream</a><a href='#coverage'>coverage</a>")
    body.append("</nav>")

    # ---- ASR: the chart is the table here (same rows, one grid; the report keeps the
    # precise table because it adds the worst-finding column). /api/asr serves the raw numbers.
    body.append("<h2 id='asr'>attack-success rates</h2>")
    body.append('<div class="kv" style="margin-bottom:.4rem">bar = 95% Wilson interval · '
                'tick = point estimate · full numbers in the delivered report</div>')
    body.append(_asr_chart(asr, link="?cat="))

    # ---- findings, filterable
    body.append("<h2 id='findings'>findings</h2>")
    if eng.findings:
        cats = sorted({f.category for f in eng.findings})
        body.append("<nav class='chips filters'>")
        body.append("<button class='on' data-f='all'>all</button>")
        for c in cats:
            body.append(f"<button data-f='{_esc(c)}'>{_esc(c)}</button>")
        body.append("</nav>")
        ranked = sorted(eng.findings, key=lambda f: _SEVERITY_RANK[f.severity])
        for f in ranked:
            body.append(
                f"<div class='finding {f.severity.value}' data-cat='{_esc(f.category)}'>"
                f"<h3><code>{_esc(f.finding_id)}</code> {_esc(f.title)}</h3>"
                f"<div class='kv'><b>{_esc(f.category)}</b> {_sev_badge(f.severity)} · "
                f"C-I-A {_esc(f.impact_analysis.get('confidentiality', 'NONE'))}/"
                f"{_esc(f.impact_analysis.get('integrity', 'NONE'))}/"
                f"{_esc(f.impact_analysis.get('availability', 'NONE'))}</div>"
                f"<div class='label'>the attack path</div><pre>{_esc(f.threat_scenario)}</pre>"
                f"<div class='label'>evidence (verbatim)</div><pre>{_esc(f.evidence)}</pre>"
                f"<div class='label'>what it costs you</div><p>{_esc(f.impact)}</p>"
                f"<div class='label'>architectural fix</div>"
                f"<p>{_esc(f.remediation_architectural_fix)}</p>"
                f"</div>"
            )
        # progressive enhancement: category filter, no framework
        body.append(
            "<script>document.querySelectorAll('.filters button').forEach(function(b){"
            "b.addEventListener('click',function(){"
            "document.querySelectorAll('.filters button').forEach(function(x){x.classList.remove('on')});"
            "b.classList.add('on');var f=b.dataset.f;"
            "document.querySelectorAll('.finding').forEach(function(d){"
            "d.style.display=(f==='all'||d.dataset.cat===f)?'':'none';});});});"
            "(function(){var r=window.matchMedia('(prefers-reduced-motion: reduce)').matches;"
            "var ds=document.querySelectorAll('.finding');"
            "if(r||!('IntersectionObserver' in window)){"
            "ds.forEach(function(d){d.classList.add('in');});return;}"
            "var io=new IntersectionObserver(function(es){es.forEach(function(e){"
            "if(e.isIntersecting){e.target.classList.add('in');io.unobserve(e.target);}});},"
            "{threshold:.1});"
            "ds.forEach(function(d,i){d.classList.add('will-reveal');"
            "d.style.transitionDelay=(i%6*60)+'ms';io.observe(d);});})();</script>"
        )
    else:
        body.append("<p class='kv'>No findings recorded.</p>")

    # ---- the attempt stream (the engine at work)
    body.append("<h2 id='stream'>attempt stream</h2><div class='stream'>")
    for a in eng.attempts:
        mark = ("<span class='hit'>HIT</span>" if a.succeeded
                else "<span class='held'>held</span>")
        body.append(f"<div>{_esc(a.at)} · {a.category} · {_esc(a.technique)} · "
                    f"{mark} · {_esc(a.environment)}</div>")
    body.append("</div>")

    # ---- coverage
    body.append("<h2 id='coverage'>coverage</h2><table>")
    body.append("<tr><th>category</th><th>status</th><th>reason</th></tr>")
    for r in rows:
        reason = _esc(r["reason"]) or ("—" if r["status"] == "tested" else "")
        body.append(f"<tr><td><code>{r['category']}</code></td><td>{r['status']}</td>"
                    f"<td>{reason}</td></tr>")
    body.append("</table>")
    body.append('<a class="top-link" href="#headline">↑ top</a>')
    return page(f"Kessler · {eng.ref}", _VIEWER_CSS, "".join(body))


class _Handler(BaseHTTPRequestHandler):
    engagement = None  # injected by serve()

    def log_message(self, fmt, *args):  # silence the default request spam
        pass

    def _send(self, code: int, content_type: str, payload: bytes) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        # belt-and-braces: never let a proxy cache or an accident expose this
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def _host_allowed(self) -> bool:
        """Binding to 127.0.0.1 is not enough on its own (session-14 review).

        A web page the operator visits can point its own hostname at 127.0.0.1 (DNS rebinding) and
        then read /api/attempts with the browser's same-origin blessing. Such a request carries
        the attacker's hostname in its Host header. Answering only loopback Host values closes it.
        """
        host = (self.headers.get("Host") or "").strip().lower()
        port = self.server.server_address[1]
        return host in {f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}"}

    def do_GET(self):  # noqa: N802 (http.server API)
        if not self._host_allowed():
            self._send(403, "text/plain; charset=utf-8", b"forbidden host\n")
            return
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/index.html"):
            page = _viewer_html(self.engagement)
            self._send(200, "text/html; charset=utf-8", page.encode("utf-8"))
            return
        if parsed.path == "/api/asr":
            payload = json.dumps(compute_asr(self.engagement.attempts), indent=2)
            self._send(200, _JSON_CT, payload.encode("utf-8"))
            return
        if parsed.path == "/api/attempts":
            q = parse_qs(parsed.query)
            cat = (q.get("cat") or [None])[0]
            rows = [dict(category=a.category, technique=a.technique, succeeded=a.succeeded,
                         observed=a.observed, payload=a.payload, environment=a.environment,
                         at=a.at, adapter_ref=a.adapter_ref)
                    for a in self.engagement.attempts
                    if cat is None or a.category == cat]
            self._send(200, _JSON_CT, json.dumps(rows, indent=2).encode("utf-8"))
            return
        self._send(404, "text/plain; charset=utf-8", b"not found\n")


def serve(document: Path, port: int = 8642, open_browser: bool = True) -> None:
    """Serve the viewer for one engagement document. Blocks; Ctrl-C to stop. 127.0.0.1 ONLY."""
    eng = parse(json.loads(Path(document).read_text(encoding="utf-8")))
    handler = type("BoundHandler", (_Handler,), {"engagement": eng})
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    url = f"http://127.0.0.1:{port}/"
    print(f"VIEWER  {url}  (localhost only · engagement evidence never leaves this machine)")
    print(f"DOC     {Path(document).resolve()}  · {len(eng.attempts)} attempts · "
          f"{len(eng.findings)} findings · Ctrl-C to stop")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        server.server_close()
