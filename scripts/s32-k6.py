"""K6 wave-1 edits (asserted, atomic): B7 white-label in ui.py; T-2 demo mode in review.py;
demo + briefing commands in cli.py."""
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


# ---------------------------------------------------------------- ui.py (B7)
BRAND = '''# --------------------------------------------------------------------------- white-label (B7)

#: White-label surface (B7): a resubmission under another practice's name renders reports
#: under that name. Deliberately tiny - a name, an optional logo (URL or data URI), an
#: optional amber override. The honesty surfaces (the voice guard, the honesty footers, the
#: evidence rules, the grammar of the number) are NOT brandable: a reseller may change the
#: name, never the grammar.
_BRAND: dict | None = None
_BRAND_ENV_READ = False


def set_brand(brand: dict | None) -> None:
    """Set (or clear) the white-label brand. Closed world; a broken brand fails loudly."""
    global _BRAND, _BRAND_ENV_READ
    _BRAND_ENV_READ = True
    if brand is None:
        _BRAND = None
        return
    if not isinstance(brand, dict):
        raise ValueError("brand must be an object")
    unknown = set(brand) - {"name", "logo", "amber"}
    if unknown:
        raise ValueError(f"unknown brand key(s): {', '.join(sorted(unknown))}")
    if not str(brand.get("name", "")).strip():
        raise ValueError("brand needs a non-empty name")
    amber = str(brand.get("amber", "")).strip()
    if amber and not re.fullmatch(r"#[0-9a-fA-F]{6}", amber):
        raise ValueError("brand amber must be a #rrggbb colour")
    _BRAND = {"name": str(brand["name"]).strip(),
              "logo": str(brand.get("logo", "")).strip(),
              "amber": amber}


def current_brand() -> dict | None:
    """The active brand; KESSLER_BRAND_JSON seeds it once per process."""
    global _BRAND_ENV_READ
    if not _BRAND_ENV_READ:
        import os
        raw = os.environ.get("KESSLER_BRAND_JSON", "")
        if raw:
            set_brand(json.loads(raw))
        else:
            _BRAND_ENV_READ = True
    return _BRAND


def masthead(title: str, meta_lines: list[str], command: str) -> str:'''

edit(ROOT / "kessler" / "ui.py", [(
    "def masthead(title: str, meta_lines: list[str], command: str) -> str:",
    BRAND,
), (
    """    return (
        '<header class="masthead">'
        f'<div class="prompt"><b>kessler</b> {command}</div>'""",
    """    b = current_brand() or {}
    _name = b.get("name", "kessler")
    _logo = (f'<img class="brand-logo" src="{_esc(b.get("logo"))}" alt="">'
             if b.get("logo") else "")
    return (
        '<header class="masthead">'
        f'<div class="prompt">{_logo}<b>{_esc(_name)}</b> {command}</div>'""",
), (
    """    css = CSS + (NEX_CSS if 'class="nex' in body else "")
    return (""",
    """    css = CSS + (NEX_CSS if 'class="nex' in body else "")
    _b = current_brand() or {}
    _brand_bits = ""
    if _b:
        if _b.get("logo"):
            _brand_bits += ".brand-logo{height:1em;vertical-align:-0.15em;margin-right:.35em}"
        if _b.get("amber"):
            _brand_bits += f":root{{--amber:{_b['amber']};--amber2:{_b['amber']}}}"
    return (""",
), (
    'f"<style>{css}</style>{head_extra}</head>"',
    'f"<style>{css}{_brand_bits}</style>{head_extra}</head>"',
)])

# ---------------------------------------------------------------- review.py (T-2)
edit(ROOT / "kessler" / "review.py", [(
    """    store_path = None
    expected = 0
    document_name = ""
""",
    """    store_path = None
    expected = 0
    document_name = ""
    demo = False
    tips = False
""",
), (
    """        path = urlparse(self.path).path
        try:
            if path == "/api/verdict":
""",
    """        path = urlparse(self.path).path
        if self.demo and path in ("/api/verdict", "/api/finish"):
            # T-2: the demo desk writes NOTHING. The response keeps the UI honest: the same
            # shape the real endpoint would return, plus wrote=false.
            self._send(200, _JSON_CT, json.dumps(
                {"demo": True, "wrote": False,
                 "note": "demo mode: this desk writes nothing; the real workbench persists "
                         "verdicts to <doc>-human-review.json"}).encode("utf-8"))
            return
        try:
            if path == "/api/verdict":
""",
), (
    """def _workbench_html(engagement: str, rows: dict, token: str, reviewer: str,
                    decided: int, expected: int, document_name: str = "") -> str:
    scored = "".join(_row_card(r) for r in rows["scored"])""",
    """def _workbench_html(engagement: str, rows: dict, token: str, reviewer: str,
                    decided: int, expected: int, document_name: str = "",
                    demo: bool = False, tips: bool = False) -> str:
    scored = "".join(_row_card(r) for r in rows["scored"])
    demo_head = ""
    if demo:
        tipset = ("read the rationale first, then the reply, then decide; keys 1-4 cast "
                  "verdicts; o opens a row; the clock measures the read."
                  if tips else "verdicts here change nothing anywhere.")
        demo_head = ("<div class='demo-banner'><b>DEMO - this desk writes nothing.</b> "
                     "Every button works; no file is written. Tour: " + tipset + "</div>")""",
), (
    """    body = (
        masthead(f"review · {_esc(engagement)}",""",
    """    body = (
        demo_head,
        masthead(f"review · {_esc(engagement)}",""",
), (
    """        "<p class='kbd-hint'>verdicts write "
        "<code>&lt;doc&gt;-human-review.json</code> beside the document; nothing here touches "
        "the engagement file or the sidecar.</p>",""",
    """        ("<p class='kbd-hint'>DEMO: verdicts write nothing; the real workbench writes "
         "<code>&lt;doc&gt;-human-review.json</code> beside the document (never the engagement "
         "file or the sidecar).</p>" if demo else
         "<p class='kbd-hint'>verdicts write "
         "<code>&lt;doc&gt;-human-review.json</code> beside the document; nothing here touches "
         "the engagement file or the sidecar.</p>"),""",
), (
    """                ".scored-zone { margin-top: 2.5rem; } .scored-zone > summary { font-size: .9rem; }"
                "h2 .n { color: var(--muted); font-weight: 400; }</style>",""",
    """                ".scored-zone { margin-top: 2.5rem; } .scored-zone > summary { font-size: .9rem; }"
                "h2 .n { color: var(--muted); font-weight: 400; }"
                ".demo-banner { border: 1px solid var(--amber); border-radius: var(--radius);"
                " background: var(--amber-dim); padding: .7rem .9rem; margin-bottom: 1.2rem;"
                " font-family: var(--mono); font-size: .82rem; }</style>",""",
), (
    """            page = _workbench_html(self.engagement, self.rows, self.token, self.reviewer,
                                   self._decided(), self.expected, self.document_name)""",
    """            page = _workbench_html(self.engagement, self.rows, self.token, self.reviewer,
                                   self._decided(), self.expected, self.document_name,
                                   self.demo, self.tips)""",
), (
    'def serve(document: Path, port: int = 8643, reviewer: str = "", open_browser: bool = True) -> None:',
    'def serve(document: Path, port: int = 8643, reviewer: str = "", open_browser: bool = True,\n'
    '          demo: bool = False, tips: bool = False) -> None:',
), (
    """        "expected": expected,
        "document_name": document.name,
    })""",
    """        "expected": expected,
        "document_name": document.name,
        "demo": demo,
        "tips": tips,
    })""",
)])

# ---------------------------------------------------------------- cli.py (T-2 + A8)
edit(ROOT / "kessler" / "cli.py", [(
    "def cmd_corpus(args) -> int:",
    '''def cmd_demo_review(args) -> int:
    """T-2: the read-only demo workbench over the sample engagement (writes nothing)."""
    from .review import serve
    doc = Path(args.document) if args.document else (
        Path(__file__).resolve().parent.parent / "run-selftest" / "a7-engagement.json")
    if not doc.exists():
        print(f"REFUSED: sample engagement not found: {doc}", file=sys.stderr)
        return 2
    print("demo mode: verdicts write NOTHING; tour tips on")
    serve(doc, port=args.port, reviewer=args.tester or "demo visitor",
          open_browser=not args.no_browser, demo=True, tips=True)
    return 0


def cmd_briefing(args) -> int:
    """A8/C4: compose a briefing DRAFT from the practice's own artifacts (never sends)."""
    from . import briefing
    try:
        text = briefing.compose(since=args.since, until=args.until)
    except (OSError, ValueError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    out = Path(args.out) if args.out else Path("out") / f"briefing-{args.since}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(f"WROTE  {out}  ({len(text)} chars; DRAFT - a human reviews before anything ships)")
    return 0


def cmd_corpus(args) -> int:''',
), (
    """    sp.add_argument("--no-browser", action="store_true")
    sp.set_defaults(fn=cmd_review)
""",
    """    sp.add_argument("--no-browser", action="store_true")
    sp.set_defaults(fn=cmd_review)

    sp = sub.add_parser("demo", help="read-only demo surfaces (writes nothing)")
    dsp = sp.add_subparsers(dest="demo_cmd")
    dr = dsp.add_parser("review", help="boot the sample engagement in the review workbench, "
                                       "read-only, with tour tips (T-2)")
    dr.add_argument("--document", help="engagement JSON (default: the sealed A7 self-test)")
    dr.add_argument("--port", type=int, default=8643)
    dr.add_argument("--tester", dest="tester", default="", help="display name (recorded nowhere)")
    dr.add_argument("--no-browser", action="store_true")
    dr.set_defaults(fn=cmd_demo_review)

    sp = sub.add_parser("briefing", help="compose a briefing DRAFT from the practice's own "
                                         "artifacts (A8/C4; never sends)")
    sp.add_argument("--since", required=True, help="window start, YYYY-MM-DD")
    sp.add_argument("--until", help="window end (default: today)")
    sp.add_argument("--out", help="output path (default: out/briefing-<since>.md)")
    sp.set_defaults(fn=cmd_briefing)
""",
)])

print("K6 wave-1 kernel edits applied")
