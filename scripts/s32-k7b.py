"""K7 wave-1 edits (asserted, atomic): M-2 JSON feed into build-log-page.py; M-1 install copy
on the log page; CORS feed route in serve.py."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def edit(path: Path, pairs: list[tuple[str, str]]) -> None:
    t = path.read_text(encoding="utf-8")
    for old, new in pairs:
        cnt = t.count(old)
        if cnt != 1:
            raise SystemExit(f"ANCHOR FAIL {path.name}: {cnt} for {old[:90]!r}")
        t = t.replace(old, new, 1)
    path.write_text(t, encoding="utf-8", newline="")
    print(f"edited {path.name} ({len(pairs)} edits)")


FEED_FN = '''def json_feed(entries_: list[dict], out_dir: Path) -> None:
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


def feed(title: str, desc: str, items_src: list[dict], path: Path) -> None:'''

INSTALL_INLINE = '''    + SUBSCRIBE
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
)'''

edit(ROOT / "scripts" / "build-log-page.py", [(
    "def feed(title: str, desc: str, items_src: list[dict], path: Path) -> None:",
    FEED_FN,
), (
    "    + SUBSCRIBE\n)",
    INSTALL_INLINE,
), (
    '     [e for e in entries if e["source"] == "pages"], ROOT / "site" / "reports" / "feed.xml")\n',
    '     [e for e in entries if e["source"] == "pages"], ROOT / "site" / "reports" / "feed.xml")\n'
    'json_feed(entries, ROOT / "site" / "feed")\n',
)])

edit(ROOT / "site" / "serve.py", [(
    '        if path in ("/g2", "/g2/"):',
    '''        if path == "/feed/kessler.json":
            # M-2: the public machine feed (PWA + any SuperApp Kessler tab). CORS open by
            # design - it is the same data as /log/, published.
            fp = BASE / "feed" / "kessler.json"
            if fp.is_file():
                body = fp.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Cache-Control", "public, max-age=300")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
        if path in ("/g2", "/g2/"):''',
)])

print("K7 wave-1 edits applied")
