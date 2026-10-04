#!/usr/bin/env python3
"""Build site/log/index.html + feeds (S-6/S-13, s32/K5): the Night Shift log.

Entries are generated from their own sources at build time - published pages (from build-reports'
PAGES metadata), register rows (baseline + bench registries), and a small curated
docs/log/releases.json for release/infra events. Nothing is hand-tallied into the page body.
Also writes /log/feed.xml and /reports/feed.xml."""
import json
import sys
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from xml.sax.saxutils import escape as xesc

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import importlib.util as _ilu
_spec = _ilu.spec_from_file_location("_br", ROOT / "scripts" / "build-reports.py")
_br = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_br)

from kessler import baseline, bench

MONTHS = {m: i for i, m in enumerate(
    "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split(), 1)}


def iso_from_display(s: str) -> str:
    try:
        d, mo, y = s.split()
        return f"{int(y):04d}-{MONTHS[mo]:02d}-{int(d):02d}"
    except (ValueError, KeyError, AttributeError):
        return ""


def iso_from_window(s: str) -> str:
    s = (s or "")[:10]
    return s if len(s) == 10 and s[4] == "-" else ""


def clean(s: str) -> str:
    return (s or "").replace("\u2014", " - ").strip()


entries = []

for p in _br.PAGES:
    d = iso_from_display(p.get("date", ""))
    if not d:
        continue
    out = p.get("out")
    if out:
        href = "/" + (out[: -len("index.html")] if out.endswith("index.html") else out)
    else:
        href = "/reports/" + p["slug"]
    entries.append({"date": d, "kind": p.get("kind", "Update"), "title": clean(p["title"]),
                    "href": href, "blurb": clean(p.get("blurb", "")), "source": "pages"})

reg = (baseline.load_registry(ROOT / "baseline-registry.json")
       if (ROOT / "baseline-registry.json").exists() else {"entries": []})
for e in reg["entries"]:
    d = iso_from_window(e.get("window", ""))
    if d:
        entries.append({"date": d, "kind": "Register",
                        "title": f'{e["ref"]} registered: {clean(e["source"])[:90]}',
                        "href": f'/register/#{e["ref"]}', "blurb": f'n={e["n"]}', "source": "register"})

try:
    breg = bench.load_register(ROOT / "bench-register.json")
except (OSError, ValueError):
    breg = {"units": []}
for u in breg["units"]:
    d = iso_from_window(u.get("window", ""))
    if d:
        entries.append({"date": d, "kind": "Bench",
                        "title": f'{u["ref"]} registered ({u.get("target_kind", "unit")})',
                        "href": "/register/", "blurb": f'n={u["n"]}', "source": "register"})

rel = json.loads((ROOT / "docs" / "log" / "releases.json").read_text(encoding="utf-8"))
for e in rel["entries"]:
    entries.append({"date": e["date"], "kind": e["kind"], "title": clean(e["title"]),
                    "href": e["href"], "blurb": clean(e.get("blurb", "")), "source": "releases"})

entries.sort(key=lambda e: e["date"], reverse=True)
assert entries, "empty log"


def disp_date(iso: str) -> str:
    d = datetime.fromisoformat(iso)
    return f"{d.day} {d.strftime('%b')} {d.year}"


items = "".join(
    f'<li class="kx-log-item"><span class="kx-log-date">{disp_date(e["date"])}</span>'
    f'<span class="kx-chip">{xesc(e["kind"])}</span>'
    f'<a href="{e["href"]}">{xesc(e["title"])}</a>'
    + (f'<p class="kx-log-blurb">{xesc(e["blurb"])}</p>' if e["blurb"] else "")
    + "</li>"
    for e in entries)

SUBSCRIBE = """
<h2 id="subscribe">Subscribe</h2>
<p class="ax-sub" style="max-width:62ch">Feeds, in any reader; no accounts, no trackers, no
drip sequences. The cadence target is weekly, and a boring on-time log builds more trust than
an occasional masterpiece.</p>
<div class="kx-toolbar">
<a class="kx-copy" style="text-decoration:none" href="feed.xml">The log - RSS</a>
<a class="kx-copy" style="text-decoration:none" href="/reports/feed.xml">Everything published - RSS</a>
<a class="kx-copy" style="text-decoration:none" href="/register/feed.xml">Register updates - RSS</a>
</div>
<p class="ax-sub">Prefer email? Write to
<a href="mailto:security@atlasnex.com?subject=Kessler%20digest">security@atlasnex.com</a>
and we add you to the occasional digest - no waitlist, no automated sequence.</p>
"""

body = (
    '<h1>The Night Shift log</h1>\n'
    '<p class="ax-sub" style="max-width:62ch">Everything the practice ships, dated and linked: '
    'measurements, teardowns, index issues, drills, releases, register updates. Generated at '
    'build time from the artifacts themselves - if it is not linked here, it did not ship.</p>\n'
    f'<ul class="kx-log">{items}</ul>\n'
    '<script type="application/json" id="kx-log-data">'
    + json.dumps({"n": len(entries)}, sort_keys=True) + "</script>\n"
    + SUBSCRIBE
    + """
<h2 id="install">Take it with you</h2>
<p class="ax-sub" style="max-width:62ch">The site installs as an app - offline reading of the
reports, registers and this log. No accounts, no push, nothing phoning home.</p>
<ul class="kx-log" style="max-width:62ch">
<li class="kx-log-item"><b>Android (Chrome):</b> the install chip appears bottom-right, or
menu &#8594; "Add to Home screen". Full citizen: standalone window, offline cache, themed
splash.</li>
<li class="kx-log-item"><b>iOS 16.4+ (Safari):</b> Share &#8594; Add to Home Screen. Web push
exists only inside Home-Screen apps on 16.4+, and this version deliberately sends none - the
feeds carry the cadence instead.</li>
<li class="kx-log-item"><b>Any desktop Chromium:</b> the same install works; everywhere else,
the feeds above are the account-free equivalent.</li>
</ul>
"""
)

html = _br.html_for("The Night Shift log | Kessler by AtlasNex", body, og="log",
                    kind="Cadence",
                    extra_head='<link rel="alternate" type="application/rss+xml" '
                               'title="Kessler Night Shift log" href="/log/feed.xml">')
assert "\u2014" not in html, "em dash in shipped copy"
out = ROOT / "site" / "log"
out.mkdir(exist_ok=True)
(out / "index.html").write_text(html, encoding="utf-8")


def json_feed(entries_: list[dict], out_dir: Path) -> None:
    """M-2: the machine feed the PWA and any SuperApp Kessler tab reads. Public, read-only,
    no accounts, no push. Same entries as the log; register summary; the /g2/ fraction."""
    from datetime import date as _date

    reg = (baseline.load_registry(ROOT / "baseline-registry.json")
           if (ROOT / "baseline-registry.json").exists() else {"entries": []})
    latest = []
    for e in sorted(reg["entries"], key=lambda x: x.get("window", ""), reverse=True)[:12]:
        n = int(e["n"])
        latest.append({"ref": e["ref"], "kind": "baseline", "n": n,
                       "successes": int(e["successes"]),
                       "status": ("published" if n >= baseline.N_FLOOR
                                  else f"not yet powered (n={n} < {baseline.N_FLOOR})")})
    g2: dict = {"status": "unavailable"}
    try:
        from kessler import threatindex
        files = (sorted(ROOT.glob("run-threatindex/export-all-*.jsonl"))
                 or sorted(ROOT.glob("run-threatindex/export-*.jsonl")))
        if files:
            caps = [json.loads(ln) for ln in
                    files[-1].read_text(encoding="utf-8").splitlines() if ln.strip()]
            by_month: dict = {}
            for r in caps:
                try:
                    text = (json.loads(r.get("request", "{}")).get("messages", [{}])[-1]
                            .get("content", ""))
                except (json.JSONDecodeError, IndexError, TypeError):
                    text = str(r.get("request", ""))
                at = str(r.get("at", ""))
                m = at[:7] if len(at) >= 7 and at[4] == "-" else "unlabelled"
                by_month.setdefault(m, []).append({"request": text, "hit": bool(r.get("hit"))})
            idx = threatindex.build_index(sorted(by_month.items()),
                                          generated=_date.today().isoformat(),
                                          own=threatindex.own_payload_set())
            m = idx["months"][-1] if idx["months"] else None
            if m:
                g2 = {"month": m["month"], "external_attempts": m["total"]["n"],
                      "external_hits": m["total"]["hits"],
                      "own_run_captures": m.get("own_run", 0)}
    except Exception:  # noqa: BLE001 - the feed must build even if the index cannot
        pass
    payload = {
        "schema": "kessler/feed/v1",
        "generated": _date.today().isoformat(),
        "note": "Public cadence feed for the Kessler PWA and the AtlasNex SuperApp Kessler tab. "
                "Read-only; no accounts; no push. Every figure is a counted measurement.",
        "entries": entries_[:40],
        "register": {"units": len(reg["entries"]), "floor": baseline.N_FLOOR, "latest": latest},
        "g2": g2,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "kessler.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    print(f"built site/feed/kessler.json ({len(payload['entries'])} entries)")


def feed(title: str, desc: str, items_src: list[dict], path: Path) -> None:
    def rfc(iso: str) -> str:
        return format_datetime(datetime.fromisoformat(iso).replace(tzinfo=timezone.utc))

    is_ = "".join(
        "<item><title>{t}</title><link>https://kessler.atlasnex.com{h}</link>"
        '<guid isPermaLink="false">kx-{d}-{h2}-{k}</guid><pubDate>{p}</pubDate>'
        "<description>{b}</description></item>".format(
            t=xesc(e["title"]), h=e["href"], d=e["date"],
            h2=xesc(e["href"].split("#")[-1][:40]), k=xesc(e["kind"]),
            p=rfc(e["date"]), b=xesc(e.get("blurb", "")))
        for e in items_src)
    xml = ('<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>'
           f"<title>{xesc(title)}</title>"
           "<link>https://kessler.atlasnex.com/log/</link>"
           f"<description>{xesc(desc)}</description>" + is_ + "</channel></rss>")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(xml, encoding="utf-8")


feed("Kessler Night Shift log", "Everything the practice ships, dated and linked.",
     entries, out / "feed.xml")
feed("Kessler - published work",
     "Every publication, dated and linked. The feed denotes updates, not verdicts.",
     [e for e in entries if e["source"] == "pages"], ROOT / "site" / "reports" / "feed.xml")
json_feed(entries, ROOT / "site" / "feed")

print(f"built site/log/index.html ({len(html)} bytes), log/feed.xml, reports/feed.xml; "
      f"{len(entries)} entries")
