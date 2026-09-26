"""MCP server assessment + agent-estate attestation (PLAN-v4 Phase 5).

Why this module exists
----------------------
The hottest documented incident class of 2026 is the poisoned/over-broad MCP server (CSA's
Deadbugz note, CVE-2025-54136, OX Security's 200k unauthenticated instances). Commercial
scanners list tools; nobody diffs them. This module is the priced R3 assessment line, in three
checks that each produce evidence a procurement reader can re-verify:

1. **Tool-chain pinning + drift (the Deadbugz test).** Take N `tools/list` snapshots of the same
   server over time and diff the tool metadata between calls. A definition that CHANGES between
   calls is a poisoned-chain finding (SAFE-T1201-class rug pull); every definition is
   SHA-256-pinned so a later snapshot can prove what changed.
2. **Over-broad permission flags.** Tool names and descriptions are scanned for scope claims
   (filesystem, network, credentials, shell) — the evidence is the matched term and the exact
   definition text, never a severity invented from vibes.
3. **Unauthenticated exposure.** A snapshot row that declares no authentication is flagged with
   its declared transport — the OX/Deadbugz exposure shape.

Agent-estate attestation (`build_attestation`) wraps the same material: a dated, hash-pinned
inventory of the tools/MCP servers an engagement touched, plus the blast engine's reach evidence,
and `verify_attestation` re-hashes the pins so a reader can detect any post-hoc edit. The format
is Kessler's (`kessler/attestation/v1`) and is published with the OSS core so the verifier is
theirs to run (MITRE AI-BOM uses the `application` semantic kind where it carries component
identity — see report.render_aibom).

Everything here is stdlib (C-2). No network: snapshots are files a run or an operator produced.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

MCP_SNAPSHOT_SCHEMA = "kessler/mcp-snapshot/v1"
ATTESTATION_SCHEMA = "kessler/attestation/v1"

#: Scope claims worth flagging in a tool definition (name + description scan). A match is
#: EVIDENCE (the term and the definition), not a verdict: over-broad is for the reviewer to
#: confirm against the server's declared purpose.
_SCOPE_TERMS: dict[str, tuple[str, ...]] = {
    "filesystem": ("filesystem", "file", "delete", "upload", "download", "directory",
                   "workspace"),
    "network": ("http", "url", "request", "fetch", "browser", "fetch_url", "web", "socket"),
    "credentials": ("credential", "secret", "token", "password", "api_key", "api key", "vault",
                    "cookie", "bearer"),
    "shell": ("shell", "exec", "command", "terminal", "bash", "powershell", "run_command"),
}


def _canon(defn: dict) -> str:
    return json.dumps(defn, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def pin_tool(defn: dict) -> str:
    """SHA-256 of the canonical tool definition — the inventory's identity for this tool."""
    return hashlib.sha256(_canon(defn).encode("utf-8")).hexdigest()


def audit_snapshot(snapshot: dict) -> dict:
    """Run the three checks over one server's N-call snapshot.

    Snapshot shape (`kessler/mcp-snapshot/v1`):
      {"schema": ..., "server": str, "purpose": str, "calls": [
          {"at": iso, "auth": str ("none" or a description), "tools": [tool-def dicts, ...]},
          ... at least 2 calls for drift, 1 for the static checks ...]}

    Returns {"server", "calls", "drift": [...], "pinned": {name: sha}, "over_broad": [...],
             "exposure": [...]} — every entry names the evidence it stands on.
    """
    if snapshot.get("schema") != MCP_SNAPSHOT_SCHEMA:
        raise ValueError(f"not a {MCP_SNAPSHOT_SCHEMA} snapshot: {snapshot.get('schema')!r}")
    calls = snapshot.get("calls") or []
    if not calls:
        raise ValueError("a snapshot with no calls says nothing (Deadbugz needs N+1)")
    if not isinstance(snapshot.get("server"), str) or not snapshot["server"].strip():
        raise ValueError("snapshot.server must name the server under assessment")

    drift: list[dict] = []
    pinned: dict[str, str] = {}
    over_broad: list[dict] = []
    exposure: list[dict] = []

    for call_no, call in enumerate(calls, 1):
        auth = str(call.get("auth", "")).strip()
        if not auth or auth.lower() in {"none", "no", "n/a", "unauthenticated"}:
            exposure.append({
                "call": call_no, "auth": auth or "(undeclared)",
                "evidence": f"call {call_no} declares auth={auth or '(undeclared)'!r} — an "
                            f"unauthenticated tool surface is reachable by anyone who can "
                            f"reach the transport",
            })
        seen_now: dict[str, str] = {}
        for defn in call.get("tools") or []:
            if not isinstance(defn, dict) or not defn.get("name"):
                raise ValueError(f"call {call_no}: every tool definition needs a name")
            name = defn["name"]
            digest = pin_tool(defn)
            seen_now[name] = digest
            if name in pinned and pinned[name] != digest:
                drift.append({
                    "tool": name, "call": call_no, "was": pinned[name][:12], "now": digest[:12],
                    "evidence": f"{name!r} changed definition between calls "
                                f"({pinned[name][:12]} -> {digest[:12]}): a tool chain that "
                                f"mutates under observation is the Deadbugz/rug-pull shape "
                                f"(SAFE-T1201-class)",
                })
            pinned.setdefault(name, digest)
            haystack = f"{name} {defn.get('description', '')}".lower()
            for scope, terms in _SCOPE_TERMS.items():
                hits = [t for t in terms if t in haystack]
                if hits:
                    over_broad.append({
                        "tool": name, "scope": scope, "terms": hits, "call": call_no,
                        "evidence": f"{name!r} claims {scope} scope (terms: {', '.join(hits)}) "
                                    f"in its own definition — confirm against the server's "
                                    f"declared purpose ({snapshot.get('purpose', 'undeclared')!r})",
                    })
        # tools that VANISHED are drift too (a chain that silently drops a pinned tool)
        if call_no > 1:
            for name, digest in pinned.items():
                if name not in seen_now:
                    drift.append({
                        "tool": name, "call": call_no, "was": digest[:12], "now": "(absent)",
                        "evidence": f"{name!r} vanished from call {call_no} while pinned as "
                                    f"{digest[:12]} — a tool chain that sheds tools under "
                                    f"observation is drift, not maintenance",
                    })
    return {
        "server": snapshot["server"],
        "calls": len(calls),
        "drift": drift,
        "pinned": pinned,
        "over_broad": over_broad,
        "exposure": exposure,
    }


def render_mcp_audit(report: dict) -> str:
    lines = [
        f"# MCP server assessment — {report['server']}",
        "",
        f"Snapshots compared: {report['calls']} (`{MCP_SNAPSHOT_SCHEMA}`). Tools pinned: "
        f"{len(report['pinned'])}.",
        "",
    ]
    if report["drift"]:
        lines.append("## Tool-chain drift (the Deadbugz test)")
        for row in report["drift"]:
            lines.append(f"- **{row['tool']}** (call {row['call']}): {row['evidence']}")
        lines.append("")
    if report["exposure"]:
        lines.append("## Unauthenticated exposure")
        for row in report["exposure"]:
            lines.append(f"- {row['evidence']}")
        lines.append("")
    if report["over_broad"]:
        lines.append("## Scope claims to confirm against the declared purpose")
        for row in report["over_broad"]:
            lines.append(f"- {row['evidence']}")
        lines.append("")
    if not (report["drift"] or report["exposure"] or report["over_broad"]):
        lines.append("No drift, no undeclared-auth call, no scope claim beyond the declared "
                     "purpose — at these snapshots. This is a dated measurement, not a warranty.")
    lines += ["", "## Pinned tool identities (SHA-256, canonical JSON)"]
    for name, digest in sorted(report["pinned"].items()):
        lines.append(f"- `{name}` `{digest}`")
    return "\n".join(lines) + "\n"


def build_attestation(*, engagement, aibom: dict, reach: list[dict],
                      inventory: list[dict]) -> dict:
    """The agent-estate attestation: a dated, hash-pinned inventory + the reach evidence.

    `inventory` rows: {"name", "kind", "definition": dict} — a tool or MCP server definition
    exactly as declared. `reach` is blast.render_reach output (or [] when the estate declares
    no edges — the attestation says so rather than hiding it).
    """
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    components = []
    for row in inventory:
        components.append({
            "name": row["name"], "kind": row["kind"],
            "hash_sha256": pin_tool(row["definition"]),
        })
    return {
        "schema": ATTESTATION_SCHEMA,
        "generated": now,
        "engagement": engagement.ref,
        "scope_sha256": engagement.scope_sha256,
        "targets": [t["id"] for t in getattr(engagement, "targets", [])],
        "components": components,
        "bom_ref": {"components": len(aibom.get("components", [])),
                    "vulnerabilities": len(aibom.get("vulnerabilities", []))},
        "reach": [{"source": r.get("source"), "target": r.get("target"),
                   "steps": r.get("steps")} for r in reach],
        "note": ("A dated inventory of what this engagement touched, hash-pinned against "
                 "post-hoc edit. Attests to the inventory's integrity and the testing performed; "
                 "not a certification, not a compliance claim."),
    }


def verify_attestation(attestation: dict, inventory: list[dict]) -> list[str]:
    """Re-hash the live inventory against the attestation's pins. Empty list = intact."""
    if attestation.get("schema") != ATTESTATION_SCHEMA:
        return [f"unknown attestation schema: {attestation.get('schema')!r}"]
    problems: list[str] = []
    pinned = {c["name"]: c for c in attestation.get("components", [])}
    live = {row["name"]: pin_tool(row["definition"]) for row in inventory}
    for name, digest in live.items():
        if name not in pinned:
            problems.append(f"{name}: present now, absent from the attestation (added later)")
        elif pinned[name]["hash_sha256"] != digest:
            problems.append(f"{name}: definition changed after attestation "
                            f"({pinned[name]['hash_sha256'][:12]} -> {digest[:12]})")
    for name in pinned:
        if name not in live:
            problems.append(f"{name}: attested but absent now (removed later)")
    return problems
