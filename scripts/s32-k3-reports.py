"""K3 edits to scripts/build-reports.py (asserted, atomic):
- og/twitter meta + __EXTRA_HEAD__ slot + kx.css v3 (HEAD)
- kx.js v3 script (FOOT)
- helpers: _slug_og, _anchorize, html_for (share bar + anchors + og replace)
- render()/build_index() routed through the helpers
- S-5: threat-index pages gain the explorer block + data island (built from the same
  captures the issue md came from; degrades to nothing on any failure).
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
p = ROOT / "scripts" / "build-reports.py"
t = p.read_text(encoding="utf-8")


def swap(old: str, new: str, n: int = 1) -> None:
    global t
    cnt = t.count(old)
    if cnt != n:
        raise SystemExit(f"ANCHOR FAIL ({cnt} != {n}): {old[:90]!r}")
    t = t.replace(old, new, n)


# E0: escape helper import
swap("import re\n", "import re\nfrom html import escape as _h_escape\n", 1)

# E1: og/twitter metas + extra-head slot (HEAD)
swap(
    '<meta name="description" content="Published work from Kessler by AtlasNex: adversarial '
    'testing for agentic AI.">\n',
    '<meta name="description" content="Published work from Kessler by AtlasNex: adversarial '
    'testing for agentic AI.">\n'
    '<meta property="og:site_name" content="Kessler by AtlasNex">\n'
    '<meta property="og:type" content="article">\n'
    '<meta property="og:title" content="{title}">\n'
    '<meta property="og:description" content="Published work from Kessler by AtlasNex: '
    'measured, dated, scoped - nothing here is a certification.">\n'
    '<meta property="og:image" content="https://kessler.atlasnex.com/og/__OG__.png">\n'
    '<meta name="kx:kind" content="__KIND__">\n'
    '<meta name="twitter:card" content="summary_large_image">\n'
    '__EXTRA_HEAD__\n',
)

# E2: kx.css v3
swap('<link rel="stylesheet" href="/kx.css?v=2">', '<link rel="stylesheet" href="/kx.css?v=3">')

# E3: kx.js v3 in FOOT
swap('</footer>\n</body>', '</footer>\n<script src="/kx.js?v=3" defer></script>\n</body>')

# E4: helpers (inserted before def no_em_dash)
HELPERS = '''

def _slug_og(out_rel: str) -> str:
    s = out_rel.replace("\\\\", "/")
    if s.endswith("/index.html"):
        s = s[: -len("/index.html")]
    elif s.endswith(".html"):
        s = s[: -len(".html")]
    if s == "index":
        s = "home"
    s = s.replace("/", "-").strip("-")
    return s or "home"


def _anchorize(body: str) -> str:
    """Stable ids on h2/h3 so ?section= links and citations point at real anchors."""
    def slug(text: str) -> str:
        s = re.sub(r"<[^>]+>", "", text).lower()
        s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
        return s[:60] or "section"

    def repl(m):
        return f\'<h{m.group(1)} id="{slug(m.group(2))}">{m.group(2)}</h{m.group(1)}>\'

    return re.sub(r"<h([23])>(.*?)</h\\1>", repl, body)


def html_for(title: str, body: str, *, og: str, kind: str = "",
             extra_head: str = "") -> str:
    """ONE writer for every PAGE-based surface: anchors, share bar, og meta fills."""
    body = _anchorize(body)
    share = (\'<div class="kx-share">\'
             \'<button type="button" class="kx-copy" data-copy-url>copy link</button>\'
             \'<button type="button" class="kx-copy" data-copy-cite data-title="\'
             + _h_escape(title, quote=True) + \'">copy citation</button></div>\')
    if body.rstrip().endswith("</article>"):
        body = body.rstrip()[: -len("</article>")] + share + "</article>"
    else:
        body = body + share
    html = PAGE.format(title=title, body=body)
    return (html.replace("__OG__", og)
                .replace("__KIND__", kind or "Published")
                .replace("__EXTRA_HEAD__", extra_head))


def _ti_explorer_block() -> str:
    """S-5: explorer + island for threat-index pages from the same capture exports the
    issue md was generated from. Any failure degrades to the plain md page."""
    try:
        import json as _json
        from collections import defaultdict as _dd

        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        from kessler import threatindex  # noqa: PLC0415
        from kessler.baseline import N_FLOOR  # noqa: PLC0415

        files = (sorted(ROOT.glob("run-threatindex/export-all-*.jsonl"))
                 or sorted(ROOT.glob("run-threatindex/export-*.jsonl")))
        if not files:
            return ""
        rows = []
        for ln in files[-1].read_text(encoding="utf-8").splitlines():
            if ln.strip():
                rows.append(_json.loads(ln))
        if not rows:
            return ""
        by_month: dict = _dd(list)
        for r in rows:
            try:
                text = (_json.loads(r.get("request", "{}")).get("messages", [{}])[-1]
                        .get("content", ""))
            except (_json.JSONDecodeError, IndexError, TypeError):
                text = str(r.get("request", ""))
            at = str(r.get("at", ""))
            month = at[:7] if len(at) >= 7 and at[4] == "-" else "unlabelled"
            by_month[month].append({"request": text, "hit": bool(r.get("hit"))})
        index = threatindex.build_index(
            sorted(by_month.items()),
            generated=f"captures through {max(by_month)}",
            own=threatindex.own_payload_set())
        island = _json.dumps(
            {k: index[k] for k in ("schema", "generated", "families", "months", "index_id")},
            sort_keys=True)
        fams = index["families"]
        m = index["months"][-1] if index["months"] else None
        options = "".join(f\'<option value="{f}">{f}</option>\' for f in fams)
        own_run = (m or {}).get("own_run", 0)
        cells = "".join(
            f\'<div class="kx-cell" data-family="{f}"><b>{f}</b>\'
            f\'<span class="kx-cell-n">{((m or {}).get("cells", {}).get(f) or {}).get("n", 0)} \'
            f\'attempts · {((m or {}).get("cells", {}).get(f) or {}).get("hits", 0)} hits</span>\'
            f\'<span class="kx-cell-state">{((m or {}).get("cells", {}).get(f) or {}).get("power", "no data")}</span></div>\'
            for f in fams)
        zero_note = ""
        if m and m["total"]["n"] == 0 and own_run:
            zero_note = (
                f\'<p class="kx-ti-zeroline">All <b>{own_run}</b> captures so far trace to our own \'
                f\'measurement traffic (classified by payload) and are excluded from every cell - \'
                f\'a rate on our own rehearsal would be self-referential theatre. The first \'
                f\'external attempts render as real cells; the denominators are honest from day \'
                f\'one, including the day they are zero.</p>\')
        return (\'\'\'
<section class="kx-explorer" data-explorer>
<h2 id="the-index-explorable">The index, explorable</h2>
<p class="ax-sub">Filter by attack family; cells fill as external traffic powers them up.
A cell below the preregistered N (\'\'\' + str(N_FLOOR) + \'\'\') stays directional and publishes no claim.</p>
\'\'\' + zero_note + \'\'\'
<div class="kx-toolbar" role="group" aria-label="Filter the index">
<label>family <select data-filter="family"><option value="">all</option>\'\'\'
                + options + \'\'\'</select></label>
<span class="kx-count" data-count aria-live="polite">\'\'\'
                + (f\'{m["month"] if m else "no month"} · {len(fams)} families\' if m else "no data")
                + \'\'\'</span>
</div>
<div class="kx-ti-wrap">\'\'\' + cells + \'\'\'</div>
<details class="kx-read"><summary>How to read a cell</summary>
<p>A cell counts attacker attempts against our own trap, with a 95% Wilson interval. Below
the floor no rate is shown: a small-n percentage is the false precision this index exists
to refuse. Zero external attempts is published as zero, never padded with our own traffic.</p>
</details>
</section>
<script type="application/json" id="kx-ti-data">\'\'\' + island + \'\'\'</script>\'\'\')
    except Exception as exc:  # noqa: BLE001 - never break the build over the extra
        print(f"note: TI explorer block skipped: {exc}")
        return ""

'''
swap("\n\ndef no_em_dash(text: str) -> str:", HELPERS + "\ndef no_em_dash(text: str) -> str:")

# E5: render() through html_for + TI block
swap(
    '    body = markdown.markdown(text, extensions=["tables", "fenced_code"])\n',
    '    body = markdown.markdown(text, extensions=["tables", "fenced_code"])\n'
    '    if "09-threat-index-" in page["src"]:\n'
    '        body += _ti_explorer_block()\n',
)
swap(
    '    html = PAGE.format(title=page["title"], body=body)\n',
    '    og = _slug_og(page.get("out") or page["slug"])\n'
    '    kind = f\'{page["kind"]} · {page["date"]}\' if page.get("kind") else ""\n'
    '    html = html_for(page["title"], body, og=og, kind=kind)\n',
)

# E6: index page fills its placeholders
swap(
    '    html = INDEX.format(title="Published work", cards=cards)\n',
    '    html = (INDEX.format(title="Published work", cards=cards)\n'
    '            .replace("__OG__", "reports").replace("__KIND__", "Archive")\n'
    '            .replace("__EXTRA_HEAD__", ""))\n',
)

p.write_text(t, encoding="utf-8", newline="")
print("build-reports.py: K3 edits applied", len(t), "bytes")
