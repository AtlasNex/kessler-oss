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

from .html_report import _esc
from .ui import masthead, nex_state, page

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
    # ALWAYS a span: the summary grid is 4 columns and a missing child shifts the verdict
    # column left (vision audit: conf values rendered in the wrong column on pending rows).
    conf = (f"<span class='rconf'>conf {_esc(r['confidence'])}</span>"
            if r.get("confidence") is not None else "<span class='rconf'></span>")
    rationale = (f"<div class='label'>judge rationale</div><pre>{_esc(r['rationale'])}</pre>"
                 if r.get("rationale") else "")
    cand = " cand" if r["bucket"] == "candidate" else ""
    flag = "<span class='flag'>flagged</span>" if r["bucket"] == "candidate" else ""
    # scored rows render NO verdict controls: they are read-only evidence. The old page gave
    # them buttons, so clicking a scored row added a store entry and could push `decided` past
    # `expected` while real pending rows stayed undecided — finish would then stamp complete.
    verdicts = ("" if r["bucket"] == "scored" else f"""
<div class='verdicts'>
<button data-v='hit' title='attack worked — key 1'>1 · HIT</button>\
<button data-v='refused' title='defence held — key 2'>2 · REFUSED</button>\
<button data-v='unsure' title='needs a second look — key 3'>3 · UNSURE</button>\
<button data-v='skip' title='not judgeable — key 4'>4 · SKIP</button>
<input class='note' placeholder='note (optional)' maxlength='{_NOTE_CAP}'>
</div>""")
    return f"""<details class='row{cand}' data-ref='{_esc(r['ref'])}' data-bucket='{r['bucket']}'\
 data-search='{_esc((r['case'] + ' ' + r['category'] + ' ' + r['technique'] + ' ' + r['payload'] + ' ' + r['reply']).lower())}'>
<summary><span class='rcase'>{_esc(r['case'])}</span><span class='rmeta'>{flag}{_esc(r['category'])} · {_esc(r['technique'])}</span>\
{conf}<span class='vstat'></span></summary>
<div class='rbody'>
<div class='label'>the attack (payload)</div><pre>{_esc(r['payload']) or '(row not found in sidecar — the candidate still reads here, never hidden)'}</pre>
<div class='label'>the agent's reply (verbatim)</div><pre>{_esc(r['reply']) or '(row not found in sidecar)'}</pre>
{rationale}{verdicts}
</div></details>"""


_WORKBENCH_CSS = """
<style>
/* workbench chrome (session 18): the shell is ui.py's; this is triage-specific layout */
.bar { position: sticky; top: 0; z-index: 6; background: var(--bg);
  border-bottom: 1px solid var(--border2); padding: .7rem .9rem .6rem;
  margin: 0 -0.9rem;              /* gutter so hint/timer never hug the edges */
  display: grid; grid-template-columns: auto 1fr; gap: .45rem .9rem; align-items: center; }
.bar .tools { min-height: 2.4rem; }
.bar > * { min-width: 0; }
.bar .clock { font-family: var(--mono); font-size: 1.5rem; color: var(--amber);
  font-variant-numeric: tabular-nums; line-height: 1.25; }
.bar button.ghost, #search { height: 2.1rem; box-sizing: border-box; }
.kbd-hint { margin-left: .35rem; }
.bar .tools { display: flex; gap: .45rem .6rem; flex-wrap: wrap; align-items: center;
  justify-content: flex-end; row-gap: .4rem; }
.progress { grid-column: 1 / -1; display: flex; align-items: center; gap: .7rem;
  font-size: .8rem; color: var(--dim); font-family: var(--mono); }
.pbar { flex: 1; height: 6px; background: var(--bg3); border-radius: 3px; overflow: hidden; }
.pbar i { display: block; height: 100%; background: var(--amber); width: 0;
  transition: width .3s ease; }
#search { background: var(--bg2); color: var(--text); border: 1px solid var(--border2);
  border-radius: 6px; padding: .32rem .6rem .32rem .75rem; font-family: var(--mono);
  font-size: .75rem; flex: 1 1 14rem; max-width: 22rem; min-width: 14rem; }
.counts span { font-family: var(--mono); font-size: .72rem; margin-left: .45rem; }
.counts .c-hit { color: var(--crit); } .counts .c-refused { color: var(--ok); }
.counts .c-unsure { color: var(--med); } .counts .c-skip { color: var(--dim); }
.row { border: 1px solid var(--border2); border-left: 3px solid var(--border2);
  border-radius: 0 var(--radius) var(--radius) 0; margin: .55rem 0; background: var(--bg2);
  scroll-margin-top: 8.5rem; }
.row.cand { border-left-color: var(--amber); }
/* fixed first column: every row is its own grid, so an auto/minmax first column
   made the case-ID edge drift row to row (vision round 7, item 3) */
.row summary { cursor: pointer; padding: .55rem .9rem; display: grid;
  grid-template-columns: 9.5rem 1fr 5.5rem 4.6rem; gap: .8rem;
  align-items: baseline; list-style: none; }
.row summary::-webkit-details-marker { display: none; }
.row .rcase { font-family: var(--mono); font-weight: 700; color: var(--text); }
.row .rmeta { color: var(--dim); font-size: .8rem; min-width: 0;
  overflow-wrap: anywhere; }
.row[open] .rbody { border-top: 1px solid var(--border); padding: .2rem .9rem .8rem; }
.row pre { white-space: pre-wrap; word-break: break-word; font-size: .78rem; }
.verdicts { display: flex; gap: .4rem; flex-wrap: wrap; margin: .7rem 0 .2rem;
  align-items: center; }
.verdicts button { font-family: var(--mono); font-size: .72rem; background: var(--bg);
  color: var(--dim); border: 1px solid var(--border2); border-radius: 999px;
  padding: .32rem .75rem; cursor: pointer; }
.verdicts button:hover { color: var(--amber); border-color: var(--amber); }
.row[data-verdict='hit'] { border-left-color: var(--crit); }
.row[data-verdict='refused'] { border-left-color: var(--ok); }
.row[data-verdict='unsure'] { border-left-color: var(--med); }
.row[data-verdict='skip'] { border-left-color: var(--dim); }
.vstat { font-family: var(--mono); font-size: .7rem; color: var(--amber);
  text-transform: uppercase; text-align: right; }
.rconf { font-family: var(--mono); font-size: .74rem; color: var(--dim); white-space: nowrap;
  text-align: right; }
.row .flag { display: inline-block; font-family: var(--mono); font-size: .62rem; font-weight: 700;
  letter-spacing: .1em; color: var(--amber); border: 1px solid var(--amber);
  border-radius: 999px; padding: 0 .45em; margin-right: .5em; vertical-align: baseline; }
.row.focus { outline: 1px solid var(--amber); }
.hidden { display: none !important; }
button.ghost { font-family: var(--mono); font-size: .72rem; background: var(--bg2);
  color: var(--dim); border: 1px solid var(--border2); border-radius: 6px;
  padding: .32rem .7rem; cursor: pointer; }
button.ghost:hover { color: var(--amber); border-color: var(--amber); }
#finish { border-color: var(--amber); color: var(--amber); }
.kbd-hint { color: var(--muted); font-size: .72rem; font-family: var(--mono); }
@media (prefers-reduced-motion: reduce) { * { transition: none !important; } }
</style>"""

_WORKBENCH_JS = """
<script>
const TOKEN=@@TOKEN@@;
const ENG=@@ENGJSON@@;
/* ---- timer: wall clock across sessions (localStorage), start/pause, never auto-wins ---- */
let secs=0, running=false, tick=null;
if(localStorage.getItem('kr-elapsed-'+ENG)) secs=parseInt(localStorage.getItem('kr-elapsed-'+ENG))||0;
const clock=document.getElementById('clock');
function draw(){const h=String(Math.floor(secs/3600)).padStart(2,'0'),
m=String(Math.floor(secs/60)%60).padStart(2,'0'),s=String(secs%60).padStart(2,'0');
clock.textContent=h+':'+m+':'+s;}
draw();
document.getElementById('toggle').onclick=()=>{running=!running;
document.getElementById('toggle').textContent=running?'pause':'start';
if(running)tick=setInterval(()=>{secs++;localStorage.setItem('kr-elapsed-'+ENG,secs);draw();},1000);
else clearInterval(tick);};
/* ---- verdicts ---- */
async function post(url,body){const r=await fetch(url,{method:'POST',
headers:{'Content-Type':'application/json','X-Review-Token':TOKEN},body:JSON.stringify(body)});
if(!r.ok)alert(await r.text());return r.ok;}
const rows={};document.querySelectorAll('.row[data-bucket]').forEach(
  r=>{if(r.dataset.bucket!=='scored')rows[r.dataset.ref]=r;});
function mark(row,v){row.querySelector('.vstat').textContent=v.toUpperCase();
row.dataset.verdict=v;counts();}
function counts(){const c={hit:0,refused:0,unsure:0,skip:0};
Object.values(rows).forEach(r=>{const v=r.dataset.verdict;if(v&&c[v]!==undefined)c[v]++;});
for(const k in c){const el=document.getElementById('c-'+k);if(el)el.textContent=k+' '+c[k];}}
async function refreshProgress(){const p=await fetch('/api/progress');const j=await p.json();
document.getElementById('progress').textContent=j.decided+'/'+j.expected+' decided';
document.getElementById('pfill').style.width=(j.expected?100*j.decided/j.expected:0)+'%';}
document.querySelectorAll('.row').forEach(row=>{
row.querySelectorAll('.verdicts button').forEach(b=>{
b.onclick=async()=>{const v=b.dataset.v;
const ok=await post('/api/verdict',{ref:row.dataset.ref,verdict:v,
note:row.querySelector('.note')?row.querySelector('.note').value:'',elapsed_seconds:secs});
if(ok){mark(row,v);refreshProgress();}};});});
/* restore recorded verdicts on load/reload (a refresh must not lose the visual state) */
fetch('/api/decisions',{headers:{'X-Review-Token':TOKEN}}).then(r=>r.json()).then(d=>{
for(const ref in d){const row=rows[ref];if(row){mark(row,d[ref].verdict);
const n=row.querySelector('.note');if(n&&!n.value)n.value=d[ref].note||'';}}
refreshProgress();counts();}).catch(()=>{});
/* ---- finish ---- */
document.getElementById('finish').onclick=async()=>{
if(await post('/api/finish',{elapsed_seconds:secs}))
alert('timing written - check the summary file');};
/* ---- search filter (candidate + pending rows) ---- */
document.getElementById('search').addEventListener('input',e=>{
const q=e.target.value.trim().toLowerCase();
document.querySelectorAll('.row[data-bucket]').forEach(r=>{
r.classList.toggle('hidden',!!q&&!r.dataset.search.includes(q));});});
/* ---- keyboard: j/k move focus, o toggles, 1-4 verdict the focused row ---- */
let focusIdx=-1;const visible=()=>[...document.querySelectorAll(
  '.row[data-bucket]:not(.hidden)')];
function setFocus(i){const v=visible();if(!v.length)return;
focusIdx=Math.max(0,Math.min(i,v.length-1));
document.querySelectorAll('.row.focus').forEach(r=>r.classList.remove('focus'));
const r=v[focusIdx];r.classList.add('focus');r.scrollIntoView({block:'nearest'});}
addEventListener('keydown',e=>{
if(/INPUT|TEXTAREA/.test(document.activeElement.tagName))return;
const v=visible();
if(e.key==='j'){setFocus(focusIdx+1);e.preventDefault();}
else if(e.key==='k'){setFocus(focusIdx<0?0:focusIdx-1);e.preventDefault();}
else if(e.key==='o'&&v[focusIdx]){v[focusIdx].open=!v[focusIdx].open;}
else if('1234'.includes(e.key)&&v[focusIdx]){
const map={'1':'hit','2':'refused','3':'unsure','4':'skip'};
const b=v[focusIdx].querySelector(".verdicts button[data-v='"+map[e.key]+"']");
if(b){b.click();e.preventDefault();}}});
counts();refreshProgress();
</script>"""


def _workbench_html(engagement: str, rows: dict, token: str, reviewer: str,
                    decided: int, expected: int, document_name: str = "") -> str:
    scored = "".join(_row_card(r) for r in rows["scored"])
    decidable = len(rows["candidates"]) + len(rows["pending"])
    # The Nex state layer (PLAN-UI-NEX): the character renders ONLY where no decidable row
    # is being read - a first-run bench, or a bench whose rows are all decided. The rows
    # themselves (and the scored attempts) stay a character-free zone: the reviewer there
    # is verifying Kessler, not meeting a mascot.
    if decidable == 0 and not rows["scored"]:
        zone = nex_state(
            "peek",
            line="nothing on the bench yet; the first run brings the first rows.",
            command=(f'kessler run <scope.json> --out {document_name or "engagement.json"} '
                     f'--reviewer "{reviewer or "Your Name"}"'),
            note=True)
    elif decidable == 0:
        zone = (nex_state(
                    "verified",
                    line="nothing left to decide in this document; the scored attempts "
                         "below are read-only evidence.")
                if decided else
                "<p class='kv'>no decidable row in this document; the attempts below are "
                "read-only evidence.</p>")
    else:
        cand = "".join(_row_card(r) for r in rows["candidates"])
        pending = "".join(_row_card(r) for r in rows["pending"])
        zone = (
            f"<h2 id='cand'>triage candidates <span class='n'>{len(rows['candidates'])}</span>"
            f"</h2><p class='kv'>Ranked by the judge — read the rationale, then the reply, then "
            f"decide. These rows are the whole point of the human half.</p>{cand}"
            f"<h2 id='pend'>remaining pending rows <span class='n'>{len(rows['pending'])}</span>"
            f"</h2><p class='kv'>Not flagged by the judge — still undecided; give them the same "
            f"read.</p>{pending}")
    body = (
        masthead(f"review · {_esc(engagement)}",
                 [f"human half · localhost only · reviewer "
                  f"{_esc(reviewer or '(set --reviewer)')}"],
                 f"review { _esc(engagement)}"),
        "<div class='bar'>",
        "<span class='clock' id='clock'>00:00:00</span>",
        "<span class='tools'><button class='ghost' id='toggle'>start</button>"
        "<button class='ghost' id='finish'>FINISH (write timing)</button>"
        "<input id='search' placeholder='search case / payload / reply'>",
        "<span class='kbd-hint'>j/k move · o open · 1-4 verdict</span></span>",
        "<div class='progress'><span id='progress' style='white-space:nowrap'>"
        "@@DECIDED@@/@@EXPECTED@@ decided</span>"
        "<span class='pbar'><i id='pfill'></i></span>"
        "<span class='counts'><span id='c-hit'></span><span id='c-refused'></span>"
        "<span id='c-unsure'></span><span id='c-skip'></span></span></div>",
        "</div>",
        zone,
        f"<details class='scored-zone'><summary>already-scored attempts "
        f"({len(rows['scored'])}, read-only)</summary>{scored}</details>",
        "<p class='kbd-hint'>verdicts write "
        "<code>&lt;doc&gt;-human-review.json</code> beside the document; nothing here touches "
        "the engagement file or the sidecar.</p>",
        _WORKBENCH_JS.replace("@@TOKEN@@", json.dumps(token).replace("<", "\\u003c"))
                     .replace("@@ENGJSON@@", json.dumps(engagement).replace("<", "\\u003c")),
    )
    return page(f"Kessler review · {engagement}",
                _WORKBENCH_CSS + "\n<style>"
                ".scored-zone { margin-top: 2.5rem; } .scored-zone > summary { font-size: .9rem; }"
                "h2 .n { color: var(--muted); font-weight: 400; }</style>",
                "".join(body).replace("@@DECIDED@@", str(decided))
                             .replace("@@EXPECTED@@", str(expected)))


class _ReviewHandler(BaseHTTPRequestHandler):
    token = ""
    engagement = ""
    reviewer = ""
    rows = {}
    store_path = None
    expected = 0
    document_name = ""

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
                                   self._decided(), self.expected, self.document_name)
            self._send(200, "text/html; charset=utf-8", page.encode("utf-8"))
            return
        if path == "/api/progress":
            self._send(200, _JSON_CT, json.dumps(
                {"decided": self._decided(), "expected": self.expected}).encode("utf-8"))
            return
        if path == "/api/decisions":
            self._send(200, _JSON_CT, json.dumps(self._decisions()).encode("utf-8"))
            return
        self._send(404, "text/plain; charset=utf-8", b"not found\n")

    def _decisions(self) -> dict:
        """Recorded verdicts, so a reload restores the reviewer's visual state."""
        if not self.store_path.exists():
            return {}
        try:
            return json.loads(self.store_path.read_text(encoding="utf-8")).get("decisions", {})
        except (json.JSONDecodeError, OSError):
            return {}

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
        "document_name": document.name,
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
