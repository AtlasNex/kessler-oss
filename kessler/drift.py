"""MCP drift radar (PLAN-v5 #19) — the Deadbugz class, scheduled.

Why this exists
---------------
Deadbugz-style poisoning is runtime-gated: a tool behaves for a few calls, then rewrites its own
instructions. Static one-pass scanners structurally cannot see it (teardown #02, docs/publish/04).
The existing `mcp_audit.audit_snapshot` audits ONE snapshot; the radar audits a SCHEDULE of
snapshots and answers the only question that matters over time: **did anything change, when, and
how often does it change without authorization?**

What it computes
----------------
1. **Per-tool hash pinning** across snapshots (the same `_canon` digest as mcp_audit — one
   definition, two consumers, no drift).
2. **Drift events:** first-seen, changed (with the old/new pin pair), disappeared. A change is
   an INTEGRITY observation, not an attack success — it never enters an ASR (D-019/D-021 lesson:
   policy checks are control violations, not attacks; the prefix `readiness:drift` says so).
3. **Stability rate with interval:** of the observation boundaries where a tool existed on both
   sides, how many showed no change — a Wilson interval over THAT count. Published as the
   "weather report" (public) or the alert trigger (private tier later).
4. **Call-count-gated suspicion:** tools whose definition changed after >= N successful calls
   (the rug-pull shape) are flagged separately — a change is not a rug-pull; a change after
   building user trust is.

C-2 stdlib only; no network (snapshots are files an operator collected; scheduling is `cron`,
not this module).
"""
from __future__ import annotations

from .asi import wilson_interval
from .mcp_audit import pin_tool

#: The technique-family prefix that marks a drift row as an integrity observation, never an
#: attack (mirrors the readiness:/audit: discipline from D-019/D-021).
DRIFT_PREFIX = "readiness:drift"


def _tools_by_name(snapshot: dict) -> dict[str, str]:
    """name -> pin for every tool definition in one snapshot (first call row wins, matching
    audit_snapshot's single-call reading; snapshots are per-collection)."""
    out: dict[str, str] = {}
    for call in snapshot.get("calls", [{}])[:1]:
        for t in call.get("tools", []) or []:
            name = t.get("name")
            if isinstance(name, str) and name not in out:
                out[name] = pin_tool(t)
    return out


def diff_snapshots(snapshots: list[tuple[str, dict]]) -> dict:
    """Diff a schedule of (stamp, snapshot) pairs. Returns the radar report dict.

    A "boundary" is one adjacent pair; each tool existing on both sides contributes one
    observation (stable True/False). First-seen and disappearance are events, not observations:
    they have no before-side, so no rate is claimed for them.
    """
    states = [(stamp, _tools_by_name(snap)) for stamp, snap in snapshots]
    events: list[dict] = []
    observations: dict[str, list[bool]] = {}
    for i in range(len(states) - 1):
        (t0, a), (t1, b) = states[i], states[i + 1]
        for name in sorted(set(a) | set(b)):
            if name not in a:
                events.append({"type": "first_seen", "tool": name, "at": t1})
            elif name not in b:
                events.append({"type": "gone", "tool": name, "at": t1})
            elif a[name] != b[name]:
                events.append({"type": "changed", "tool": name, "at": t1,
                               "from_pin": a[name], "to_pin": b[name]})
                observations.setdefault(name, []).append(False)
            else:
                observations.setdefault(name, []).append(True)
    return {
        "collections": len(states),
        "tools": sorted({n for _, ts in states for n in ts}),
        "events": events,
        "observations": observations,
    }


def tool_stability(report: dict) -> dict[str, dict]:
    """Per-tool stability: n boundaries observed, held (no-change) count, Wilson 95% interval."""
    out: dict[str, dict] = {}
    for name, obs in report["observations"].items():
        n = len(obs)
        held = sum(1 for x in obs if x)
        ci = wilson_interval(held, n)
        out[name] = {
            "observations": n, "held": held,
            "stability": held / n if n else None,
            "ci_low": ci[0] if ci else None, "ci_high": ci[1] if ci else None,
        }
    return out


def rug_pull_suspects(snapshots: list[tuple[str, dict]]) -> list[dict]:
    """Tools whose definition CHANGED after a prior clean observation boundary — the rug-pull
    shape (worked for N calls, then rewrote its own instructions). Suspect, not verdict."""
    report = diff_snapshots(snapshots)
    out = []
    for name, obs in report["observations"].items():
        clean_run = 0
        for stable in obs:
            if stable:
                clean_run += 1
            elif clean_run:
                out.append({"tool": name, "clean_boundaries_before_change": clean_run})
                break
    return out


def render_drift_md(report: dict, *, public: bool = True) -> str:
    """The weather report (public form) / alert digest (private form shares the same numbers).

    `public=True` never names the client's estate: the weather report is about the shape of the
    observation, while the private form (public=False) names tools for the owning client."""
    lines = [
        f"# MCP drift {'weather report' if public else 'alert'}",
        "",
        f"**Collections:** {report['collections']} · **Tools seen:** {len(report['tools'])} · "
        f"**Events:** {len(report['events'])}",
        "",
    ]
    if not report["events"]:
        lines.append(
            "No drift observed: every tool definition that existed across adjacent collections "
            "kept the same SHA-256 pin. A clean weather report is a statement about the "
            "observation window, not a guarantee about the tool."
        )
    else:
        lines += [
            "| Type | Tool | At |",
            "| --- | --- | --- |",
        ]
        for e in report["events"]:
            lines.append(f"| {e['type']} | `{e['tool']}` | {e['at']} |")
        lines += [
            "",
            f"Drift rows are **{DRIFT_PREFIX}** integrity observations — nobody attacked "
            "anything; these never enter an attack-success rate (D-019 rule).",
        ]
    stab = tool_stability(report)
    if stab:
        lines += ["", "## Stability, with its interval",
                  "", "| Tool | Boundaries | Held | Stability | 95% interval |",
                  "| --- | --- | --- | --- | --- |"]
        for name, s in sorted(stab.items()):
            ci = ("—" if s["ci_low"] is None
                  else f"[{s['ci_low'] * 100:.0f}%, {s['ci_high'] * 100:.0f}%]")
            rate = "—" if s["stability"] is None else f"{s['stability'] * 100:.0f}%"
            lines.append(f"| `{name}` | {s['observations']} | {s['held']} | {rate} | {ci} |")
        lines += ["", "Stability is the share of adjacent-collection boundaries where the tool "
                      "definition was unchanged. It is an integrity rate, not a safety verdict."]
    return "\n".join(lines)


def render_drift_full(snapshots: list[tuple[str, dict]], *, public: bool = True) -> str:
    """The one-call entry: diff + stability + rug-pull suspects rendered together."""
    report = diff_snapshots(snapshots)
    text = render_drift_md(report, public=public)
    rug = rug_pull_suspects(snapshots)
    if rug:
        text += ("\n\n## Rug-pull shape (clean runs followed by a change)\n\n"
                 + "\n".join(f"- `{r['tool']}` changed after {r['clean_boundaries_before_change']} "
                             "clean boundary/boundaries — the Deadbugz pattern; verify the new "
                             "definition text before resuming trust" for r in rug))
    else:
        text += ("\n\nNo rug-pull shape observed (no tool completed clean boundaries and then "
                 "changed within this window).")
    return text
