"""kessler/briefing.py (A8/C4, session 32): compose a briefing DRAFT from the practice's own artifacts.

Sources, all local and dated: docs/log/releases.json (release/infra entries), the two machine
registers (windows), and the honeypot export (own-run vs external, via threatindex). Nothing
here invents a trend: a section with no data says so, in one line. The output is a DRAFT - a
human edits before anything ships anywhere.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import date
from pathlib import Path


def _clean(s: str) -> str:
    return str(s).replace("\u2014", " - ").strip()


def _releases(root: Path, since: str, until: str) -> list[tuple[str, str, str]]:
    p = root / "docs" / "log" / "releases.json"
    if not p.exists():
        return []
    out = []
    for e in json.loads(p.read_text(encoding="utf-8")).get("entries", []):
        if since <= str(e.get("date", "")) <= until:
            out.append((str(e["date"]), _clean(e.get("title", "")), _clean(e.get("blurb", ""))))
    return sorted(out, reverse=True)


def _register_summary(root: Path) -> list[str]:
    lines: list[str] = []
    from .baseline import N_FLOOR, load_registry
    from .bench import load_register
    bp = root / "baseline-registry.json"
    if bp.exists():
        reg = load_registry(bp)
        ents = reg.get("entries", [])
        powered = sum(1 for e in ents if int(e.get("n", 0)) >= N_FLOOR)
        lines.append(f"- baseline units: {len(ents)} registered, {powered} at or above the "
                     f"floor (n>={N_FLOOR}); floors and intervals print on every row.")
    else:
        lines.append("- baseline units: none registered yet (stated, not padded).")
    kp = root / "bench-register.json"
    if kp.exists():
        try:
            breg = load_register(kp)
        except (OSError, ValueError):
            breg = {"units": []}
        units = breg.get("units", [])
        kinds = sorted({str(u.get("target_kind", "?")) for u in units})
        lines.append(f"- open bench: {len(units)} unit(s) across "
                     f"{', '.join(kinds) if kinds else 'no kinds'}; "
                     "identical driver and oracle across units.")
    else:
        lines.append("- open bench: no units registered yet.")
    return lines


def _honeypot_summary(root: Path) -> list[str]:
    try:
        from . import threatindex
        files = (sorted(root.glob("run-threatindex/export-all-*.jsonl"))
                 or sorted(root.glob("run-threatindex/export-*.jsonl")))
        if not files:
            return ["- no honeypot export present; nothing to read (stated)."]
        rows = []
        for ln in files[-1].read_text(encoding="utf-8").splitlines():
            if ln.strip():
                rows.append(json.loads(ln))
        by_month: dict[str, list[dict]] = defaultdict(list)
        for r in rows:
            try:
                text = (json.loads(r.get("request", "{}")).get("messages", [{}])[-1]
                        .get("content", ""))
            except (json.JSONDecodeError, IndexError, TypeError):
                text = str(r.get("request", ""))
            at = str(r.get("at", ""))
            month = at[:7] if len(at) >= 7 and at[4] == "-" else "unlabelled"
            by_month[month].append({"request": text, "hit": bool(r.get("hit"))})
        index = threatindex.build_index(sorted(by_month.items()),
                                        generated=date.today().isoformat(),
                                        own=threatindex.own_payload_set())
        m = index["months"][-1] if index["months"] else None
        if not m:
            return ["- index present but empty (stated)."]
        own_n = m.get("own_run", 0)
        total = m["total"]
        if total["n"] == 0 and own_n:
            return [f"- {m['month']}: external attempts ZERO; {own_n} own-run captures were "
                    "classified out of every cell by payload (self-referential rates are the "
                    "theatre this index refuses)."]
        return [f"- {m['month']}: {total['n']} external attempt(s), {total['hits']} hit(s); "
                f"cells below n>=400 stay directional."]
    except Exception as exc:  # noqa: BLE001 - the briefing must never fabricate
        return [f"- honeypot index unreadable this run ({type(exc).__name__}); stated, not guessed."]


def compose(since: str, until: str | None = None, root: Path | None = None) -> str:
    """Compose the draft. Deterministic for fixed (since, until, root)."""
    root = root or Path(__file__).resolve().parent.parent
    until = until or date.today().isoformat()
    if not (len(since) == 10 and since[4] == "-") or not (len(until) == 10 and until[4] == "-"):
        raise ValueError("since/until must be YYYY-MM-DD")
    if since > until:
        raise ValueError("since is after until")

    lines = [
        f"# Briefing draft - {since} to {until}",
        "",
        "*DRAFT: generated from the practice's own artifacts (releases log, registers, honeypot "
        "index). A human edits and signs off before anything ships anywhere.*",
        "",
        "## What shipped in the window",
        "",
    ]
    shipped = _releases(root, since, until)
    if shipped:
        for d, t, b in shipped:
            lines.append(f"- **{d}** - {t}" + (f". {b}" if b else ""))
    else:
        lines.append("- nothing in the releases log inside the window (stated, not padded).")

    lines += ["", "## The measurement estate right now", ""]
    lines += _register_summary(root)
    lines += ["", "## Honeypot index status", ""]
    lines += _honeypot_summary(root)
    lines += ["", "## Standing notes", "",
              "- every rate is a Wilson-95 interval over counted attempts; empty cells stay "
              "stated; nothing here is a certification.",
              "- coverage decisions (tested / excluded / unsupported) are part of the record, "
              "not an appendix.", ""]
    text = "\n".join(lines)
    if "\u2014" in text:
        raise ValueError("em dash in briefing output")
    return text
