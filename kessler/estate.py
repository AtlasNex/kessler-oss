"""Estate rollup + run cost/power meter (PLAN-v5 #21) — multi-agent R2 hours, honest quoting.

Two small things that gate real sales:

1. **Per-target rollup** (`rollup`). A live run mixes targets in one denominator; an estate
   report needs each target measured separately (the Standing Attestation tenant, and the
   R2 "multi-agent estate" claim, both key on it). The join is again the `adapter_ref`
   (`runner:{unit}:{target}` — the target id is the last colon field), so the rollup is a
   view over the SAME attempts, never a second measurement.

2. **Run cost/power meter** (`estimate`). `kessler plan` prints a denominator; a client quote
   needs two more numbers: how long it will take and how much power (detection floor) that
   many units buys. Both come from measurements that already exist in the repo — the G2
   rehearsal's 2.57 s/scheduled-unit (own endpoint, 8 lanes; docs/G2-REHEARSAL.md §2.1) — so
   the projection carries its assumption in the same sentence as its figure, and a plan is
   never quoted without the meter. The per-unit constant is a MODULE default, overridable:
   a re-measured rehearsal updates one line, not a document hunt.
"""
from __future__ import annotations

from .asi import ALL_IDS
from .corpus import TestCase, achieved_power, census

#: Measured wall-clock per SCHEDULED unit at the G2 rehearsal's lane count (8), own endpoint.
#: Source: docs/G2-REHEARSAL.md §2.1 (427 units / 1,097.8 s = 2.57 s/unit). A CEILING for a
#: rate-limited single lane and an OPTIMISTIC number for a faster target — it is stated, not
#: hidden; the engagement's own rehearsal replaces it.
SECONDS_PER_UNIT = 2.57

#: Scheduled units = attempted + pending-review + unreached (lesson 15/V-21: the denominator
#: for a per-X figure is what X actually is). This constant is that set, per target.
def scheduled_units(cases: list[TestCase], targets: list[dict], *, per_target: bool = True) -> int:
    """Planned scheduled-unit count. With --lanes L the WALL-CLOCK divides by lanes, but the
    denominator (units) does not change — the lane count only multiplies the request rate."""
    n = len(cases) * (len(targets) if per_target else 1)
    return n


def estimate(cases: list[TestCase], targets: list[dict], *, lanes: int = 8,
             seconds_per_unit: float = SECONDS_PER_UNIT) -> dict:
    """Project wall-clock and coverage for a planned run. Every figure names its assumption."""
    units = scheduled_units(cases, targets)
    wall = units * seconds_per_unit / max(1, lanes)
    power = achieved_power(cases)
    cen = census(cases)
    hours = wall / 3600.0
    return {
        "units": units,
        "cases": len(cases),
        "targets": len(targets),
        "lanes": max(1, lanes),
        "seconds_per_unit": seconds_per_unit,
        "projected_wall_seconds": wall,
        "projected_wall_hours": hours,
        "assumption": f"wall-clock = units x {seconds_per_unit} s / {max(1, lanes)} lanes; "
                      f"{seconds_per_unit} s/unit is the measured G2 rehearsal figure "
                      "(own endpoint, 8 lanes, docs/G2-REHEARSAL.md §2.1) — a ceiling when the "
                      "target rate-limits, optimistic when it is faster",
        "per_category_upper_at_zero": power,   # the detection floor (F-6b): what a zero-hit
                                               # run at this n still cannot exclude
        "corpus_total": cen["total"],
        "empty_categories": cen["empty_categories"],
    }


def rollup(engagement) -> dict:
    """Per-target attempt rollup from the recorded adapter_ref suffix (`:{target_id}`)."""
    from .asi import compute_asr

    by_target: dict[str, list] = {}
    unattributed = 0
    for a in engagement.attempts:
        ref = a.adapter_ref
        tid = ref.rsplit(":", 1)[-1] if ref.startswith("runner:") and ":" in ref else ""
        if tid and any(t["id"] == tid for t in engagement.targets):
            by_target.setdefault(tid, []).append(a)
        else:
            unattributed += 1
    out = {"targets": {}, "unattributed": unattributed}
    for tid, group in by_target.items():
        asr = compute_asr(group)
        out["targets"][tid] = {
            "attempts": asr["__overall__"]["attempts"],
            "successes": asr["__overall__"]["successes"],
            "asr": asr["__overall__"]["asr"],
            "ci_low": asr["__overall__"]["ci_low"],
            "ci_high": asr["__overall__"]["ci_high"],
            "categories": [c for c in ALL_IDS if asr[c]["attempts"]],
        }
    return out


def render_estimate_md(est: dict) -> str:
    lines = [
        f"**Planned run:** {est['units']} scheduled unit(s) = {est['cases']} case(s) x "
        f"{est['targets']} target(s), at {est['lanes']} lane(s).",
        "",
        f"- **Projected wall-clock:** {est['projected_wall_hours']:.1f} h "
        f"({est['projected_wall_seconds']:.0f} s) — {est['assumption']}",
        f"- **Planned sample:** {est['cases']} case(s) drawn from the composed corpus",
    ]
    if est["empty_categories"]:
        lines.append(f"- **Empty categories (C-4 will REFUSE to emit):** "
                     f"{', '.join(est['empty_categories'])} — widen --sample or add "
                     f"--min-per-category")
    pc = est["per_category_upper_at_zero"]
    if pc:
        worst = max(pc.values(), key=lambda r: r["upper_at_zero"])
        lines.append(
            f"- **Detection floor:** the weakest category resolves to "
            f"{worst['upper_at_zero'] * 100:.0f}% at zero hits "
            f"(n={worst['n']}) — below that, 'held' means 'not detected', not 'safe'.")
    return "\n".join(lines)


def render_rollup_md(ru: dict) -> str:
    lines = [
        "| Target | Attempts | Successes | ASR | 95% interval | Categories tested |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for tid, row in sorted(ru["targets"].items()):
        ci = ("—" if row["ci_low"] is None
              else f"[{row['ci_low'] * 100:.1f}%, {row['ci_high'] * 100:.1f}%]")
        lines.append(f"| `{tid}` | {row['attempts']} | {row['successes']} | "
                     f"{row['asr'] * 100:.1f}% | {ci} | {', '.join(row['categories']) or '—'} |")
    lines += [
        "",
        "Per-target rates are the estate's Standing-Attestation tenants (PLAN-v5 #12 keys on "
        "them); the overall engagement rate is the ASR table's, and the two denominators are "
        "never summed. "
        + (f"{ru['unattributed']} attempt(s) carried no target id and are excluded from this "
           "table (they remain in the overall ASR)." if ru["unattributed"] else
           "Every recorded attempt carries its target."),
    ]
    return "\n".join(lines)
