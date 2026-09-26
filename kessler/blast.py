"""The blast-radius engine (BUILD B5) — quantifying what one compromised agent can reach.

Why this exists
---------------
OFFER.md promises a "blast-radius analysis: the union of every credential, tool and API each agent
can reach", and the report renders it. But a *render* of whatever the scope author typed is not an
analysis. This module computes one from the target inventory:

1. **Reachability graph.** Targets are nodes; a reach entry `kind:resource` (e.g. `api:email`,
   `cred:db_read`, `tool:ticket_update`, `store:vector_index`) is an edge from its holder.
2. **Per-agent reachable set** and the **estate union** — the union, not the intersection, is the
   blast radius (a defence that holds per agent can still fail as an estate).
3. **Cascade chokepoints (ASI08).** Any resource reachable from two or more agents is a shared
   failure domain: one compromised agent reaching it can poison what every other agent trusts.
   These are ranked first — the Kessler name is the pitch.
4. **Composition classification.** Every resource is classified (credential / api / tool / store /
   data / network / model) so the report can say what a compromise YIELDS (credentials > data >
   compute), not just count strings.
5. **Crown-jewel proximity.** Resources tagged `crown_jewel` in the scope (a scope file may tag
   reaches with `!` suffix, e.g. `cred:payments_api!`) are flagged wherever they appear.

Honesty rules, as everywhere: this is computed from the *declared* inventory. It is an analysis of
what the client TOLD us plus what testing VERIFIED — the report says which. Absence of a resource
from the inventory is not proof of absence (the same rule as C-1's complement).

C-2 stdlib-only. No graph library; the graphs here are small (an estate is tens of nodes) and a
dict-of-sets is the correct data structure at every scale this practice will see.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

#: Resource kinds recognised in reach entries (`<kind>:<name>[!]`).
RESOURCE_KINDS = ("cred", "api", "tool", "store", "data", "network", "model")

#: What a compromise of each kind yields, worst first — used to rank exposure, not to score it.
KIND_YIELD = {
    "cred": ("credential theft", 0),
    "data": ("direct data access", 1),
    "store": ("data-store access", 2),
    "api": ("authenticated API abuse", 3),
    "tool": ("tool abuse", 4),
    "network": ("network reach", 5),
    "model": ("model access / cost abuse", 6),
}

_REACH_RE = re.compile(r"^(?P<kind>[a-z_]+):(?P<name>[A-Za-z0-9_.\-/]+)(?P<crown>!)?$")


@dataclass(frozen=True)
class Resource:
    """One thing an agent can reach, parsed from its reach entry."""

    kind: str
    name: str
    crown_jewel: bool

    @property
    def key(self) -> str:
        return f"{self.kind}:{self.name}"

    @property
    def yield_rank(self) -> int:
        return KIND_YIELD.get(self.kind, (self.kind, 99))[1]

    @property
    def yield_label(self) -> str:
        return KIND_YIELD.get(self.kind, (self.kind, 99))[0]


@dataclass
class BlastRadius:
    """The computed blast radius of one estate."""

    per_agent: dict[str, list[Resource]] = field(default_factory=dict)
    union: list[Resource] = field(default_factory=list)
    chokepoints: list[dict] = field(default_factory=list)
    crown_jewels: list[str] = field(default_factory=list)
    unparseable: list[str] = field(default_factory=list)
    unclassified: list[str] = field(default_factory=list)

    @property
    def exposure_ranked(self) -> list[Resource]:
        """Union sorted worst-yield-first, crown jewels first among equals."""
        return sorted(self.union, key=lambda r: (not r.crown_jewel, r.yield_rank, r.key))

    def summary(self) -> dict:
        return {
            "agents": len(self.per_agent),
            "union_size": len(self.union),
            "chokepoints": len(self.chokepoints),
            "crown_jewels": len(self.crown_jewels),
            "unparseable": len(self.unparseable),
            "unclassified": len(self.unclassified),
        }


def parse_reach(entry: str) -> Resource:
    """Parse one reach entry. Raises ValueError on a malformed entry — never skips silently."""
    m = _REACH_RE.match(entry.strip())
    if not m:
        raise ValueError(
            f"malformed reach entry {entry!r}: expected '<kind>:<name>' with an optional '!' "
            f"(crown-jewel marker) and kind one of {', '.join(RESOURCE_KINDS)}"
        )
    kind = m.group("kind")
    if kind not in RESOURCE_KINDS:
        raise ValueError(
            f"unclassified resource kind {kind!r} in {entry!r}; expected one of "
            f"{', '.join(RESOURCE_KINDS)}"
        )
    return Resource(kind=kind, name=m.group("name"), crown_jewel=bool(m.group("crown")))


def compute_blast_radius(targets: list[dict]) -> BlastRadius:
    """Compute the estate's blast radius from a target inventory (scope/engagement shape)."""
    br = BlastRadius()
    reach_map: dict[str, set[str]] = {}  # resource key -> agent ids that reach it

    for t in targets:
        tid = t.get("id", "")
        resources: list[Resource] = []
        for entry in t.get("reaches") or []:
            try:
                r = parse_reach(entry)
            except ValueError as exc:
                br.unparseable.append(f"{tid}: {exc}")
                continue
            resources.append(r)
            reach_map.setdefault(r.key, set()).add(tid)
            if r.crown_jewel:
                br.crown_jewels.append(f"{r.key} (reachable from {tid})")
            if r.yield_rank == 99:
                br.unclassified.append(f"{tid}: {r.key}")
        br.per_agent[tid] = sorted(resources, key=lambda r: (r.yield_rank, r.key))

    br.union = sorted(
        {r.key: r for rs in br.per_agent.values() for r in rs}.values(),
        key=lambda r: r.key,
    )
    # Chokepoints: shared resources, worst-yield-first. A resource two agents share is the ASI08
    # cascade path: compromise A, and everything A touches is now attacker-positioned against B.
    for key, holders in reach_map.items():
        if len(holders) > 1:
            r = next(x for x in br.union if x.key == key)
            br.chokepoints.append({
                "resource": key,
                "kind": r.kind,
                "yield": r.yield_label,
                "agents": sorted(holders),
                "crown_jewel": r.crown_jewel,
            })
    br.chokepoints.sort(key=lambda c: (not c["crown_jewel"], c["resource"]))
    br.crown_jewels.sort()
    return br


def render_blast_radius_md(br: BlastRadius) -> str:
    """The markdown section — computed, never hand-typed. Feeds REPORT-SPEC section 6."""
    if not br.per_agent:
        return "No targets were recorded in scope. Nothing to analyse."
    out: list[str] = []
    for tid, resources in br.per_agent.items():
        if resources:
            body = "; ".join(f"`{r.key}` ({r.yield_label})" for r in resources)
        else:
            body = "nothing recorded"
        out.append(f"**{tid}** can reach: {body}.")
    if br.unparseable:
        out.append(
            "\n**Inventory errors (must be fixed before the next report):**\n\n"
            + "\n".join(f"- {u}" for u in br.unparseable)
        )
    ranked = br.exposure_ranked
    out.append(
        "\n**Union of reach across every agent in scope** — "
        f"{len(br.union)} resource(s). Worst-first: "
        + ", ".join(f"`{r.key}`" for r in ranked[:10])
        + ("..." if len(ranked) > 10 else "") + "."
    )
    if br.chokepoints:
        out.append(
            "\n**Cascade chokepoints (ASI08)** — resources reachable from more than one agent. "
            "Compromise one agent and these become attacker-positioned against the others:\n\n"
            + "\n".join(
                f"- `{c['resource']}` ({c['yield']}) — shared by {', '.join(f'`{a}`' for a in c['agents'])}"
                + (" — **crown jewel**" if c["crown_jewel"] else "")
                for c in br.chokepoints
            )
        )
    else:
        out.append(
            "\nNo chokepoints recorded: no resource is reachable from two agents. (This is a "
            "statement about the declared inventory, not a guarantee — see the coverage table."
            + (" The inventory contained unparseable entries, listed above, which may hide shared "
               "resources." if br.unparseable else "") + ")"
        )
    if br.crown_jewels:
        out.append(
            "\n**Crown jewels in reach:**\n\n" + "\n".join(f"- {c}" for c in br.crown_jewels)
        )
    out.append(
        "\n*Computed from the declared inventory by the blast-radius engine; the reachable set is "
        "the union, not the intersection. Resources absent from the inventory are not proven "
        "absent — adversarial testing (sections 4-5) is the check on this page.*"
    )
    return "\n".join(out)
