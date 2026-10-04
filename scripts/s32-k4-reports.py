"""K4/S-10: the demo triage desk + packet navigator on the sample page (build-reports special
case, same pattern as the TI explorer). Rows come from the sealed SELFTEST-A7-001 engagement
document - real attempts, real evidence text; the desk itself writes nothing."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
p = ROOT / "scripts" / "build-reports.py"
t = p.read_text(encoding="utf-8")
if "_sample_desk_block" in t:
    raise SystemExit("already applied: build-reports carries the desk block")


def swap(old: str, new: str) -> None:
    global t
    cnt = t.count(old)
    if cnt != 1:
        raise SystemExit(f"ANCHOR FAIL ({cnt}): {old[:90]!r}")
    t = t.replace(old, new, 1)


DESK = '''

def _sample_nav_block() -> str:
    """S-10: the packet navigator - every artifact one hop from the sample page."""
    links = [
        ("report.md", "Report (Markdown)"), ("report.html", "Report (HTML)"),
        ("coverage.md", "Coverage"), ("coverage-heatmap.html", "Coverage heatmap"),
        ("board-summary.html", "Board summary"), ("remediation-log.html", "Remediation log"),
        ("attestation-letter.html", "Attestation letter"), ("aibom.json", "AIBOM"),
        ("../verify/", "Verify the capsule"),
    ]
    chips = " ".join(
        f'<a class="kx-copy" style="text-decoration:none" href="{href}">{label}</a>'
        for href, label in links)
    return (
        '<h2 id="the-packet-as-files">The packet, as files</h2>\\n'
        '<p class="ax-sub">Every artifact of this engagement, unredacted by choice. The page '
        'you are on is the index; these are the files an auditor would receive.</p>\\n'
        f'<div class="kx-toolbar" style="margin-bottom:26px">{chips}</div>\\n')


def _sample_desk_block() -> str:
    """S-10: read-only demo triage desk over the sealed self-test engagement. Any failure
    degrades to nothing (the page stays the report index)."""
    try:
        import json as _json
        doc = _json.loads((ROOT / "run-selftest" / "a7-engagement.json").read_text(encoding="utf-8"))
        attempts = doc.get("attempts", [])
        if not attempts:
            return ""
        hit = [a for a in attempts if a.get("succeeded")]
        held = [a for a in attempts if not a.get("succeeded")]
        picked = (hit[:1] + held[:5]) if hit else held[:6]
        rows = []
        for a in picked:
            rows.append({
                "ref": f'{a.get("technique", "?")}@{a.get("environment", "?")}',
                "category": a.get("category", ""),
                "technique": a.get("technique", ""),
                "payload": a.get("payload", "").replace("\\u2014", " - ")[:300],
                "reply": (a.get("observed", "") or "(no effect observed)").replace("\\u2014", " - ")[:300],
                "oracle": "automated success" if a.get("succeeded") else "defence held (automated oracle)",
            })
        island = _json.dumps({"expected": len(rows), "rows": rows}, ensure_ascii=False, sort_keys=True)
        if "</" in island:
            return ""
        cards = "".join(
            f'<article class="kx-desk-card" data-desk-row="{_h_escape(r["ref"], quote=True)}">'
            f'<div class="kx-desk-meta"><span class="kx-chip">{_h_escape(r["category"])}</span>'
            f'<span class="kx-chip">{_h_escape(r["technique"])}</span>'
            f'<span class="kx-chip kx-note">oracle: {_h_escape(r["oracle"])}</span></div>'
            f'<p class="kx-desk-payload"><b>payload:</b> {_h_escape(r["payload"])}</p>'
            f'<p class="kx-desk-reply"><b>reply observed:</b> {_h_escape(r["reply"])}</p>'
            f'<div class="kx-desk-verdicts" role="group" aria-label="verdict">'
            + "".join(
                f'<button type="button" data-desk-verdict="{v}" aria-pressed="false">{v}</button>'
                for v in ("hit", "refused", "unsure", "skip"))
            + "</div></article>"
            for r in rows)
        return (
            '<section class="kx-desk" data-desk>\\n'
            '<h2 id="demo-triage-desk">Demo triage desk: six real rows, no writes</h2>\\n'
            '<div class="kx-desk-banner"><b>This desk writes nothing.</b> The six rows below are '
            'real attempts from the sealed SELFTEST-A7-001 engagement (payloads and replies '
            'verbatim). Verdicts stay in your browser; the real workbench persists decisions to '
            'the decision store and its finish refuses while rows remain undecided.</div>\\n'
            + cards +
            '<div class="kx-desk-bar"><span class="kx-count" data-desk-count aria-live="polite">'
            '0 of 6 decided</span>'
            '<button type="button" class="ax-btn primary" data-desk-finish>finish (demo)</button></div>\\n'
            '<div class="kx-desk-summary" data-desk-summary hidden></div>\\n'
            '<script type="application/json" id="kx-desk-data">' + island + '</script>\\n'
            '</section>\\n')
    except Exception as exc:  # noqa: BLE001 - the extra never breaks the page
        print(f"note: sample desk block skipped: {exc}")
        return ""


'''

swap("\n\ndef no_em_dash(text: str) -> str:", DESK + "\ndef no_em_dash(text: str) -> str:")

swap(
    '    if "09-threat-index-" in page["src"]:\n'
    '        body += _ti_explorer_block()\n',
    '    if "09-threat-index-" in page["src"]:\n'
    '        body += _ti_explorer_block()\n'
    '    if "08-sample-engagement" in page["src"]:\n'
    '        body += _sample_nav_block() + _sample_desk_block()\n',
)

p.write_text(t, encoding="utf-8", newline="")
print("build-reports.py: sample desk + nav installed")
