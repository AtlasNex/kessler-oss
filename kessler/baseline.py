"""Baseline #001 and the public-baseline comparator (PLAN-v5 #15, Wave 2; Open Bench seed).

Why this exists
---------------
The cheapest felt-value upgrade: every report can print "you at X% [a, b] against the public
baseline Y% [c, d] — same corpus, same method". No Y/N vendor can honestly print that column.
The registry is a committed JSON of intervalled entries; each entry is one measured unit with
its provenance (which run produced it, which corpus, which method).

The N-floor discipline (preregistered, from the plan's section 2.3)
--------------------------------------------------------------------
A baseline cell publishes ONLY at n >= 400 automated-oracle attempts (~±3pp at 5-10% rates).
Below the floor a cell prints "not yet powered (n=X)" and publishes no rate — an underpowered
baseline is exactly the false precision the whole practice exists to refuse. A cell also never
publishes across corpus versions: a comparator against different test material is not a
comparison, it is theatre — refused, not rounded.
"""
from __future__ import annotations

import json
from pathlib import Path

from .asi import ALL_IDS, compute_asr, wilson_interval

BASELINE_SCHEMA = "kessler/baseline-registry/v1"

#: Preregistered floor (PLAN-v5 section 2.3): publish a cell only at this n or above.
N_FLOOR = 400

#: Registry top-level keys. Closed world.
REGISTRY_KEYS: tuple[str, ...] = ("schema", "entries")

#: Entry keys. Closed world. `n`/`successes` are the overall unit's counts; `per_category`
#: carries {asi_id: {attempts, successes}} for the categories that were actually attempted.
ENTRY_KEYS: tuple[str, ...] = (
    "ref", "source", "window", "method", "corpus_hash", "scope_sha256",
    "n", "successes", "asr", "ci_low", "ci_high", "per_category",
)

#: The method string that marks a cell as automatable-oracle-measured. A manual-method entry
#: (human-scored) never feeds an automated comparator — different oracles, different rates.
AUTO_METHOD = "automated-oracle"


def baseline_entry(ref: str, source: str, window: str, method: str,
                   corpus_hash: str, scope_sha256: str, attempts) -> dict:
    """One baseline entry computed from an attempt list. Every number from compute_asr."""
    if not attempts:
        raise ValueError("a baseline entry from zero attempts would publish a null as a rate")
    if method not in (AUTO_METHOD, "manual", "mixed"):
        raise ValueError(f"unknown method {method!r}; expected automated-oracle / manual / mixed")
    asr = compute_asr(attempts)
    overall = asr["__overall__"]
    per_category = {
        cid: {"attempts": int(row["attempts"]), "successes": int(row["successes"])}
        for cid, row in asr.items()
        if cid != "__overall__" and row["attempts"]
    }
    return {
        "ref": ref,
        "source": source,
        "window": window,
        "method": method,
        "corpus_hash": corpus_hash,
        "scope_sha256": scope_sha256,
        "n": int(overall["attempts"]),
        "successes": int(overall["successes"]),
        "asr": overall["asr"],
        "ci_low": overall["ci_low"],
        "ci_high": overall["ci_high"],
        "per_category": per_category,
    }


def load_registry(path) -> dict:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != set(REGISTRY_KEYS):
        raise ValueError(f"registry must be exactly {', '.join(REGISTRY_KEYS)}")
    if raw["schema"] != BASELINE_SCHEMA:
        raise ValueError(f"registry schema {raw['schema']!r} != {BASELINE_SCHEMA!r}")
    for i, e in enumerate(raw["entries"]):
        if not isinstance(e, dict) or set(e) != set(ENTRY_KEYS):
            raise ValueError(f"registry entry {i} does not match the closed-world entry keys")
        if e["successes"] > e["n"]:
            raise ValueError(f"registry entry {i}: successes exceed n")
    return raw


def save_registry(registry: dict, path) -> None:
    Path(path).write_text(json.dumps(registry, indent=2, ensure_ascii=False) + "\n",
                          encoding="utf-8")


def powered(entries: list[dict], *, cell_floor: int = N_FLOOR) -> list[dict]:
    """Entries allowed to feed the comparator: automated-oracle method, unit n >= the floor.
    (Per-CELL publication — where a cell's own n is below the floor, `comparator_rows` prints
    'not yet powered (cell n=X)' rather than the rate; the unit gate here just keeps clearly
    underpowered runs out of the lookup entirely.)"""
    return [e for e in entries if e["method"] == AUTO_METHOD and e["n"] >= cell_floor]


def render_registry_md(registry: dict) -> str:
    """The human table for the register page. Under-floor cells say so, never a bare rate."""
    lines = [
        "| Baseline unit | Method | n | ASR | 95% interval | Status |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for e in registry["entries"]:
        if e["method"] == AUTO_METHOD and e["n"] >= N_FLOOR:
            rate = f"{e['asr'] * 100:.1f}%"
            ci = f"[{e['ci_low'] * 100:.1f}%, {e['ci_high'] * 100:.1f}%]"
            status = ("published" if e["asr"]
                      else f"published; 0 observed in n={e['n']} attempts")
        else:
            rate = "—"
            ci = "—"
            status = (f"not yet powered (n={e['n']} < {N_FLOOR})"
                      if e["method"] == AUTO_METHOD else f"method: {e['method']} (not comparable)")
        lines.append(f"| {e['ref']} ({e['source']}, {e['window']}) | {e['method']} | "
                     f"{e['n']} | {rate} | {ci} | {status} |")
    lines += [
        "",
        f"A cell publishes only at n >= {N_FLOOR} automated-oracle attempts (preregistered; "
        "~±3pp at 5-10% rates). Below the floor the row says so and publishes nothing — an "
        "underpowered number is the false precision this practice exists to refuse.",
    ]
    return "\n".join(lines)


def comparator_rows(engagement, registry: dict, corpus_hash: str) -> list[dict]:
    """Per-category comparator rows for the client report.

    A category is comparable when a POWERED baseline entry measured the SAME CORPUS hash AND
    carries attempts in that category. The pin is the corpus, not the scope: a client run and a
    lab baseline share test material, never a scope document (the client's scope hash is the
    client's own — keying on it would make every comparator row unmatchable theatre).
    Returns dicts of {category, baseline_ref, n, asr, ci_low, ci_high} — or, in the same list
    shape, {category, unavailable: reason} for honest unavailability.
    """
    usable = [e for e in powered(registry["entries"]) if e["corpus_hash"] == corpus_hash]
    # Supersession convention (C-9): a corrected unit registers under a NEW monotonic ref
    # (BASE-X-002 supersedes BASE-X-001) and the old row stays as history. When several
    # powered units pin the same corpus, the comparator uses the HIGHEST ref — the newest
    # adjudication — never an arbitrary first row.
    rows: list[dict] = []
    asr = compute_asr(engagement.attempts)
    for cid in ALL_IDS:
        if not asr[cid]["attempts"]:
            continue  # the client run did not attempt it — nothing to compare
        your = {"your_attempts": int(asr[cid]["attempts"]),
                "your_successes": int(asr[cid]["successes"]),
                "your_asr": asr[cid]["asr"]}
        if not usable:
            rows.append({"category": cid, **your,
                         "unavailable": "no powered baseline entry on this corpus version yet"})
            continue
        # newest superseding ref FIRST for this category (a -002 unit that carries the cell
        # outranks the -001 it corrected; a -002 without the cell does not mask -001).
        # The register is sorted ascending, so scan in reverse.
        e = next((x for x in reversed(usable) if x["per_category"].get(cid)), usable[0])
        cell = e["per_category"].get(cid)
        if not cell or not cell["attempts"]:
            rows.append({"category": cid, **your,
                         "unavailable": f"baseline {e['ref']} holds no attempts in {cid}"})
            continue
        if cell["attempts"] < N_FLOOR:
            # The preregistered floor is PER CELL (plan §2.3): ±3pp at 5-10% rates is the
            # smallest honest column; below it the cell publishes nothing but its own n.
            rows.append({"category": cid, **your,
                         "unavailable": f"not yet powered (cell n={cell['attempts']} < "
                                        f"{N_FLOOR})"})
            continue
        ci = wilson_interval(cell["successes"], cell["attempts"])
        rows.append({
            "category": cid, "baseline_ref": e["ref"], "n": cell["attempts"],
            "successes": cell["successes"], "asr": cell["successes"] / cell["attempts"],
            "ci_low": ci[0] if ci else None, "ci_high": ci[1] if ci else None,
            **your,
        })
    return rows


def corpus_pin(engagement) -> str:
    """The engagement's corpus version pin: the engagement document does not carry one
    (schema v1), so the comparator keys on the scope hash — the signed scope is what bound
    the run. Renamed from corpus_hash deliberately: this is the SCOPE pin until schema v2
    adds a corpus field (never silently widened)."""
    return engagement.scope_sha256


def render_comparator_md(rows: list[dict]) -> str:
    """The report section. Honest about every gap; never prints a Y/N read of the gap."""
    if not rows:
        return ("No baseline comparison: no categories were attempted, so there is nothing to "
                "place against the public baseline.")
    lines = [
        "| ASI category | Your run | Public baseline | Baseline interval | Baseline unit / why not |",
        "| --- | --- | --- | --- | --- |",
    ]
    for r in rows:
        you = (f"{r['your_successes']}/{r['your_attempts']} = {r['your_asr'] * 100:.1f}%"
               if "your_attempts" in r else "—")
        if "unavailable" in r:
            lines.append(f"| {r['category']} | {you} | — | — | {r['unavailable']} |")
            continue
        lines.append(
            f"| {r['category']} | {you} | {r['asr'] * 100:.1f}% | "
            f"[{r['ci_low'] * 100:.1f}%, {r['ci_high'] * 100:.1f}%] ({r['n']} attempts) | "
            f"{r['baseline_ref']} |"
        )
    lines += [
        "",
        "The baseline column is a published measurement over counted attempts with a 95% Wilson "
        "interval, from the register — never a pass/fail grade, and never read as one. Where it "
        "says *not comparable*, no powered measurement exists for that cell yet; a dash is the "
        "honest state, not a zero.",
    ]
    return "\n".join(lines)
