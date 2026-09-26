"""`kessler review` — the human-half reading workbench (session 17, D-030).

What it is
----------
`kessler view` (D-024) is a READ-ONLY viewer: a viewer that could edit evidence would undermine
the reason evidence exists. The G2 human half needs a different surface: the OWNER reading
replies and recording verdicts with a stopwatch. This module is that workbench — a separate
command with its own rules, so D-024 stays intact:

- **It never modifies the engagement document, the pending-review sidecar, or the triage
  artefact.** Its only write is a NEW file, `<doc>-human-review.json` — the human verdicts are
  new evidence, appended with who/when/what, atomically (tmp + os.replace).
- **Verdicts are constrained** to {hit, refused, unsure, skip}; free text is capped. A verdict
  without a named reviewer is refused at export (C-1 adjacent: unevidenced claims fail closed).
- **127.0.0.1 ONLY + per-session token.** Same DNS-rebinding Host check as the viewer, plus a
  random token the page carries and every POST must echo — a hostile web page cannot drive the
  workbench from the operator's browser.
- **C-2 stdlib only.** http.server + json; the page is vanilla HTML/JS with the house CSS.

Row order is the whole point: triage candidates FIRST (the judge's ranked reading order), then
the remaining pending-review rows, then the already-scored attempts read-only. The elapsed
timer rides on every verdict and the FINISH action writes the timing summary — that number is
the G2 human-half measurement.
"""
from __future__ import annotations

import json
import os
import secrets
import threading
import time
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .html_report import CSS, _esc

VERDICTS = ("hit", "refused", "unsure", "skip")
_NOTE_CAP = 2000
_JSON_CT = "application/json; charset=utf-8"


# ---------------------------------------------------------------- pure core (unit-tested)

def assemble_rows(doc: dict, sidecar: dict | None, triage: dict | None) -> dict:
    """Candidates first (triage order), then remaining pending rows, then scored attempts.

    Joins a triage ref (`KC-xxxx@target`) to its sidecar row on the case id before the '@'.
    A candidate whose sidecar row is missing is still emitted (payload/reply marked absent) —
    hiding a ranked candidate would be the triage lying by omission.
    """
    pending = list((sidecar or {}).get("rows", []))
    by_case = {r.get("case"): r for r in pending}
    used: set[str] = set()

    candidates = []
    for t in (triage or {}).get("rows", []):
        if t.get("verdict") != "candidate":
            continue
        case_id = t.get("ref", "").split("@", 1)[0]
        row = by_case.get(case_id)
        used.add(case_id)
        candidates.append({
            "ref": t.get("ref", case_id),
            "case": case_id,
            "category": (row or {}).get("category") or t.get("category", ""),
            "technique": (row or {}).get("technique") or t.get("technique", ""),
            "channel": (row or {}).get("channel", ""),
            "payload": (row or {}).get("payload", ""),
            "reply": (row or {}).get("reply", ""),
            "confidence": t.get("confidence"),
            "rationale": t.get("rationale", ""),
            "bucket": "candidate",
        })

    rest = []
    for r in pending:
        if r.get("case") in used:
            continue
        rest.append({
            "ref": f"{r.get('case', '?')}@{r.get('target', '?')}",
            "case": r.get("case", "?"),
            "category": r.get("category", ""),
            "technique": r.get("technique", ""),
            "channel": r.get("channel", ""),
            "payload": r.get("payload", ""),
            "reply": r.get("reply", ""),
            "confidence": None,
            "rationale": "",
            "bucket": "pending",
        })

    scored = [{
        "ref": f"{a.get('technique', '?')}@{a.get('environment', '?')}",
        "case": a.get("technique", "?"),
        "category": a.get("category", ""),
        "technique": a.get("technique", ""),
        "channel": "",
        "payload": a.get("payload", ""),
        "reply": a.get("observed", ""),
        "confidence": None,
        "rationale": "hit" if a.get("succeeded") else "defence held (automated oracle)",
        "bucket": "scored",
    } for a in doc.get("attempts", [])]

    return {"candidates": candidates, "pending": rest, "scored": scored}


_STORE_LOCK = threading.Lock()   # one store file, many verdict POSTs: serialize read-merge-write (F-7)


def record_decision(path: Path, engagement: str, reviewer: str,
                    decision: dict) -> dict:
    """Validate + merge one decision into the human-review file, atomically.

    Re-posting the same ref UPDATES that ref's decision (the human may change their mind);
    every row carries the reviewer and a fresh UTC timestamp. The engagement document itself
    is never touched by this module.
    """
    verdict = str(decision.get("verdict", "")).strip().lower()
    if verdict not in VERDICTS:
        raise ValueError(f"verdict must be one of {', '.join(VERDICTS)}; got {verdict!r}")
    ref = str(decision.get("ref", "")).strip()
    if not ref:
        raise ValueError("decision carries no ref")
    note = str(decision.get("note", "")).strip()[:_NOTE_CAP]
    try:
        elapsed = int(decision.get("elapsed_seconds", 0))
    except (TypeError, ValueError):
        elapsed = 0
    entry = {"ref": ref, "verdict": verdict, "note": note,
             "elapsed_seconds": max(0, elapsed),
             "reviewer": reviewer, "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}

    with _STORE_LOCK:
        store: dict = {"engagement": engagement, "reviewer": reviewer, "decisions": {}}
        if path.exists():
            prior = json.loads(path.read_text(encoding="utf-8"))
            if prior.get("engagement") != engagement:
                raise ValueError(f"review file belongs to engagement {prior.get('engagement')!r}, "
                                 f"not {engagement!r} - refusing to mix engagements")
            store["reviewer"] = prior.get("reviewer") or reviewer
            store["decisions"] = prior.get("decisions", {})
        store["decisions"][ref] = entry

        tmp = path.with_suffix(path.suffix + ".tmp")
        payload = json.dumps(store, indent=2, ensure_ascii=False) + "\n"
        for attempt in range(3):
            try:
                tmp.write_text(payload, encoding="utf-8")
                os.replace(tmp, path)
                break
            except PermissionError:   # Windows sharing violation (WinError 32) - retry
                if attempt == 2:
                    raise
                time.sleep(0.05)
    return entry


def finish_review(path: Path, engagement: str, reviewer: str, elapsed_seconds: int,
                  decisions_expected: int | None = None) -> dict:
    """Write the timing summary beside the decisions - the G2 human-half measurement.

    Refuses while undecided rows remain when the caller knows the expected count: a 'finished'
    stamp on a half-read review would be exactly the unevidenced claim this product refuses.
    """
    store = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    if store.get("engagement") != engagement:
        raise ValueError("no decisions recorded for this engagement yet")
    decided = len(store.get("decisions", {}))
    if decisions_expected is not None and decided < decisions_expected:
        raise ValueError(f"{decisions_expected - decided} row(s) undecided - finish refused "
                         "(a half-read review must not stamp itself complete)")
    summary = {
        "engagement": engagement,
        "reviewer": reviewer or store.get("reviewer", ""),
        "elapsed_seconds": max(0, int(elapsed_seconds)),
        "decided": decided,
        "expected": decisions_expected,
        "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "per_verdict": {},
    }
    for d in store.get("decisions", {}).values():
        summary["per_verdict"][d["verdict"]] = summary["per_verdict"].get(d["verdict"], 0) + 1
    out = path.with_name(path.stem.replace("-human-review", "") + "-human-review-summary.json")
    tmp = out.with_suffix(out.suffix + ".tmp")
    tmp.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, out)
    return summary


# ---------------------------------------------------------------- page + server

def _row_card(r: dict) -> str:
    conf = (f" · confidence {_esc(r['confidence'])}" if r.get("confidence") is not None else "")
    rationale = (f"<div class='label'>judge rationale</div><pre>{_esc(r['rationale'])}</pre>"
                 if r.get("rationale") else "")
    return f"""<details class='row' data-ref='{_esc(r['ref'])}' data-bucket='{r['bucket']}'>
<summary><b>{_esc(r['case'])}</b> · {_esc(r['category'])} · {_esc(r['technique'])}{conf}
<span class='vstat'></span></summary>
<div class='label'>the attack (payload)</div><pre>{_esc(r['payload'])}</pre>
<div class='label'>the agent's reply (verbatim)</div><pre>{_esc(r['reply'])}</pre>
{rationale}
<div class='verdicts'>
<button data-v='hit'>HIT — attack worked</button>
<button data-v='refused'>REFUSED</button>
<button data-v='unsure'>UNSURE</button>
<button data-v='skip'>SKIP</button>
<input class='note' placeholder='note (optional)' maxlength='{_NOTE_CAP}'>
</div></details>"""


def _workbench_html(engagement: str, rows: dict, token: str, reviewer: str,
                    decided: int, expected: int) -> str:
    cards = "".join(_row_card(r) for r in rows["candidates"] + rows["pending"])
    scored = "".join(_row_card(r) for r in rows["scored"])
    page = """<!doctype html><html lang='en'><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width, initial-scale=1'>
<title>Kessler review · @@ENGTITLE@@</title><style>@@CSS@@</style></head><body>
<style>
body { margin:0 auto; max-width:900px; padding:1rem 1.2rem 4rem; }
.timer { position:sticky; top:0; background:var(--bg); padding:.6rem 0; z-index:5;
  display:flex; gap:1rem; align-items:baseline; border-bottom:1px solid var(--border); }
.timer .clock { font-family:var(--mono); font-size:1.6rem; color:var(--amber); }
.row { border:1px solid var(--border); border-radius:8px; margin:.6rem 0; padding:.5rem .9rem;
  background:var(--bg2); }
.row summary { cursor:pointer; color:var(--fg); }
.row pre { white-space:pre-wrap; word-break:break-word; font-size:.78rem; }
.verdicts { display:flex; gap:.4rem; flex-wrap:wrap; margin:.6rem 0; align-items:center; }
.verdicts button { font-family:var(--mono); font-size:.72rem; background:var(--bg);
  color:var(--dim); border:1px solid var(--border2); border-radius:999px; padding:.3rem .7rem;
  cursor:pointer; }
.verdicts button:hover { color:var(--amber); border-color:var(--amber); }
.row.hit { border-color:var(--crit); }
.verdicts .note { flex:1; min-width:180px; background:var(--bg); color:var(--fg);
  border:1px solid var(--border2); border-radius:6px; padding:.3rem .5rem;
  font-family:var(--mono); font-size:.72rem; }
.vstat { font-family:var(--mono); font-size:.7rem; color:var(--amber); }
#progress { color:var(--dim); font-size:.8rem; }
@media (prefers-reduced-motion: reduce) { * { transition:none !important; } }
</style>
<div class='prompt'><b>kessler</b> review · human half · localhost only</div>
<div class='timer'><span class='clock' id='clock'>00:00:00</span>
<button id='toggle'>start / pause</button><button id='finish'>FINISH (write timing)</button>
<span id='progress'>@@DECIDED@@/@@EXPECTED@@ decided</span>
<span>reviewer: @@REVIEWER@@</span></div>
<h2>triage candidates &mdash; read these first</h2>@@CANDIDATES@@
<h2>already-scored attempts (read-only)</h2>@@SCORED@@
<script>
const TOKEN=@@TOKEN@@;
const ENG=@@ENGJSON@@;
let secs=0, running=false, tick=null;
if(localStorage.getItem('kr-elapsed-'+ENG)) secs=parseInt(localStorage.getItem('kr-elapsed-'+ENG));
const clock=document.getElementById('clock');
const draw=()=>{const h=String(Math.floor(secs/3600)).padStart(2,'0'),
m=String(Math.floor(secs/60)%60).padStart(2,'0'),s=String(secs%60).padStart(2,'0');
clock.textContent=h+':'+m+':'+s;};
draw();
document.getElementById('toggle').onclick=()=>{running=!running;
if(running)tick=setInterval(()=>{secs++;localStorage.setItem('kr-elapsed-'+ENG,secs);draw();},1000);
else clearInterval(tick);};
async function post(url,body){const r=await fetch(url,{method:'POST',
headers:{'Content-Type':'application/json','X-Review-Token':TOKEN},body:JSON.stringify(body)});
if(!r.ok){const t=await r.text();alert(t);}return r.ok;}
document.querySelectorAll('.row').forEach(row=>{
row.querySelectorAll('.verdicts button').forEach(b=>{
b.onclick=async()=>{const v=b.dataset.v;
const ok=await post('/api/verdict',{ref:row.dataset.ref,verdict:v,
note:row.querySelector('.note').value,elapsed_seconds:secs});
if(ok){row.querySelector('.vstat').textContent=v.toUpperCase();
row.classList.toggle('hit',v==='hit');
const p=await fetch('/api/progress');const j=await p.json();
document.getElementById('progress').textContent=j.decided+'/'+j.expected+' decided';}};});});
document.getElementById('finish').onclick=async()=>{
if(await post('/api/finish',{elapsed_seconds:secs}))alert('timing written - check the summary file');};
</script></body></html>"""
    return (page
            .replace("@@CSS@@", CSS)
            .replace("@@ENGTITLE@@", _esc(engagement))
            .replace("@@TOKEN@@", json.dumps(token).replace("<", "\\u003c"))
            .replace("@@ENGJSON@@", json.dumps(engagement).replace("<", "\\u003c"))
            .replace("@@DECIDED@@", str(decided))
            .replace("@@EXPECTED@@", str(expected))
            .replace("@@REVIEWER@@", _esc(reviewer or "(set --reviewer)"))
            .replace("@@CANDIDATES@@", cards)
            .replace("@@SCORED@@", scored))


class _ReviewHandler(BaseHTTPRequestHandler):
    token = ""
    engagement = ""
    reviewer = ""
    rows = {}
    store_path = None
    expected = 0

    def log_message(self, fmt, *args):
        pass

    def _send(self, code: int, content_type: str, payload: bytes) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def _guard(self) -> bool:
        host = (self.headers.get("Host") or "").strip().lower()
        port = self.server.server_address[1]
        if host not in {f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}"}:
            self._send(403, "text/plain; charset=utf-8", b"forbidden host\n")
            return False
        return True

    def do_GET(self):  # noqa: N802
        if not self._guard():
            return
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            page = _workbench_html(self.engagement, self.rows, self.token, self.reviewer,
                                   self._decided(), self.expected)
            self._send(200, "text/html; charset=utf-8", page.encode("utf-8"))
            return
        if path == "/api/progress":
            self._send(200, _JSON_CT, json.dumps(
                {"decided": self._decided(), "expected": self.expected}).encode("utf-8"))
            return
        self._send(404, "text/plain; charset=utf-8", b"not found\n")

    def _decided(self) -> int:
        if not self.store_path.exists():
            return 0
        try:
            return len(json.loads(self.store_path.read_text(encoding="utf-8"))
                       .get("decisions", {}))
        except (json.JSONDecodeError, OSError):
            return 0

    def do_POST(self):  # noqa: N802
        if not self._guard():
            return
        if (self.headers.get("X-Review-Token") or "") != self.token:
            self._send(403, "text/plain; charset=utf-8", b"forbidden token\n")
            return
        length = int(self.headers.get("Content-Length") or 0)
        if length > 64_000:
            self._send(413, "text/plain; charset=utf-8", b"payload too large\n")
            return
        try:
            body = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        except json.JSONDecodeError:
            self._send(400, "text/plain; charset=utf-8", b"malformed json\n")
            return
        path = urlparse(self.path).path
        try:
            if path == "/api/verdict":
                entry = record_decision(self.store_path, self.engagement, self.reviewer, body)
                self._send(200, _JSON_CT, json.dumps(entry).encode("utf-8"))
                return
            if path == "/api/finish":
                summary = finish_review(self.store_path, self.engagement, self.reviewer,
                                        body.get("elapsed_seconds", 0), self.expected)
                self._send(200, _JSON_CT, json.dumps(summary).encode("utf-8"))
                return
        except ValueError as exc:
            self._send(400, "text/plain; charset=utf-8", str(exc).encode("utf-8"))
            return
        self._send(404, "text/plain; charset=utf-8", b"not found\n")


def serve(document: Path, port: int = 8643, reviewer: str = "", open_browser: bool = True) -> None:
    """Serve the review workbench for one engagement document. Blocks; Ctrl-C to stop."""
    document = Path(document)
    doc = json.loads(document.read_text(encoding="utf-8"))
    engagement = doc.get("ref", document.stem)

    sidecar_p = document.with_name(document.stem + "-pending-review.json")
    triage_p = document.with_name(document.stem + "-triage.json")
    sidecar = json.loads(sidecar_p.read_text(encoding="utf-8")) if sidecar_p.exists() else None
    triage = json.loads(triage_p.read_text(encoding="utf-8")) if triage_p.exists() else None
    rows = assemble_rows(doc, sidecar, triage)
    expected = len(rows["candidates"]) + len(rows["pending"])

    store_path = document.with_name(document.stem + "-human-review.json")
    handler = type("BoundReviewHandler", (_ReviewHandler,), {
        "token": secrets.token_hex(16),
        "engagement": engagement,
        "reviewer": reviewer,
        "rows": rows,
        "store_path": store_path,
        "expected": expected,
    })
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    url = f"http://127.0.0.1:{port}/"
    print(f"REVIEW  {url}  (localhost only · verdicts write {store_path.name} beside the doc)")
    print(f"ROWS    {len(rows['candidates'])} candidate(s) · {len(rows['pending'])} pending · "
          f"{len(rows['scored'])} scored (read-only) · reviewer "
          f"{reviewer or '(NOT SET - pass --reviewer)'}")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        server.server_close()
