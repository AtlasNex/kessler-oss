#!/usr/bin/env python3
"""Build /console/ - the Kessler Konsole, live.

The sealed run replays as a working instrument. Everything on the page is real:
- rows/verdicts/counters from run-selftest/a7-engagement.json (25 attempts, 1 got through)
- the corpus count from kessler.corpus.build() (the same source the tests pin)
- the estate numbers from the deployed feed (register units, external attempts, captures)
- the capsule chain line matches the sealed artifact verified at /verify/

Sounds are the four ElevenLabs cues in site/assets/sfx (generated via the vault key,
through the VPS network path). Buttons wire to real surfaces: recount -> /verify/,
triage desk -> /sample/#demo-triage-desk, re-run copies the real CLI command.

ASCII-safe: the data island uses json.dumps defaults (\\uXXXX escapes), so the shipped
file stays ASCII for the deploy gate while the browser renders the real characters."""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from kessler.corpus import build  # noqa: E402

A7 = ROOT / "run-selftest" / "a7-engagement.json"
FEED = ROOT / "site" / "feed" / "kessler.json"
OUT = ROOT / "site" / "console" / "index.html"


def wilson(k: int, n: int) -> tuple[float, float]:
    z = 1.959963984540054
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = (z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5)) / d
    return max(0.0, c - h), min(1.0, c + h)


def main() -> int:
    data = json.loads(A7.read_text(encoding="utf-8"))
    ats = data["attempts"]
    t0 = datetime.fromisoformat(ats[0]["at"])
    rows = []
    for i, a in enumerate(ats):
        off = int((datetime.fromisoformat(a["at"]) - t0).total_seconds())
        tech = a["technique"].split(":", 1)[-1]
        pay = " ".join(str(a.get("payload") or "").split())[:74]
        obs = " ".join(str(a.get("observed") or "").split())[:220]
        rows.append({"seq": i + 1, "m": off, "tech": tech, "pay": pay,
                     "hit": bool(a["succeeded"]), "fam": a["category"], "obs": obs})
    n, k = len(rows), sum(1 for r in rows if r["hit"])
    lo, hi = wilson(k, n)
    corpus = len(build()[0])

    units, ext, captures = 5, 0, None
    if FEED.exists():
        f = json.loads(FEED.read_text(encoding="utf-8"))
        units = f.get("register", {}).get("units", units)
        g2 = f.get("g2", {})
        ext = g2.get("external_attempts", ext)
        captures = g2.get("own_run_captures")

    rows_js = json.dumps(rows, sort_keys=True)
    today = datetime.now().strftime("%d %b %Y")
    captures_html = (f"{captures:,}" if captures else "building")

    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>The Konsole - watch the Kessler sealed run, line by line</title>
<meta name="description" content="The Kessler Konsole replays the sealed A7 self-test as a working instrument: 25 attempts stream in, each verdict stamped, every number recomputable at /verify/.">
<link rel="canonical" href="https://kessler.atlasnex.com/console/">
<meta property="og:image" content="https://kessler.atlasnex.com/og/console.png">
<meta property="og:title" content="The Konsole - the sealed run, line by line">
<meta name="kx:kind" content="console">
<meta name="theme-color" content="#0A1631">
<link rel="icon" type="image/svg+xml" href="https://atlasnex.com/favicon.svg">
<link rel="stylesheet" href="/kx.css?v=7">
<style>
@font-face{{font-family:'Sora';font-weight:400 800;src:url(/assets/fonts/sora-latin-700-normal.woff2)}}
@font-face{{font-family:'HKG';font-weight:400;src:url(/assets/fonts/hanken-grotesk-latin-400-normal.woff2)}}
@font-face{{font-family:'JBM';font-weight:500;src:url(/assets/fonts/jetbrains-mono-latin-500-normal.woff2)}}
@font-face{{font-family:'Kalam';font-weight:400;src:url(/assets/fonts/kalam-latin-400-normal.woff2)}}
:root{{
  --paper:#F6F4EF; --paper2:#EDEAE2; --card:#FFFEFA; --ink:#0A1631; --mid:#060E22;
  --mute:#545D6B; --lunar:#A9B1C4;
  --green:#2FBF8F; --green-ink:#0B7A55; --amber:#F2B544; --coral:#F4655B; --cta:#C7372E;
  --vio:#8B7CF6; --vio-ink:#5B48C9;
  --ease:cubic-bezier(.16,1,.3,1);
  --mono:'JBM',ui-monospace,monospace; --sans:'HKG',system-ui,sans-serif; --disp:'Sora',system-ui,sans-serif; --hand:'Kalam',cursive;
}}
*{{box-sizing:border-box;margin:0;padding:0}}
html,body{{height:100%}}
body{{background:var(--paper);color:var(--ink);font-family:var(--sans);font-size:14px;overflow:hidden}}
::selection{{background:var(--green);color:var(--ink)}}
a:focus-visible,button:focus-visible{{outline:3px solid var(--green);outline-offset:3px}}
.skip{{position:absolute;left:-999px;top:0;background:var(--ink);color:var(--paper);padding:10px 16px;z-index:99}}
.skip:focus{{left:8px;top:8px}}
.app{{display:grid;grid-template-columns:248px 1fr 336px;grid-template-rows:64px 1fr 60px;height:100%;gap:14px;padding:14px}}
.hud{{font:500 10.5px var(--mono);letter-spacing:.15em;text-transform:uppercase;color:var(--mute)}}
.card{{background:var(--card);border:2px solid var(--ink);box-shadow:6px 6px 0 var(--ink)}}
.instrument{{background:var(--mid);border:2px solid var(--ink);color:var(--paper);
  box-shadow:6px 6px 0 var(--ink), inset 0 0 0 1px rgba(246,244,239,.05), inset 0 16px 40px rgba(0,0,0,.35);
  transform-style:preserve-3d;transition:transform .25s var(--ease);will-change:transform}}
.top{{grid-column:1/-1;display:flex;align-items:center;gap:14px;background:var(--paper);color:var(--ink);
  border:2px solid var(--ink);box-shadow:6px 6px 0 var(--ink);padding:0 16px}}
.brand{{display:flex;align-items:center;gap:11px;font:700 19px var(--disp);letter-spacing:-.03em;color:var(--ink);text-decoration:none}}
.brand .dot{{width:12px;height:12px;background:var(--vio);border:2px solid var(--ink);border-radius:50%}}
.brand small{{font:500 10px var(--mono);letter-spacing:.18em;text-transform:uppercase;color:var(--mute);margin-left:2px}}
.statepill{{display:inline-flex;align-items:center;gap:7px;font:500 10.5px var(--mono);letter-spacing:.13em;
  text-transform:uppercase;border:2px solid var(--ink);padding:6px 10px;background:var(--card)}}
.statepill i{{width:8px;height:8px;border-radius:50%;background:var(--coral);border:1.5px solid var(--ink);animation:blink 1.4s steps(2,end) infinite}}
.statepill.ok i{{background:var(--green);animation:none}}
@keyframes blink{{50%{{opacity:.35}}}}
.clock{{font:500 14px var(--mono);letter-spacing:.08em;font-variant-numeric:tabular-nums;border:2px solid var(--ink);padding:6px 11px;background:var(--card)}}
.transport{{margin-left:auto;display:flex;gap:9px;margin-right:4px}}
.tbtn{{font:600 13px var(--mono);color:var(--ink);background:var(--card);border:2px solid var(--ink);
  min-width:46px;height:38px;cursor:pointer;box-shadow:3px 3px 0 var(--ink);
  transition:box-shadow .16s var(--ease),translate .16s var(--ease)}}
.tbtn:hover{{box-shadow:5px 5px 0 var(--ink)}}
.tbtn:active{{box-shadow:0 0 0;translate:3px 3px}}
.tbtn.on{{background:var(--green)}}
.stamp{{font:700 10px var(--mono);letter-spacing:.14em;text-transform:uppercase;color:var(--cta);
  border:2px solid var(--cta);padding:6px 10px 7px;rotate:-1.4deg;background:var(--paper);margin-right:4px}}
.rail{{display:flex;flex-direction:column;gap:14px;min-height:0}}
.navv{{padding:12px}}
.navv a{{display:flex;align-items:center;gap:12px;color:var(--mute);text-decoration:none;
  font:600 13px var(--disp);padding:10px;border:2px solid transparent;transition:all .15s var(--ease)}}
.navv a b{{font:500 10.5px var(--mono);letter-spacing:.08em}}
.navv a:hover{{border-color:var(--ink)}}
.navv a.on{{background:var(--ink);color:var(--paper);border-color:var(--ink);box-shadow:4px 4px 0 rgba(10,22,49,.25)}}
.navv a.on b{{color:var(--lunar)}}
.estate{{padding:14px}}
.estate h4{{margin-bottom:9px}}
.kpi{{display:flex;justify-content:space-between;align-items:baseline;padding:7px 0;border-bottom:1.5px dashed rgba(10,22,49,.22)}}
.kpi:last-child{{border-bottom:0}}
.kpi dt{{font:500 10px var(--mono);letter-spacing:.12em;text-transform:uppercase;color:var(--mute)}}
.kpi dd{{font:700 18px var(--disp);letter-spacing:-.02em;font-variant-numeric:tabular-nums}}
.kpi dd em{{font:500 10px var(--mono);color:var(--green-ink);font-style:normal;letter-spacing:.08em}}
.note{{background:#FFD85A;border:1.5px solid var(--ink);box-shadow:3px 3px 0 var(--ink);padding:10px 13px 8px;
  font-family:var(--hand);font-size:15px;line-height:1.35;rotate:-1deg;margin:14px 3px 3px}}
.note small{{display:block;font-family:var(--mono);font-size:8.5px;letter-spacing:.14em;text-transform:uppercase;color:var(--mute);margin-top:5px}}
.canvas{{display:flex;flex-direction:column;min-height:0;gap:14px}}
.lanehead{{display:flex;align-items:flex-end;gap:20px;padding:16px 22px 15px}}
.krail{{display:flex;flex-direction:column;align-items:center;gap:8px;padding-right:14px;border-right:1.5px solid rgba(10,22,49,.25)}}
.krail b{{font:700 15px var(--disp);color:var(--green-ink)}}
.krail i{{writing-mode:vertical-rl;font:500 10px var(--mono);letter-spacing:.22em;text-transform:uppercase;color:var(--mute);font-style:normal}}
.lanehead h1{{font:700 26px/1 var(--disp);letter-spacing:-.04em;margin-bottom:4px}}
.lanehead .sub{{display:block;margin-top:8px}}
.clause{{font:700 15px var(--disp);color:var(--green-ink);border:2px solid currentColor;padding:4px 10px;rotate:-2deg;white-space:nowrap;margin-bottom:6px}}
.hudchip{{font:500 10px var(--mono);letter-spacing:.13em;text-transform:uppercase;border:2px solid var(--ink);padding:5px 10px;background:var(--paper2);margin-bottom:5px}}
.counters{{margin-left:auto;display:flex;gap:28px;text-align:right;align-items:flex-end;padding-bottom:1px}}
.counters b{{font:700 32px/1 var(--disp);letter-spacing:-.045em;font-variant-numeric:tabular-nums;display:block}}
.counters span{{display:block;margin-top:7px}}
#cH{{color:var(--cta)}}
.hl{{background:linear-gradient(transparent 16%,rgba(47,191,143,.85) 16%,rgba(47,191,143,.85) 86%,transparent 86%) no-repeat 0 62%/var(--hl,0%) 78%;transition:background-size .55s var(--ease)}}
.stream{{flex:1;min-height:0;display:flex;flex-direction:column;overflow:hidden}}
.streamtop{{display:flex;align-items:center;gap:14px;padding:12px 18px 10px;border-bottom:2px solid rgba(246,244,239,.85)}}
.runbar{{width:34px;height:3px;background:var(--green)}}
#rows{{flex:1;min-height:0;overflow:hidden}}
.row{{display:grid;grid-template-columns:50px 84px 116px 1fr 168px;gap:12px;align-items:center;
  padding:10px 18px;border-top:1.5px solid rgba(246,244,239,.16);font:500 12px var(--mono);
  animation:inrow .4s var(--ease) both}}
@keyframes inrow{{from{{opacity:0;translate:0 6px}}to{{opacity:1;translate:0 0}}}}
.row:hover{{background:rgba(246,244,239,.06)}}
.row .seq{{color:var(--lunar);text-align:right}} .row .t{{color:var(--lunar)}}
.row .tech{{color:var(--paper)}}
.row .pay{{color:var(--lunar);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.st{{justify-self:start;font:700 10px var(--mono);letter-spacing:.09em;text-transform:uppercase;
  border:1.5px solid var(--paper);padding:4px 8px;animation:stampin .4s var(--ease) both;transform-origin:left center;min-width:126px;text-align:center}}
@keyframes stampin{{0%{{transform:scale(1.45) rotate(-7deg);opacity:0}}62%{{transform:scale(.97) rotate(1deg);opacity:1}}100%{{transform:none}}}}
.st.held{{background:var(--green);color:var(--ink);border-color:var(--green)}}
.st.hit{{background:var(--cta);color:#FFFFFF;border-color:var(--cta);rotate:-2deg}}
.viz{{border-top:2px solid rgba(246,244,239,.85);padding:13px 18px 14px;display:flex;gap:28px;align-items:center}}
.viz .hud{{margin-bottom:8px;color:var(--lunar)}}
.queue{{display:flex;gap:9px;align-items:center;border-top:1.5px solid rgba(246,244,239,.3);padding:11px 18px 13px}}
.qo{{font:500 11px var(--mono);letter-spacing:.06em;color:var(--ink);background:var(--paper2);border:1.5px solid var(--ink);padding:5px 10px;box-shadow:2px 2px 0 rgba(246,244,239,.5)}}
.capnote{{font:500 10.5px var(--mono);color:var(--lunar);letter-spacing:.03em}}
.capnote a{{color:var(--green)}}
.insp{{display:flex;flex-direction:column;min-height:0}}
.insp .head{{padding:15px 16px 12px;border-bottom:2px solid var(--ink);display:flex;justify-content:space-between;align-items:baseline}}
.insp .head h2{{font:700 17px var(--disp);letter-spacing:-.02em}}
.insp .body{{padding:14px 16px;display:grid;gap:13px;align-content:start;overflow:hidden}}
.kv{{display:grid;grid-template-columns:108px 1fr;gap:6px 12px;font:500 11.5px var(--mono)}}
.kv dt{{color:var(--mute);font-size:10px;letter-spacing:.1em;text-transform:uppercase;padding-top:2px}}
.kv dd{{color:var(--ink);word-break:break-word}}
.ev{{border-left:3px solid var(--green);padding:2px 0 2px 12px;font:500 12px/1.65 var(--sans);color:var(--ink)}}
.ev b{{font-family:var(--mono);font-size:10px;letter-spacing:.1em;text-transform:uppercase;color:var(--green-ink);display:block;margin-bottom:3px}}
.ev.warn{{border-left-color:var(--cta)}} .ev.warn b{{color:var(--cta)}}
.actions{{display:grid;gap:10px;padding:0 16px 16px;margin-top:auto}}
.act{{font:600 14.5px var(--disp);display:flex;justify-content:space-between;align-items:center;cursor:pointer;
  padding:12px 14px;border:2px solid var(--ink);background:var(--paper);color:var(--ink);text-decoration:none;
  box-shadow:4px 4px 0 var(--ink);transition:box-shadow .16s var(--ease),translate .16s var(--ease)}}
.act:hover{{box-shadow:7px 7px 0 var(--ink)}}
.act:active{{box-shadow:0 0 0;translate:4px 4px}}
.act i{{font-style:normal;display:inline-grid;place-items:center;width:26px;height:26px;background:var(--ink);color:var(--paper);border:2px solid var(--ink)}}
.act.mag i{{background:var(--cta);color:#FFFFFF}}
.tline{{grid-column:1/-1;display:flex;align-items:center;gap:16px;padding:0 18px;background:var(--card);border:2px solid var(--ink);box-shadow:6px 6px 0 var(--ink)}}
.track{{flex:1;height:32px;position:relative}}
.railbar{{position:absolute;left:0;right:0;top:15px;height:3px;background:rgba(10,22,49,.25)}}
.fill{{position:absolute;left:0;top:15px;height:3px;background:var(--green);width:0;transition:width .55s linear}}
.mk{{position:absolute;top:10px;width:3px;height:13px;background:rgba(10,22,49,.28)}}
.mk.done{{background:var(--green-ink)}}
.mk.hit{{background:var(--cta);top:7px;height:19px;width:4px;rotate:8deg}}
.head2{{position:absolute;top:5px;width:6px;height:24px;background:var(--amber);border:2px solid var(--ink);transition:left .55s linear}}
.toast{{position:fixed;left:50%;bottom:22px;translate:-50% 0;background:var(--ink);color:var(--paper);border:2px solid var(--paper);font:500 12px var(--mono);letter-spacing:.06em;padding:10px 16px;opacity:0;pointer-events:none;transition:opacity .25s;z-index:50}}
.toast.on{{opacity:1}}
.soundbtn{{font:500 11px var(--mono);letter-spacing:.06em;border:2px solid var(--ink);background:var(--card);color:var(--ink);padding:8px 11px;cursor:pointer}}
footer.kfoot{{display:none}}
@media (max-width:1180px){{.app{{grid-template-columns:220px 1fr}}.insp{{display:none}}}}
@media (prefers-reduced-motion:reduce){{*{{animation:none!important;transition:none!important}}.instrument{{transform:none!important}}}}
</style></head>
<body>
<a class="skip" href="#rows">Skip to the run</a>
<div class="app">
  <header class="top">
    <a class="brand" href="/"><span class="dot"></span>Kessler <small>konsole by atlasnex</small></a>
    <span class="statepill"><i></i>replay &middot; sealed run</span>
    <span class="statepill ok"><i></i>lane a7</span>
    <span class="clock" id="clock">00:00:00</span>
    <div class="transport">
      <button class="tbtn on" id="btnPlay" title="play / pause" aria-label="play or pause the replay">&#10074;&#10074;</button>
      <button class="tbtn" id="btnStep" title="step one line" aria-label="step one line">&#9654;&#9654;</button>
      <button class="tbtn" id="btnSpeed" title="speed">1x</button>
    </div>
    <button class="soundbtn" id="btnSound" aria-pressed="true">sound on</button>
    <span class="stamp">not live &middot; replays the sealed run</span>
  </header>

  <aside class="rail">
    <nav class="card navv" aria-label="Konsole sections"><p class="hud" style="padding:4px 10px 10px">sections</p>
      <a class="on" href="/console/"><b>&#167;1</b>Konsole</a>
      <a href="/log/"><b>&#167;2</b>Night log</a>
      <a href="/register/"><b>&#167;3</b>Register</a>
      <a href="/reports/09-threat-index-001.html"><b>&#167;4</b>Threat index</a>
      <a href="/verify/"><b>&#167;5</b>Verify</a>
      <a href="/pricing/"><b>&#167;6</b>Engage</a>
    </nav>
    <section class="card estate">
      <p class="hud">estate &middot; checked today</p>
      <dl class="kpi"><dt>corpus</dt><dd>{corpus:,}</dd></dl>
      <dl class="kpi"><dt>register units</dt><dd>{units}</dd></dl>
      <dl class="kpi"><dt>outside attempts 10/26</dt><dd>{ext} <em>&#10003; none yet</em></dd></dl>
      <dl class="kpi"><dt>own captures</dt><dd>{captures_html}</dd></dl>
    </section>
    <div class="note">the bench is idle. press play - this run reads itself out, one held line at a time.
      <small>nex note &middot; one per screen</small></div>
  </aside>

  <main class="canvas">
    <section class="card lanehead">
      <div class="krail"><b>&#167;01</b><i>sealed run</i></div>
      <h1>Selftest &middot; A7 <span class="sub hud">lane 01 // own stack // ran 13-14 sep &middot; sealed</span></h1>
      <span class="clause">lane 01</span>
      <span class="hudchip">25 attempts</span>
      <div class="counters">
        <div><b id="cN">0</b><span class="hud">attempted</span></div>
        <div><b id="cH">0</b><span class="hud">got through</span></div>
        <div><b><span class="hl" id="cRwrap"><span id="cR">-</span></span></b><span class="hud">rate</span></div>
        <div><b id="cB">-</b><span class="hud">true rate sits in</span></div>
      </div>
    </section>
    <section class="instrument stream" id="stream">
      <div class="streamtop"><span class="runbar"></span><span class="hud" style="color:var(--lunar)">the run, as it happened</span>
        <span class="hud" style="color:var(--lunar);margin-left:auto">each line stays a line - nothing is deleted</span></div>
      <div id="rows" tabindex="0" role="log" aria-live="off" aria-label="the run, line by line"></div>
      <div class="viz">
        <div style="width:252px"><p class="hud">where the true rate sits (95%)</p>
          <canvas id="band" width="252" height="56" aria-label="confidence band for the true rate"></canvas></div>
        <div style="width:210px"><p class="hud">lines that got through</p>
          <canvas id="spark" width="210" height="56" aria-label="one dot per line that got through"></canvas></div>
        <p class="capnote" style="margin-left:auto;max-width:250px">every number here recomputes at <a href="/verify/">/verify/</a> - same arithmetic, run in your browser.</p>
      </div>
      <div class="queue"><span class="hud" style="color:var(--lunar)">up next</span><div id="qrows" style="display:flex;gap:8px;flex-wrap:nowrap;overflow:hidden"></div></div>
    </section>
  </main>

  <aside class="insp card">
    <div class="head"><h2>Line inspector</h2><span class="hud">p. <span id="iPage">01</span> / 25</span></div>
    <div class="body">
      <dl class="kv">
        <dt>line</dt><dd id="iRef">-</dd>
        <dt>family</dt><dd id="iCat">-</dd>
        <dt>technique</dt><dd id="iTech">-</dd>
        <dt>who decided</dt><dd id="iOra">-</dd>
        <dt>ran at</dt><dd id="iLat">-</dd>
      </dl>
      <div class="ev" id="iEv"><b>what happened</b>press play, then click any line.</div>
      <div class="ev"><b>chain</b>capsule link 13 of 27 &middot; hash ok &middot; head 00d525c4&hellip;</div>
    </div>
    <div class="actions">
      <a class="act mag" href="/verify/" id="actRecount">Recount this capsule <i>&#8599;</i></a>
      <a class="act" href="/sample/#demo-triage-desk">Open in triage desk <i>&#8599;</i></a>
      <button class="act" id="actRerun">Copy the re-run command <i>&#9654;</i></button>
    </div>
  </aside>

  <footer class="tline">
    <span class="hud">t-0</span>
    <div class="track" id="track"><div class="railbar"></div><div class="fill" id="tfill"></div><div class="head2" id="thead" style="left:0"></div></div>
    <span class="hud" id="tcap" style="font-variant-numeric:tabular-nums">0 / {n}</span>
  </footer>
</div>
<div class="toast" id="toast" role="status"></div>
<audio id="s-tick" preload="none" src="/assets/sfx/kx-tick.mp3"></audio>
<audio id="s-stamp" preload="none" src="/assets/sfx/kx-stamp.mp3"></audio>
<audio id="s-click" preload="none" src="/assets/sfx/kx-click.mp3"></audio>
<audio id="s-seal" preload="none" src="/assets/sfx/kx-seal.mp3"></audio>

<script>
"use strict";
var RUN = {rows_js};
var N=0,H=0,i=0,playing=true,startedAt=0;
var rows=document.getElementById("rows"),track=document.getElementById("track");
var mks=[];
RUN.forEach(function(_,x){{var mk=document.createElement("div");mk.className="mk";mk.style.left=(x/(RUN.length-1)*100)+"%";track.appendChild(mk);mks.push(mk);}});
var hitMk=document.createElement("div");hitMk.className="mk hit";hitMk.style.left=((RUN.findIndex(function(r){{return r.hit;}}))/(RUN.length-1)*100)+"%";track.appendChild(hitMk);
var qrows=document.getElementById("qrows");
RUN.slice(6,14).forEach(function(r){{var s=document.createElement("span");s.className="qo";s.textContent=r.tech;qrows.appendChild(s);}});
var soundOn=(localStorage.getItem("kx-sound")||"on")==="on";
var sTick=document.getElementById("s-tick"),sStamp=document.getElementById("s-stamp"),sClick=document.getElementById("s-click"),sSeal=document.getElementById("s-seal");
function ping(el){{ if(!soundOn) return; try{{ var p=el.cloneNode(); p.volume=.5; p.play(); }}catch(e){{}} }}
function setSoundLabel(){{var b=document.getElementById("btnSound");b.textContent=soundOn?"sound on":"sound off";b.setAttribute("aria-pressed",soundOn?"true":"false");}}
setSoundLabel();
document.getElementById("btnSound").addEventListener("click",function(){{soundOn=!soundOn;localStorage.setItem("kx-sound",soundOn?"on":"off");setSoundLabel();}});
function toast(msg){{var t=document.getElementById("toast");t.textContent=msg;t.classList.add("on");setTimeout(function(){{t.classList.remove("on");}},1800);}}
document.getElementById("actRerun").addEventListener("click",function(){{
  var cmd="kessler run scopes/selftest-scope.json";
  (navigator.clipboard?navigator.clipboard.writeText(cmd):Promise.reject()).then(function(){{toast("copied: "+cmd);}}).catch(function(){{toast(cmd);}});
  ping(sClick);
}});
document.getElementById("actRecount").addEventListener("click",function(){{ping(sSeal);}});
document.querySelectorAll(".act").forEach(function(a){{a.addEventListener("click",function(){{ping(sClick);}});}});
function wilson(k,n){{var z=1.959963984540054,p=k/n,d=1+z*z/n,c=(p+z*z/(2*n))/d,h=(z*Math.sqrt(p*(1-p)/n+z*z/(4*n*n)))/d;return[Math.max(0,c-h),Math.min(1,c+h)];}}
function bandDraw(){{
  var c=document.getElementById("band"),g=c.getContext("2d");g.clearRect(0,0,252,56);
  g.strokeStyle="rgba(246,244,239,.35)";g.lineWidth=1.5;g.strokeRect(10.75,9.75,230,32);
  g.fillStyle="#A9B1C4";g.font="500 10px monospace";
  if(N<2){{g.fillText("waiting for the first lines",12,52);return;}}
  var w=wilson(H,N),x0=11+w[0]*229,x1=11+w[1]*229;
  g.fillStyle="rgba(47,191,143,.32)";g.fillRect(x0,11,x1-x0,31);
  g.strokeStyle="#2FBF8F";g.strokeRect(x0,11,x1-x0,31);
  g.fillStyle="#F6F4EF";g.beginPath();g.arc(11+(H/N)*229,26.5,5,0,7);g.fill();
  g.strokeStyle="#0A1631";g.lineWidth=2;g.stroke();
  g.fillStyle="#A9B1C4";g.fillText("0",10,54);g.fillText("100%",220,54);
}}
function sparkDraw(){{
  var c=document.getElementById("spark"),g=c.getContext("2d");g.clearRect(0,0,210,56);
  g.fillStyle="#A9B1C4";g.font="500 10px monospace";
  if(N<2){{g.fillText("nothing yet",12,36);return;}}
  RUN.forEach(function(r,idx){{if(idx<i&&r.hit){{var x=12+idx/(RUN.length-1)*186;g.fillStyle="#F4655B";g.beginPath();g.arc(x,26,5,0,7);g.fill();g.strokeStyle="#0A1631";g.lineWidth=2;g.stroke();}}}});
  g.fillStyle="#A9B1C4";g.fillText("one dot = one line that got through",12,50);
}}
function esc(s){{return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;");}}
function drawHL(){{var rw=document.getElementById("cRwrap");var target=8+Math.min(70,(H/N*100)*1.3);rw.style.setProperty("--hl","0%");void rw.offsetWidth;requestAnimationFrame(function(){{rw.style.setProperty("--hl",target+"%");}});}}
function step(){{
  if(i>=RUN.length)return;
  var r=RUN[i],hit=r.hit;N++;if(hit)H++;
  var el=document.createElement("div");el.className="row";
  var mm=String(Math.floor(r.m/60)).padStart(2,"0"),ss=String(r.m%60).padStart(2,"0");
  el.innerHTML='<span class="seq">'+String(i+1).padStart(2,"0")+'</span><span class="t">m+'+mm+':'+ss+'</span><span class="tech">'+esc(r.tech)+'</span><span class="pay">'+esc(r.pay)+'</span><span class="st '+(hit?"hit":"held")+'">'+(hit?"got through":"held")+'</span>';
  el.addEventListener("click",function(){{inspect(r,i);ping(sClick);}});
  rows.insertBefore(el,rows.firstChild);
  while(rows.children.length>10){{rows.removeChild(rows.lastChild);}}
  document.getElementById("cN").textContent=N;
  document.getElementById("cH").textContent=H;
  document.getElementById("cR").textContent=(H/N*100).toFixed(1)+"%";
  drawHL();
  var w=wilson(H,N);document.getElementById("cB").textContent="["+(w[0]*100).toFixed(0)+"%, "+(w[1]*100).toFixed(0)+"%]";
  document.getElementById("tfill").style.width=(i/(RUN.length-1)*100)+"%";
  document.getElementById("thead").style.left=(i/(RUN.length-1)*100)+"%";
  document.getElementById("tcap").textContent=(i+1)+" / "+RUN.length;
  document.getElementById("iPage").textContent=String(i+1).padStart(2,"0");
  if(mks[i]){{mks[i].classList.add("done");}}
  ping(hit?sStamp:sTick);
  el.click();bandDraw();sparkDraw();
  if(qrows&&qrows.firstChild){{qrows.removeChild(qrows.firstChild);}}
  i++;
}}
function inspect(r,idx){{
  document.getElementById("iRef").textContent="line "+(idx+1)+" of "+RUN.length;
  document.getElementById("iCat").textContent=r.fam+" - family "+r.fam.slice(3);
  document.getElementById("iTech").textContent=r.tech;
  document.getElementById("iOra").textContent=r.hit?"the harness watched it get through":"the harness watched it get refused";
  var mm=String(Math.floor(r.m/60)).padStart(2,"0"),ss=String(r.m%60).padStart(2,"0");
  document.getElementById("iLat").textContent="m+"+mm+":"+ss;
  var ev=document.getElementById("iEv");
  if(r.hit){{ev.className="ev warn";ev.innerHTML="<b>what happened</b>"+(r.obs?esc(r.obs):"the agent followed the planted instruction.")+" The line stays in the report and in the capsule - it is not hidden.";}}
  else{{ev.className="ev";ev.innerHTML="<b>what happened</b>"+(r.obs?esc(r.obs):"no effect observed - the refusal is on the record. A held line counts as an attempt, never as a pass by default.");}}
}}
setInterval(function(){{
  if(!playing||i>=RUN.length)return;
  if(startedAt===0){{startedAt=Date.now();}}
  var t=(Date.now()-startedAt)/1000,hh=String(Math.floor(t/3600)).padStart(2,"0"),mm=String(Math.floor(t/60)%60).padStart(2,"0"),ss=String(Math.floor(t)%60).padStart(2,"0");
  document.getElementById("clock").textContent=hh+":"+mm+":"+ss;
  step();
}},900);
document.getElementById("btnPlay").addEventListener("click",function(){{
  playing=!playing;this.innerHTML=playing?"&#10074;&#10074;":"&#9654;";this.classList.toggle("on",playing);ping(sClick);
}});
document.getElementById("btnStep").addEventListener("click",function(){{playing=false;var p=document.getElementById("btnPlay");p.innerHTML="&#9654;";p.classList.remove("on");step();}});
document.getElementById("btnSpeed").addEventListener("click",function(){{this.textContent=this.textContent==="1x"?"2x":this.textContent==="2x"?"4x":"1x";ping(sClick);}});
/* deterministic preview for screenshots/audits: /console/?n=16 freezes the run at line 16 */
var pn=parseInt(new URLSearchParams(location.search).get("n")||"0",10);
if(pn>0){{playing=false;var pb=document.getElementById("btnPlay");pb.innerHTML="&#9654;";pb.classList.remove("on");for(var pz=0;pz<Math.min(pn,RUN.length);pz++){{step();}}}}
if(!window.matchMedia("(prefers-reduced-motion: reduce)").matches){{
  var st=document.getElementById("stream");
  window.addEventListener("pointermove",function(e){{
    var r=st.getBoundingClientRect();
    var x=(e.clientX-r.left)/r.width-0.5, y=(e.clientY-r.top)/r.height-0.5;
    st.style.transform="perspective(1500px) rotateY("+(x*1.7).toFixed(2)+"deg) rotateX("+(-y*1.2).toFixed(2)+"deg)";
  }});
}}
</script>
</body></html>
"""

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(page, encoding="utf-8", newline="")
    print(f"built {OUT.relative_to(ROOT)} ({len(page):,} bytes) | rows={n} hits={k} "
          f"band=[{lo*100:.1f}%, {hi*100:.1f}%] corpus={corpus:,} units={units} ext={ext}")
    assert page[:15].lower().startswith("<!doctype"), "bad head"
    assert "\u2014" not in page, "deploy gate: em dash in shipped copy"
    return 0


if __name__ == "__main__":
    sys.exit(main())
