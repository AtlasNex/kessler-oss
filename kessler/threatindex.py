"""Agentic Threat Index #001+ (PLAN-v5 #13) — the monthly public index from g2 captures.

What it is
----------
One number per month per technique FAMILY: of the attempts captured at our own honeypots
(traffic against an endpoint we own, so the corpus-inflow licence gate governs reuse of
PAYLOADS but the COUNTS are ours to publish), what share hit, with its Wilson interval, plus
the honest nulls: early traffic is bots and indexers, and that gets SAID, not smoothed.

Why it is an index and not a scoreboard of others
-------------------------------------------------
The publishable unit is the ATTACKER'S success against OUR estate, not any vendor's product.
We never name a scanning organisation, never rank a vendor, never treat a blocked attack as
proof a competitor works. The register's only ranking is family-vs-family within our own trap.

Rails (all enforced here):
* counts come from the capture rows; a row without a parsable family is bucketed `unclear`
  and PUBLISHED as such (never dropped — dropping rows is how denominators get slimmed);
* a family at n < N_FLOOR (400) prints "directional (n=X)" and NO rate claim (kill list 6:
  no index cell below its preregistered N; the floor travels with the baseline register's);
* disclosure hygiene per endpoint (plan #22 done-when): the data-handling statement and the
  bait-only-credentials note are part of the render, not a wiki page elsewhere;
* monthly cadence: a month with zero traffic renders an honest "no data" row, never a hole.
"""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict

from .asi import wilson_interval
from .baseline import N_FLOOR

INDEX_SCHEMA = "kessler/threat-index/v0"

#: Coarse family classification of a captured request. Ordered rules; first match wins; the
#: taxonomy is OURS (public), and every row shows which rule fired. A pattern list here must
#: stay small and readable — this is an index, not a WAF.
_FAMILY_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("secret-request", ("system prompt", "secret", "api key", "token", "password", "credential")),
    ("role-play/jailbreak", ("pretend", "developer mode", "dan", "jailbreak", "roleplay")),
    ("instruction-override", ("ignore previous", "ignore prior", "new instructions",
                              "disregard", "override")),
    ("exfiltration-probe", ("http", "url", "webhook", "post to", "send to", "curl")),
    ("memory-plant", ("remember this", "save to memory", "for future sessions", "note that")),
    ("recon", ("tools", "functions", "capabilities", "what can you do", "list your")),
)

DATA_HANDLING = (
    "The g2 honeypots are our own endpoints. We record request text, timestamp, instance, and "
    "whether the trap's canary leaked; no credentials of yours are ever present in a trap "
    "(all lure values are bait-only), and no client data touches them. Payloads captured here "
    "are corpus-inflow CANDIDATES reviewed against the licence gate before any reuse. Scanned "
    "IPs are not published, not sold, and used only for our own abuse control."
)


def family_of(request: str) -> str:
    low = request.lower()
    for fam, needles in _FAMILY_RULES:
        if any(n in low for n in needles):
            return fam
    return "unclear"


def build_index(months: list[tuple[str, list[dict]]], *, generated: str) -> dict:
    """months: [(YYYY-MM, rows)] where rows are capture dicts {request, hit(bool)}.

    Returns per-month per-family cells {n, hits, asr, ci, power} plus the month's honest
    totals. Families are the union over the whole index (a family absent this month renders
    a zero row, because an index with holes invites cherry-picking)."""
    fams = sorted({family_of(r["request"]) for _, rows in months for r in rows}
                  | {f for f, _ in _FAMILY_RULES})
    out = {"schema": INDEX_SCHEMA, "generated": generated, "families": fams, "months": []}
    for month, rows in months:
        by_fam: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        for r in rows:
            f = family_of(r["request"])
            by_fam[f][0] += 1
            by_fam[f][1] += 1 if r["hit"] else 0
        cells = {}
        for f in fams:
            n, hits = by_fam.get(f, [0, 0])
            ci = wilson_interval(hits, n) if n else (None, None)
            cells[f] = {"n": n, "hits": hits,
                        "asr": hits / n if n else None,
                        "ci_low": ci[0] if ci else None, "ci_high": ci[1] if ci else None,
                        "power": ("published" if n >= N_FLOOR
                                  else "directional (below preregistered N)" if n else "no data")}
        total_n = sum(c["n"] for c in cells.values())
        total_hits = sum(c["hits"] for c in cells.values())
        ci_t = wilson_interval(total_hits, total_n) if total_n else (None, None)
        out["months"].append({"month": month, "cells": cells,
                              "total": {"n": total_n, "hits": total_hits,
                                        "asr": total_hits / total_n if total_n else None,
                                        "ci_low": ci_t[0] if ci_t else None,
                                        "ci_high": ci_t[1] if ci_t else None}})
    out["index_id"] = hashlib.sha256(
        json.dumps(out["months"], sort_keys=True).encode()).hexdigest()[:12]
    return out


def render_index_md(index: dict, *, issue: int = 1) -> str:
    m = index["months"][-1] if index["months"] else None
    lines = [
        f"# Agentic Threat Index #{issue:03d}",
        "",
        f"Generated {index['generated']} from our own g2 honeypot captures "
        f"(id `{index['index_id']}`). Rates are attacker success against OUR trap, with 95% "
        "Wilson intervals; a cell below the preregistered N (400) is marked directional and "
        "publishes no claim. Early traffic includes scanners and indexers — said, not "
        "smoothed. We do not name scanning organisations and we do not rank vendors.",
        "",
    ]
    if not m or not m["total"]["n"]:
        lines.append("**No captured attempts this period.** The index stays published empty "
                     "rather than padded: a hole in a time series is information.")
        return "\n".join(lines)
    lines += [
        f"## {m['month']}", "",
        "| Family | Attempts | Hits | Hit rate | 95% interval | Power |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for f in index["families"]:
        c = m["cells"][f]
        if not c["n"]:
            lines.append(f"| {f} | 0 | — | — | — | no data |")
            continue
        rate = f"{c['asr'] * 100:.1f}%" if c["power"] == "published" else "—"
        band = ("—" if c["ci_low"] is None
                else f"[{c['ci_low'] * 100:.1f}%, {c['ci_high'] * 100:.1f}%]")
        lines.append(f"| {f} | {c['n']} | {c['hits']} | {rate} | {band} | {c['power']} |")
    t = m["total"]
    band = (f"[{t['ci_low'] * 100:.1f}%, {t['ci_high'] * 100:.1f}%]"
            if t["ci_low"] is not None else "—")
    lines.append(f"| **all families** | **{t['n']}** | **{t['hits']}** | — | {band} | "
                 "total with interval |")
    lines += ["", "Where interval-only rows appear: the preregistered floor "
              f"(n>={N_FLOOR} per cell) has not been reached, and a small-n rate is the false "
              "precision this index exists to refuse. Repeated months power the cells up; the "
              "denominators are printed until they do.", "",
              "## Data-handling statement", "", DATA_HANDLING]
    return "\n".join(lines)
