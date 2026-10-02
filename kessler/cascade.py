"""Cascade chain-search (PLAN-v5 #20, ASI08) — composing mild findings into demonstrated paths.

Why this exists
---------------
The literal Kessler syndrome: one collision cascading to destroy the whole band. Individually
mild findings that COMPOSE into a serious outcome are the highest-value story in a report —
and until now the chain narrative was hand-written from what the tester happened to notice.
This searches the reach graph the blast engine already builds and enumerates which
credential/tool handoffs actually connect, so the chain is found, not remembered.

What it does (and honestly does not)
------------------------------------
1. **Graph walk over declared reach.** Nodes are targets. An edge exists where either:
   (a) two targets share a resource (co-reach: compromise A, be positioned on B), or
   (b) A reaches `tool:X`/`api:X` naming another target B (the invocation edge).
   Chains are simple paths with >= 2 edges (a 1-edge co-reach is a chokepoint, which
   `blast.py` already reports; the search's value is second-order reach — A→B→C).
2. **Yield-ordered ranking.** A chain's rank is the worst YIELD its hops grant (credential
   theft > data > store > API > tool > network > model, from `blast.KIND_YIELD`), tie-broken
   by crown-jewel touch, then length. A rank, never a measurement: no ASR is claimed (C-5).
3. **Findings attachment is a text join, stated as such.** A chain is "supported by reported
   findings" when every hop's resource key appears in the finding corpus (evidence /
   reproduction / threat-scenario text). Support is not demonstration — an unattempted path
   renders `candidate — not demonstrated` and stays that way until a run scores it.
4. **The demonstration unit is the whole chain** (mirrors lesson 16: one attempt per
   sequence; lesson 17: verdict-bearing reply first in the evidence).

Deterministic: sorted everywhere; the same graph yields the same chain list in the same order.
C-2 stdlib only.

Ponytail ceilings, stated: `MAX_DEPTH` edges and `MAX_CHAINS_PER_SOURCE` keep enumeration
finite on dense graphs, and the cap is REPORTED when tripped (a silent cap is a silent lie).
The upgrade path is k-shortest-paths search, not a solver dependency.
"""
from __future__ import annotations

from .blast import compute_blast_radius

#: Search depth cap in EDGES. Six hops is beyond any published agentic cascade incident
#: (the OpenAI swarm incident's documented path was three meaningful hops).
MAX_DEPTH = 6

#: Ceiling on chains enumerated per source node (dense reach graphs explode
#: combinatorially). When tripped the source lands in `cap_sources` and the render says so.
MAX_CHAINS_PER_SOURCE = 200


def build_edges(targets: list[dict]) -> dict[str, list[dict]]:
    """src -> sorted edge dicts {to, resource, crown_jewel, via}.

    `via` names the edge kind (`coreach` / `invocation`) so the render can say WHY a hop
    exists — a chain whose hops are invocation-name matches is weaker evidence than a
    shared-credential chain, and the reader should see which is which.
    """
    by_id = {t["id"]: t for t in targets}
    holders: dict[str, list[str]] = {}
    crown_of: dict[str, bool] = {}
    for t in targets:
        for entry in t.get("reaches") or []:
            res = entry.rstrip("!")
            holders.setdefault(res, [])
            if t["id"] not in holders[res]:
                holders[res].append(t["id"])
            crown_of[res] = crown_of.get(res, False) or entry.endswith("!")

    edges: dict[str, list[dict]] = {tid: [] for tid in by_id}
    for res, hs in holders.items():
        # (a) co-reach: every holder positioned on every other holder
        for s in hs:
            for d in hs:
                if s != d:
                    edges[s].append({"to": d, "resource": res,
                                     "crown_jewel": crown_of[res], "via": "coreach"})
        # (b) invocation: tool:X / api:X where X names another target
        if res.split(":", 1)[0] in ("tool", "api"):
            name = res.split(":", 1)[-1].lower()
            norm = lambda x: x.lower().replace("_", "-")  # noqa: E731
            for d in by_id:
                if norm(d) == norm(name) and d not in hs:
                    for s in hs:
                        edges[s].append({"to": d, "resource": res,
                                         "crown_jewel": crown_of[res], "via": "invocation"})
    for src in edges:
        seen: set[tuple] = set()
        uniq = []
        for e in sorted(edges[src], key=lambda e: (e["to"], e["resource"], e["via"])):
            key = (e["to"], e["resource"], e["via"])
            if key not in seen:
                seen.add(key)
                uniq.append(e)
        edges[src] = uniq
    return edges


def _worst_yield(br_keys: dict, res_keys: list[str]) -> tuple[int, str]:
    rank, label = 99, "unclassified"
    for k in res_keys:
        r = br_keys.get(k)
        if r and r.yield_rank < rank:
            rank, label = r.yield_rank, r.yield_label
    return rank, label


def search_chains(targets: list[dict], *, max_depth: int = MAX_DEPTH) -> dict:
    """Enumerate cascade chains (simple paths, 2..max_depth edges) over the reach graph."""
    br = compute_blast_radius(targets)
    br_keys = {r.key: r for r in br.union}
    edges = build_edges(targets)
    chains: list[dict] = []
    capped: set[str] = set()

    def walk(src: str, node: str, path: list[str], res_keys: list[str],
             crowns: list[bool], vias: list[str]) -> None:
        if len(path) >= 3:  # >= 2 edges: second-order reach, the cascade story
            rank, label = _worst_yield(br_keys, res_keys)
            chains.append({
                "source": src,
                "path": " → ".join(path),
                "hops": len(path) - 1,
                "resources": list(res_keys),
                "vias": list(vias),
                "worst_yield": label,
                "worst_yield_rank": rank,
                "crown_jewel": any(crowns),
            })
        if len(path) - 1 >= max_depth:
            return
        if sum(1 for c in chains if c["source"] == src) >= MAX_CHAINS_PER_SOURCE:
            capped.add(src)
            return
        for e in edges.get(node, []):
            if e["to"] in path:
                continue
            walk(src, e["to"], path + [e["to"]], res_keys + [e["resource"]],
                 crowns + [e["crown_jewel"]], vias + [e["via"]])

    for src in sorted(edges):
        walk(src, src, [src], [], [], [])
    chains.sort(key=lambda c: (c["worst_yield_rank"], not c["crown_jewel"], c["hops"],
                               c["path"]))
    return {
        "chains": chains,
        "cap_sources": sorted(capped),
        "max_depth": max_depth,
        "nodes": len(edges),
        "edges": {s: len(es) for s, es in sorted(edges.items())},
    }


def attach_findings(report: dict, findings) -> dict:
    """Mark chains supported by the finding corpus. TEXT JOIN, stated in the render: every
    hop's resource key named somewhere in findings' evidence/reproduction/threat-scenario."""
    blob = " ".join((f.evidence + " " + f.reproduction + " " + f.threat_scenario)
                    for f in findings).lower()
    for c in report["chains"]:
        c["supported_by_findings"] = all(k.lower() in blob for k in c["resources"])
    return report


def render_cascade_md(report: dict, *, top: int = 12) -> str:
    """The chain-search table. Every row carries its honest status: searched != attacked."""
    chains = report["chains"]
    lines = [
        f"**Cascade chain-search:** {len(chains)} candidate path(s) of 2-{report['max_depth']} "
        f"hop(s) enumerated over {report['nodes']} estate node(s); top "
        f"{min(top, len(chains)) if chains else 0} by worst-yield shown. **No attack-success "
        "rate is claimed for any row** — these are paths to ATTEMPT, and a demonstration is "
        "one attempt per composed chain with the full hop sequence in the technique name.",
        "",
    ]
    if report["cap_sources"]:
        lines.append(
            f"**Enumeration cap tripped** for: {', '.join(report['cap_sources'])} — the "
            f"ranking covers the worst-yield paths from those sources up to "
            f"{MAX_CHAINS_PER_SOURCE} each, not all paths. Stated, not silent.\n"
        )
    if not chains:
        lines.append(
            "No multi-hop cascade path exists in the declared inventory (no shared resource "
            "or invocation edge chains two hops). Single-hop shared resources are the "
            "chokepoints in the blast-radius section. Both statements are about the "
            "INVENTORY, not a guarantee about the estate."
        )
        return "\n".join(lines)
    lines += [
        "| # | Path | Hops | Worst yield granted | Crown jewel | Support | Status |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for i, c in enumerate(chains[:top], 1):
        support = "findings name every hop" if c.get("supported_by_findings") else "—"
        lines.append(f"| {i} | `{c['path']}` | {c['hops']} | {c['worst_yield']} | "
                     f"{'yes' if c['crown_jewel'] else '—'} | {support} | "
                     f"candidate — not demonstrated |")
    lines += [
        "",
        "Sorted worst-yield first (credential theft > direct data > data-store > API > tool "
        "> network > model). Hop kinds are in the JSON (`kessler cascade --json`): a co-reach "
        "hop is a shared failure domain; an invocation hop is a declared call path. Attempt "
        "the supported rows first: they are the chains the test material already touches.",
    ]
    return "\n".join(lines)
