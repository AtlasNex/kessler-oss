"""The Kessler runner CLI (BUILD B3) — the thing that makes the harness a product.

The engagement loop, end to end
-------------------------------
    kessler plan     scopes/example-scope.json        -> the plan: what will run, against what
    kessler run      scope.json [--sample N]        -> attempts recorded into a NEW engagement doc
    kessler report   engagement.json --out outdir    -> all five artefacts (C-4 gated)
    kessler validate engagement.json                -> parse check only
    kessler view      engagement.json [--port N]    -> the localhost viewer (B4)
    kessler corpus   [--show N]                   -> the composed v2 corpus census (D-026)

Design rules, inherited and unchanged:
* **C-2 stdlib-only.** argparse + http.server + json + ThreadPoolExecutor. Runs on a locked-down
  client laptop.
* **Fail closed everywhere.** A scope file that fails validation, a technique that cannot render,
  a dataset that invents a category — every one raises before anything is recorded. Nothing is
  skipped silently; a silently-skipped finding is worse than a crash.
* **The measurement contract.** `run` records attempts (the denominator is honest because every
  scheduled technique produces exactly one attempt, success OR failure); `report` refuses to emit
  while coverage is incomplete (C-4). The runner never writes prose by hand.

Target drivers (Phase 1, PLAN-v3): the default is `echo` (deterministic, offline — CI and the
self-test pipeline). `--driver http` (1.1) sends scheduled units to a real OpenAI-compatible
endpoint and scores them honestly: automated-oracle units become Attempts, manual-oracle units go
to a pending-review sidecar (never a held defence), and an unreached target leaves the unit out of
the denominator entirely. `--lanes N` (1.2) runs bounded parallel request lanes with rate-limit
backoff; the recorded set is identical to a serial run because outcomes are assembled BY JOB
INDEX, never by completion order. Live traffic happens in the driver; the runner records results.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from .asi import ALL_IDS, Attempt
from .corpus import (CHANNELS, PUBLIC_CLAIM, achieved_power, automated_census, build, census,
                     sample)
from .datasets import load_all
from .synth import synthesize_pack, write_pack
from .lint import LintError
from .schema import SchemaError, parse, save
from .scope import load_scope
from .selftest import TargetUnreachable
from . import bundle as bundle_mod
from . import gate as gate_mod


# --------------------------------------------------------------------------- target drivers

@dataclass(frozen=True)
class DriverOutcome:
    """What one scheduled unit produced. Exactly one of the three is set.

    `attempt` — a scored binary result (hit with C-1 evidence, or a held defence). `pending` — a
    manual-oracle unit whose reply a human must judge; it is NEVER a held defence (session-14
    review), so it goes to a sidecar, out of the ASR denominator. `unreached` — the target gave no
    verdict-bearing reply: the unit leaves the denominator entirely (B-9: a network fault is not a
    verdict).
    """

    attempt: "Attempt | None" = None
    pending: dict | None = None
    unreached: str = ""


class EchoDriver:
    """A deterministic offline target: records every scheduled technique as NOT achieved.

    Why a driver that never succeeds: the runner's job is to record attempts honestly, and CI /
    the self-test pipeline need a target that exercises the full path (plan -> attempt -> doc ->
    report) without touching a network. A driver that fabricated successes would be the one thing
    this codebase may never contain (C-1).
    """

    name = "echo"
    #: A live driver can only drive endpoint-declared targets. Echo calls nothing, needs none.
    requires_endpoint = False

    def __init__(self, techniques_by_id: dict | None = None):
        self._techniques = techniques_by_id or {}

    def run_technique(self, technique, target) -> DriverOutcome:
        payload = (technique.render(**{s: target.get("slots", {}).get(s, d)
                                       for s, d in technique.slots.items()})
                   if technique.slots else technique.template)
        return DriverOutcome(attempt=Attempt(
            category=technique.category,
            technique=f"runner:{technique.id}",
            succeeded=False,
            observed="",
            payload=payload,
            environment=f"{target['id']} ({target['kind']})",
            adapter_ref=f"runner:{technique.id}:{target['id']}",
        ))

    def run_case(self, case, target) -> DriverOutcome:
        """Same contract, one corpus-v2 test case (technique x behaviour x channel) at a time.

        Offline: every case is a held defence (the echo driver demonstrates nothing, C-1). The
        payload is the case as composed, so the recorded evidence is the exact text a live driver
        would have sent.
        """
        return DriverOutcome(attempt=Attempt(
            category=case.category,
            technique=f"runner:{case.technique_id}",
            succeeded=False,
            observed="",
            payload=case.content,
            environment=f"{target['id']} ({target['kind']})",
            adapter_ref=f"runner:{case.id}:{target['id']}",
        ))


class LiveHttpDriver:
    """Sends each scheduled unit to a real HTTP target and scores it honestly.

    Three outcomes, never two (session-14 review): a unit whose technique has an AUTOMATED oracle
    is scored hit (with the verbatim reply as C-1 evidence) or held; a unit whose technique is
    MANUAL becomes pending-review, out of the denominator. A target that gives no verdict-bearing
    reply raises TargetUnreachable and the unit is left out entirely (never a held defence).

    The transport is `kessler.selftest.call_target` (OpenAI-compatible chat; endpoint via
    KESSLER_TARGET_URL, Bearer via KESSLER_TARGET_API_KEY, never logged). `call_target` is looked
    up on the selftest MODULE at call time so tests can stub it without any network path.
    """

    name = "http"
    requires_endpoint = True

    def __init__(self, techniques_by_id: dict, timeout: int = 60, retry_window: int = 300):
        self._techniques = techniques_by_id
        self._timeout = timeout
        self._retry_window = retry_window

    def _call(self, prompt: str, history: list[dict] | None = None) -> str:
        """One target turn with rate-limit backoff (the lane pool needs this).

        `transport(prompt, history)` is the STUBBABLE seam (session-13's rule): tests replace
        selftest.transport; production routes it to call_target_multi, whose history parameter
        is what conducts multi-turn sequences (3.2).

        ponytail: retries HTTP 429 only, linear sleep capped at 15s inside a 5-minute window —
        enough for baibase's limits. Upgrade path: honour Retry-After, or a token-bucket lane
        scheduler, if a client endpoint rate-limits harder.
        """
        from . import selftest  # module, not symbol: tests stub selftest.transport
        deadline = time.monotonic() + self._retry_window
        tries = 0
        while True:
            try:
                return selftest.transport(prompt, history=history, timeout=self._timeout)
            except TargetUnreachable as exc:
                if "HTTP 429" not in str(exc) or time.monotonic() >= deadline:
                    raise
                tries += 1
                time.sleep(min(2.0 * tries, 15.0))

    def run_technique(self, technique, target) -> DriverOutcome:
        payload = (technique.render(**{s: target.get("slots", {}).get(s, d)
                                       for s, d in technique.slots.items()})
                   if technique.slots else technique.template)
        reply = self._call(payload)
        return self._score(technique, payload, target,
                           ref=f"runner:{technique.id}:{target['id']}", reply=reply)

    def run_case(self, case, target) -> DriverOutcome:
        technique = self._techniques.get(case.technique_id)
        channel = CHANNELS_BY_ID.get(case.channel_id)
        if channel and channel.sessions:
            # Phase 4 multi-session replay: session 1 plants, session N triggers. History resets
            # between sessions, so only the agent's durable memory connects them — that gap is
            # exactly what the memory-attack pack tests.
            reply, evidence = self._conduct_sessions(channel.compose_sessions(case.payload))
        else:
            turns = channel.compose_turns(case.payload) if channel else [case.content]
            if len(turns) == 1:
                reply, evidence = self._call(turns[0]), None
            else:
                # 3.2: a scripted channel is CONDUCTED — setup turns sent and answered for real,
                # the ask scored on the final reply, the whole transcript carried as the evidence.
                # One attempt per sequence: the denominator counts attacks, not messages.
                reply, evidence = self._conduct(turns)
        if technique is None:
            # A case whose technique cannot be looked up has no knowable oracle. Its reply goes
            # to the human, never silently scored.
            return DriverOutcome(pending={
                "case": case.id, "technique": case.technique_id, "category": case.category,
                "target": target["id"], "channel": case.channel_id,
                "payload": case.content, "reply": (evidence or reply)[:2000],
            })
        return self._score(technique, case.content, target,
                           ref=f"runner:{case.id}:{target['id']}", reply=reply,
                           evidence=evidence, case=case)

    def _conduct(self, turns: list[str]) -> tuple[str, str]:
        """Conduct a scripted sequence; return (final reply, transcript evidence).

        An unreachable turn raises TargetUnreachable, and the WHOLE sequence leaves the
        denominator (B-9): a half-conducted conversation proves nothing about the ask.
        """
        history: list[dict] = []
        reply = ""
        for t in turns:
            reply = self._call(t, history)
            history.append({"role": "user", "content": t})
            history.append({"role": "assistant", "content": reply})
        lines = []
        for i in range(0, len(history), 2):
            lines.append(f"user: {history[i]['content']}")
            lines.append(f"assistant: {history[i + 1]['content']}")
        return reply, self._transcript(lines)

    def _conduct_sessions(self, sessions: list[list[str]]) -> tuple[str, str]:
        """Conduct a multi-session replay (PLAN-v4 Phase 4); return (final reply, transcript).

        The conversation history RESETS between sessions — the target's durable memory is the
        only link, which is exactly what the memory pack tests. One attempt per replay: the
        whole cross-session sequence is one attack. A dead turn unreachES the whole replay
        (B-9), in any session. The transcript records the boundary verbatim.
        """
        lines: list[str] = []
        reply = ""
        for s_index, turns in enumerate(sessions):
            if s_index:
                lines.append("--- conversation reset; durable memory persists ---")
            history: list[dict] = []
            for t in turns:
                reply = self._call(t, history)
                history.append({"role": "user", "content": t})
                history.append({"role": "assistant", "content": reply})
            for i in range(0, len(history), 2):
                lines.append(f"user: {history[i]['content']}")
                lines.append(f"assistant: {history[i + 1]['content']}")
        return reply, self._transcript(lines)

    @staticmethod
    def _transcript(lines: list[str]) -> str:
        # Evidence layout (R2, design-package fix): verdict-bearing text FIRST. The evidence
        # cap clips the END of a string, so a chronological transcript would clip away the
        # final reply — the one thing C-1 exists to preserve. The oracle scores the full
        # reply (unclipped); only the stored evidence is windowed, final reply verbatim,
        # earlier turns elided head-first when they do not fit. `lines` is the flat
        # user/assistant exchange list whose LAST entry is the final reply.
        transcript = lines[-1]
        prior = "\n---\n".join(lines[:-1])  # everything before the final reply
        if prior:
            room = 2000 - len(transcript) - len("\n---\n")
            if room > 0:
                transcript = prior[-room:] + "\n---\n" + transcript
        return transcript

    def _score(self, technique, payload, target, *, ref, reply, evidence=None,
               case=None) -> DriverOutcome:
        from .selftest import effect_hit  # local: live deps stay off the import path
        env = f"{target['id']} ({target['kind']})"
        if not technique.is_automated:
            row = {"technique": technique.id, "category": technique.category,
                   "target": target["id"], "payload": payload,
                   "reply": (evidence or reply)[:2000]}
            if case is not None:
                row.update(case=case.id, channel=case.channel_id)
            return DriverOutcome(pending=row)
        hit = bool(reply) and effect_hit(technique, reply)
        # C-1 evidence: the transcript for a conducted sequence, the verbatim reply otherwise.
        observed = (evidence or reply)[:2000] if hit else ""
        return DriverOutcome(attempt=Attempt(
            category=technique.category,
            technique=f"runner:{technique.id}",
            succeeded=hit,
            observed=observed,
            payload=payload,
            environment=env,
            adapter_ref=ref,
        ))


CHANNELS_BY_ID = {ch.id: ch for ch in CHANNELS}

DRIVERS = {"echo": EchoDriver, "http": LiveHttpDriver}


# --------------------------------------------------------------------------- commands

def cmd_plan(args) -> int:
    """What would run: scope targets x dataset techniques, with the coverage denominator."""
    scope = load_scope(args.scope)
    packs = load_all(args.dataset) if args.dataset else load_all()
    techniques = [t for ts in packs.values() for t in ts]
    targets = scope.targets
    print(f"SCOPE  {scope.ref} — {scope.client}: {len(targets)} target(s)")
    for t in targets:
        print(f"  - {t['id']} ({t['kind']})")
    # The plan must show what `run` will actually do: an excluded category is never attempted,
    # so counting it here would promise a denominator the run cannot deliver.
    excluded = set(scope.exclusions)
    techniques = [t for t in techniques if t.category not in excluded]
    print(f"TECHNIQUES  {len(techniques)} in scope, loaded from {len(packs)} pack(s)")
    by_cat: dict[str, int] = {}
    for t in techniques:
        by_cat[t.category] = by_cat.get(t.category, 0) + 1
    for cid in ALL_IDS:
        if cid in excluded:
            print(f"  {cid}: excluded by the scope - {scope.exclusions[cid][:60]}")
            continue
        marker = "" if by_cat.get(cid) else "  <- NO TECHNIQUE CONTENT (coverage will need an exclusion)"
        print(f"  {cid}: {by_cat.get(cid, 0)} technique(s){marker}")
    unit, count = "techniques", len(techniques)
    if not getattr(args, "techniques_only", False):
        cases, _, behaviors = build(args.dataset, getattr(args, "behaviors", None))
        cases = [c for c in cases if c.category not in excluded]
        if getattr(args, "automated_only", False):
            # The preregistered subset (PLAN-v5 2.3): ONLY automated-oracle techniques can
            # score a baseline cell; manual rows would leave the denominator as pending.
            auto_ids = {t.id for t in techniques if t.is_automated}
            cases = [c for c in cases if c.technique_id in auto_ids]
        cases = sample(cases, getattr(args, "sample", 0) or 0,
                       min_per_category=getattr(args, "min_per_category", 0) or 0)
        power = achieved_power(cases)
        print("ACHIEVED POWER (F-6b) per category — n and the largest true ASR a zero-hit run "
              "of this n still cannot exclude (Wilson 95% upper bound at 0 hits):")
        for cid, row in power.items():
            print(f"  {cid}  n={row['n']:<4} upper_at_zero={row['upper_at_zero']:.1%}")
        unit, count = "composed test cases", len(cases)
        print(f"CORPUS  {count} test case(s) from {len(behaviors)} behaviour(s); "
              "per-category counts above are techniques, the denominator below is cases "
              "(--techniques-only falls back to the technique unit)")
    print(f"PLANNED ATTEMPTS  {count * max(len(targets), 1)} "
          f"({count} {unit} x {max(len(targets), 1)} target(s))")
    if getattr(args, "budget", False):
        if getattr(args, "techniques_only", False):
            print("BUDGET  REFUSED: the meter projects the corpus unit (quoted runs are "
                  "corpus runs); drop --techniques-only. (No corpus, no quote — PLAN-v5 #21.)")
        else:
            from .estate import estimate, render_estimate_md
            print()
            print("RUN COST / POWER METER (PLAN-v5 #21) — a plan is not quoted until this "
                  "projection exists:")
            print(render_estimate_md(estimate(cases, targets,
                                              lanes=getattr(args, "lanes", 8))))
    print("This is the coverage denominator the report will demand (C-4). Run `kessler run` "
          "to execute.")
    return 0


def cmd_synth(args) -> int:
    """Synthesize a per-target behaviour pack from the operator-supplied spec (PLAN-v3 3.3).

    Rule 2 of the module: synthesis never touches datasets/behaviors/, so the default corpus
    count cannot drift. The printed lines describe what was WRITTEN, never a public claim."""
    text = Path(args.spec).read_text(encoding="utf-8")
    try:
        pack = synthesize_pack(text)
    except ValueError as exc:  # tool-less spec: honest refusal, no pack, exit 2
        print(f"REFUSED-SYNTH  {exc}", file=sys.stderr)
        return 2
    rows = pack["behaviors"]
    print(f"TARGET SPEC  {args.spec}")
    print(f"BEHAVIORS    {len(rows)} synthesized "
          f"({len({r['applies_to'][0] for r in rows})} ASI categories)")
    by_cat: dict[str, int] = {}
    for r in rows:
        by_cat[r["applies_to"][0]] = by_cat.get(r["applies_to"][0], 0) + 1
    for cid in ALL_IDS:
        if cid in by_cat:
            print(f"  {cid}: {by_cat[cid]}")
    if args.show:
        # --show N>0 = the rows of the first N ASI categories, in category order (F-1:
        # args.show is an int, so membership must test a slice, not the int itself).
        first_n = set(ALL_IDS[:args.show]) if args.show > 0 else None
        for r in rows:
            if first_n is None or r["applies_to"][0] in first_n:
                print(f"  [{r['id']}] {r['text']}")
    out = write_pack(text, args.out)
    print(f"PACK         {out}  (NOTE: --behaviors is a directory OVERRIDE, not a merge - "
          f"point plan/run at a dir holding this pack BESIDE the standing packs; "
          f"datasets/behaviors/ stays untouched - D-029)")
    return 0


def cmd_review(args) -> int:
    """Serve the human-half review workbench (D-030) for one engagement document."""
    from .review import serve

    serve(Path(args.document), port=args.port, reviewer=args.tester,
          open_browser=not args.no_browser)
    return 0


def cmd_corpus(args) -> int:
    """Print the composed corpus census (D-026 rule 3: the count is printed, never claimed)."""
    cases, techniques, behaviors = build(args.dataset, args.behaviors)
    print(f"TECHNIQUES {len(techniques)}  BEHAVIOURS {len(behaviors)}  CHANNELS {len(CHANNELS)}")
    packs = sorted({(b.pack, b.licence) for b in behaviors})
    for pack, licence in packs:
        print(f"  pack {pack} [{licence}]")
    c = census(cases)
    print(f"TEST CASES {c['total']} (rendered, deduped)")
    for cid in ALL_IDS:
        n = c["by_category"][cid]
        marker = "  <- NO CASES" if not n else ""
        print(f"  {cid}: {n}{marker}")
    for ch in CHANNELS:
        print(f"  {ch.id:<17} {c['by_channel'][ch.id]}")
    ac = automated_census(cases, techniques)
    print(f"AUTOMATED-ORACLE MASS {ac['total']} (only these can score unaided in a live run; "
          f"a NULL result speaks for these categories and no others - review F-6)")
    for cid in ALL_IDS:
        n = ac["by_category"][cid]
        marker = "  <- NO AUTOMATED ORACLE" if not n else ""
        print(f"  {cid}: {n}{marker}")
    if c["empty_categories"]:
        print("REFUSED: categories with zero composed cases: "
              + ", ".join(c["empty_categories"]))
        return 2
    print("CLAIMABLE: " + PUBLIC_CLAIM.format(
        cases=c["total"], techniques=len(techniques),
        behaviors=len(behaviors), channels=len(CHANNELS)))
    if args.show:
        for case in cases[: args.show]:
            print(f"\n--- {case.id}  {case.category} {case.technique_id} "
                  f"{case.behavior_id} via {case.channel_id} ---\n{case.content}")
    return 0


def _computed_exclusions(jobs, outcomes, scope_exclusions, sidecar_name):
    """F-14 root fix (PLAN-v4 Phase 4): compute evidence-bearing exclusions for categories the
    run did not score, so a produced document never carries a silently blank row (C-4 says a
    blank row reads as a formatting choice; it is an undelivered scope item).

    The reason names exactly what happened to the category's units — manual review, unreached,
    or never sampled — and never fabricates a test result. Root-cause level: every caller that
    assembles a document from a run passes through here, so no sibling path ships a blank row.
    """
    from .asi import ALL_IDS

    attempted: set[str] = set()
    manual: dict[str, int] = {}
    lost: dict[str, int] = {}
    for (kind, target, unit), outcome in zip(jobs, outcomes):
        cid = unit.category
        if outcome.attempt is not None:
            attempted.add(cid)
        elif outcome.pending is not None:
            manual[cid] = manual.get(cid, 0) + 1
        elif outcome.unreached:
            lost[cid] = lost.get(cid, 0) + 1
    out: dict[str, str] = {}
    for cid in ALL_IDS:
        if cid in attempted or cid in scope_exclusions:
            continue
        if manual.get(cid):
            out[cid] = (f"{manual[cid]} unit(s) conducted with a manual-oracle only in this run; "
                        f"verdicts pending in {sidecar_name} (outside the ASR denominator, A7-1.x). "
                        f"No automated effect check scores this category.")
        elif lost.get(cid):
            out[cid] = (f"{lost[cid]} scheduled unit(s) never reached the target (B-9: an "
                        f"unreached unit leaves the denominator); in scope but untested in this run.")
        else:
            out[cid] = ("no unit for this category in this run's sample (kessler plan prints the "
                        "per-category counts); untested here.")
    return out


def cmd_run(args) -> int:
    """Execute the plan against the driver; write the engagement document.

    Job order is (target, unit) submission order and outcomes are assembled BY JOB INDEX, so the
    recorded document is identical for --lanes 1 and --lanes 8 (1.2's determinism clause: the
    lanes change wall-clock, never the denominator).
    """
    scope = load_scope(args.scope)
    packs = load_all(args.dataset) if args.dataset else load_all()
    techniques = [t for ts in packs.values() for t in ts]
    targets = scope.targets
    if not targets:
        print("REFUSED: the scope file names no targets — nothing to test, nothing to record.",
              file=sys.stderr)
        return 2
    # D-020 fails FAST, before any traffic: a live run that spends real wall-clock and rate-limit
    # budget only to refuse the document afterwards is the old ordering's bug.
    if not args.tester and not scope.testers:
        print("REFUSED: no tester named. D-020 requires testers NAMED on the engagement document "
              "(a report that cannot say who did the work is unusable as evidence). Pass "
              "--tester \"Your Name\" or add a testers list to the scope file.", file=sys.stderr)
        return 2
    driver = DRIVERS[args.driver]({t.id: t for t in techniques})

    # A category the scope EXCLUDES must not be attempted. Two reasons, both hard: sending traffic
    # for an out-of-scope category is testing outside the signed scope (AGENTS.md), and an attempt
    # recorded under an excluded category silently flips its coverage row from `excluded` to
    # `tested` — the report would then claim coverage the client never authorised.
    excluded = set(scope.exclusions)
    if excluded:
        print(f"SCOPE EXCLUDES  {', '.join(sorted(excluded))} — no attempt will be made for "
              "these; the report carries the written reason instead (C-4)")

    # A live driver can only drive endpoint-declared targets (the A7 rule): a target with no
    # declared endpoint has nothing to call, and routing its traffic through another target's
    # URL would misattribute rows (C-1 adjacent). Skipped HERE, printed, never faked.
    if driver.requires_endpoint:
        targets_run = [t for t in targets if t.get("endpoint")]
        skipped = [t["id"] for t in targets if not t.get("endpoint")]
        if not targets_run:
            print("REFUSED: the live driver found no endpoint-declared target in the scope. "
                  "Add \"endpoint\": true to the tested target or run with --driver echo.",
                  file=sys.stderr)
            return 2
    else:
        targets_run, skipped = list(targets), []

    # Jobs: (kind, target, unit) in deterministic submission order.
    jobs: list[tuple[str, dict, object]] = []
    if not getattr(args, "techniques_only", False):
        # The composed corpus is the unit of work. Against a live driver this is one real
        # request per case per target, so --sample takes a slice that still carries every
        # ASI category; --techniques-only falls back to the 25-technique unit.
        cases, _, behaviors = build(args.dataset, getattr(args, "behaviors", None))
        cases = [c for c in cases if c.category not in excluded]
        if getattr(args, "automated_only", False):
            # The preregistered subset (PLAN-v5 2.3): ONLY automated-oracle techniques can
            # score a baseline cell; manual rows would leave the denominator as pending.
            auto_ids = {t.id for t in techniques if t.is_automated}
            cases = [c for c in cases if c.technique_id in auto_ids]
        total = len(cases)
        cases = sample(cases, getattr(args, "sample", 0) or 0,
                       min_per_category=getattr(args, "min_per_category", 0) or 0)
        power = achieved_power(cases)
        print("ACHIEVED POWER (F-6b) per category — n and the largest true ASR a zero-hit run "
              "of this n still cannot exclude (Wilson 95% upper bound at 0 hits):")
        for cid, row in power.items():
            print(f"  {cid}  n={row['n']:<4} upper_at_zero={row['upper_at_zero']:.1%}")
        note = "" if len(cases) == total else f" (sampled from {total}, every category kept)"
        print(f"CORPUS  {len(cases)} test case(s) from {len(behaviors)} behaviour(s)"
              f"{note}; the denominator is cases, not techniques")
        thin = [cid for cid in ALL_IDS
                if cid not in excluded and not any(c.category == cid for c in cases)]
        if thin:
            print(f"WARNING  the sample carries no case for {', '.join(thin)} — the report will "
                  "REFUSE to emit until those categories are tested or excluded (C-4)")
        for target in targets_run:
            for c in cases:
                jobs.append(("case", target, c))
    else:
        for target in targets_run:
            for t in techniques:
                if t.category in excluded:
                    continue
                jobs.append(("technique", target, t))

    if not jobs:
        print("REFUSED: every in-scope category is excluded — there is nothing to test. A scope "
              "that excludes all ten categories is a scope problem, not a run.", file=sys.stderr)
        return 2

    def _job(job):
        kind, target, unit = job
        try:
            if kind == "case":
                return driver.run_case(unit, target)
            return driver.run_technique(unit, target)
        except TargetUnreachable as exc:
            return DriverOutcome(unreached=f"{unit.id}@{target['id']}: {exc}")

    lanes = max(1, int(getattr(args, "lanes", 1) or 1))
    started = time.monotonic()
    if lanes == 1 or len(jobs) == 1:
        outcomes = [_job(j) for j in jobs]
    else:
        from concurrent.futures import ThreadPoolExecutor  # stdlib; C-2 intact
        outcomes: list[DriverOutcome | None] = [None] * len(jobs)
        with ThreadPoolExecutor(max_workers=lanes) as pool:
            futures = {pool.submit(_job, j): i for i, j in enumerate(jobs)}
            for fut, i in futures.items():
                outcomes[i] = fut.result()
    elapsed = time.monotonic() - started

    attempts = [o.attempt for o in outcomes if o.attempt is not None]
    pending = [o.pending for o in outcomes if o.pending is not None]
    unreached = [o.unreached for o in outcomes if o.unreached]
    if not attempts and not pending:
        print(f"REFUSED: the run recorded nothing — {len(unreached)} of {len(jobs)} scheduled "
              "unit(s) got no verdict-bearing reply. An unreached target is not a tested target.",
              file=sys.stderr)
        return 2

    eng = scope.to_engagement(attempts=attempts)
    if args.ref:
        eng.ref = args.ref
    eng.testers = list(scope.testers)
    if args.tester and args.tester not in eng.testers:
        eng.testers.append(args.tester)
    out = Path(args.out)
    sidecar = None
    if pending:
        sidecar = out.with_name(out.stem + "-pending-review.json")
        sidecar.write_text(json.dumps(
            {"engagement": eng.ref, "count": len(pending), "rows": pending},
            indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    # F-14: no silently blank category in a produced document (see _computed_exclusions).
    for cid, reason in _computed_exclusions(
            jobs, outcomes, eng.exclusions, sidecar.name if sidecar else "").items():
        eng.exclusions[cid] = reason
    save(eng, out)
    done = sum(1 for a in attempts if a.succeeded)
    print(f"RECORDED  {len(attempts)} attempt(s) across {len(targets_run)} target(s) "
          f"in {elapsed:.1f}s ({lanes} lane(s)); {done} succeeded; "
          f"{len(attempts) - done} defences held / not achieved.")
    print(f"DOCUMENT  {out} (engagement {eng.ref})")
    if unreached:
        print(f"UNREACHED  {len(unreached)} scheduled unit(s) got no verdict-bearing reply and "
              "are NOT in the denominator (not counted as defences):")
        for line in unreached[:10]:
            print(f"  - {line}")
        if len(unreached) > 10:
            print(f"  ... and {len(unreached) - 10} more")
    if pending:
        print(f"PENDING-REVIEW  {len(pending)} unit(s) have no automated oracle; their replies "
              f"need a human judge and are NOT in the ASR denominator: {sidecar}")
    if skipped:
        print(f"NOTE  targets skipped by the live driver (no endpoint declared): "
              f"{', '.join(skipped)}")
    print("NEXT  `kessler report " + str(out) + " --out <dir>` — the report will refuse to emit "
          "until every category is tested or excluded with a reason (C-4). That refusal is the "
          "product working.")
    return 0


def cmd_validate(args) -> int:
    eng = parse(json.loads(Path(args.document).read_text(encoding="utf-8")))
    rows = eng.coverage()
    missing = [r["category"] for r in rows if r["status"] == "missing"]
    print(f"VALID  {eng.ref}: {len(eng.attempts)} attempt(s), {len(eng.findings)} finding(s)")
    if missing:
        print(f"coverage incomplete: {len(missing)} category(ies) missing: {', '.join(missing)}")
        print("the report command will REFUSE to emit until this is resolved (C-4)")
        return 1
    print("coverage complete")
    return 0


def cmd_report(args) -> int:
    from .report import attach_baseline_registry, self_check, write_all

    try:
        eng = parse(json.loads(Path(args.document).read_text(encoding="utf-8")))
        if args.baseline:
            from .baseline import load_registry
            from .capsule import canonical_corpus_hash
            registry = load_registry(args.baseline)
            chash = args.corpus_hash or canonical_corpus_hash()
            attach_baseline_registry(eng, registry, chash)
            print(f"BASELINE  registry loaded ({len(registry['entries'])} entries), "
                  f"corpus pin {chash[:12]}…")
        issues = self_check(eng)
        if issues:
            for i in issues:
                print(f"  BLOCKER  {i}", file=sys.stderr)
            print("REFUSED: the generator cannot disagree with itself; fix the document, not the "
                  "checker.", file=sys.stderr)
            return 2
        written = write_all(eng, args.out)
    except (LintError, SchemaError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    from .html_report import render_html_report
    html_path = Path(args.out) / "report.html"
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(render_html_report(eng), encoding="utf-8")
    written.append(html_path)
    for p in written:
        print(f"WROTE  {p}")
    return 0


def cmd_triage(args) -> int:
    """Rank and cluster candidate findings for human attention. The judge proposes; only a
    human (via build_finding) confirms, and the kernel's numbers are untouched by this command."""
    from .datasets import load_all
    from .triage import call_judge, run_triage

    techniques_by_id = {t.id: t for ts in load_all().values() for t in ts}
    report = run_triage(args.document, judge=call_judge, techniques_by_id=techniques_by_id)
    d = report.to_dict()
    out = Path(args.out) if args.out else Path(args.document).with_name(
        Path(args.document).stem + "-triage.json")
    out.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"TRIAGE  {d['judged']} row(s) judged: {d['candidates']} candidate(s), "
          f"{d['dismissed']} dismissed, {d['refused_no_evidence']} refused for no evidence, "
          f"{d['judge_failed']} judge failures.")
    for cat, refs in sorted(d["clusters"].items()):
        print(f"  {cat}: {len(refs)} candidate(s)")
    print(f"ARTEFACT  {out}")
    print("NOTE  this ranking is a reading order, not a measurement: no number here enters any "
          "report; the engagement document was final before this command ran (C-1 shape).")
    return 0


def cmd_calibrate(args) -> int:
    """Measure the configured judge's own error rate against the labelled set (2.2). The only
    numbers this prints describe the JUDGE, never a client's agent."""
    from .triage import call_judge, calibrate

    path = Path(__file__).resolve().parent.parent / "datasets" / "calibration" \
        / "judge-calibration.json"
    labelled = json.loads(path.read_text(encoding="utf-8"))
    try:
        res = calibrate(call_judge, labelled)
    except Exception as exc:  # judge unreachable: honest refusal, no silent zero
        print(f"JUDGE-UNREACHABLE  {exc}\nNEXT  export KESSLER_JUDGE_URL and "
              "KESSLER_JUDGE_API_KEY (the judge must not be the target under test), then retry.",
              file=sys.stderr)
        return 2
    out = Path(args.out) if args.out else Path("judge-calibration-result.json")
    out.write_text(json.dumps(res, indent=2) + "\n", encoding="utf-8")
    fmt = lambda x: "n/a" if x is None else f"{x:.0%}"
    ci = lambda v: "" if not v else f" [{v[0]:.0%}, {v[1]:.0%}]"
    print(f"JUDGE  {res['labelled']} labelled rows: tp={res['tp']} fp={res['fp']} "
          f"fn={res['fn']} tn={res['tn']} skipped={res['skipped']}")
    print(f"FALSE-POSITIVE rate {fmt(res['false_positive_rate'])}"
          f"{ci(res['fp_ci95'])} (of what the judge called candidate)")
    print(f"FALSE-NEGATIVE rate {fmt(res['false_negative_rate'])}"
          f"{ci(res['fn_ci95'])} (of what the truth called candidate — the expensive direction)")
    print(f"NOTE  these rates describe the JUDGE, measured offline against a human-labelled set; "
          f"they belong in methodology prose, never in a client's ASR table. Artefact: {out}")
    return 0


def cmd_view(args) -> int:
    from .viewer import serve
    serve(Path(args.document), port=args.port, open_browser=not args.no_browser)
    return 0


def cmd_gate(args) -> int:
    """The CI gate (PLAN-v4 Phase 2.1). Exit 0 pass, 1 regression, 2 refusal.

    `--init` writes the baseline from the current run (an explicit human act — a gate that
    auto-baselines would launder regressions into passes). Without it, the document is COMPARED
    against the committed baseline.
    """
    try:
        eng = parse(json.loads(Path(args.document).read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, SchemaError) as exc:
        print(f"REFUSED: cannot load the engagement document: {exc}", file=sys.stderr)
        return 2
    if args.init:
        baseline = gate_mod.build_baseline(eng, target_url_env=args.url_env)
        gate_mod.save_baseline(baseline, args.baseline)
        per_cat = ", ".join(f"{cid} {row['successes']}/{row['attempts']}"
                            for cid, row in sorted(baseline["per_category"].items()))
        print(f"BASELINE WRITTEN  {args.baseline} (engagement {baseline['engagement_ref']}, "
              f"{baseline['successes']}/{baseline['total']} overall)")
        print(f"  categories: {per_cat or 'none'}")
        pin = baseline["endpoint"]
        print(f"  endpoint pin: env {pin['env_var']}"
              + (f" url_sha256 {pin['url_sha256'][:16]}... (the URL itself is NOT stored)"
                 if pin["url_sha256"] else " (UNSET at init — name-pinned only)"))
        print("NEXT  commit this file; `kessler gate <doc> --baseline <file>` then fails the "
              "build when the ASR rises significantly or coverage collapses")
        return gate_mod.EXIT_PASS
    try:
        baseline = gate_mod.load_baseline(args.baseline)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"REFUSED: cannot load the baseline: {exc}", file=sys.stderr)
        return gate_mod.EXIT_REFUSED
    except gate_mod.GateError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return gate_mod.EXIT_REFUSED
    report = gate_mod.evaluate_baseline(baseline, eng)
    print(gate_mod.render_gate_report(report, str(args.baseline), eng.ref))
    return {
        "PASS": gate_mod.EXIT_PASS,
        "REGRESSION": gate_mod.EXIT_REGRESSION,
        "REFUSED": gate_mod.EXIT_REFUSED,
    }[report["status"]]


def cmd_bundle(args) -> int:
    """The compliance evidence bundle (PLAN-v4 Phase 3.2): cover + framework annexes + the
    re-pinned standards crosswalk. Renders only what the C-4 gate already allowed elsewhere;
    the certification-language rule runs over every artefact before it is written."""
    eng = parse(json.loads(Path(args.document).read_text(encoding="utf-8")))
    artefacts = bundle_mod.render_bundle(eng)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    bad = 0
    for name, text in artefacts.items():
        hits = bundle_mod.lint_prose(text)
        if hits:
            bad += 1
            print(f"REFUSED {name}: certification language detected:", file=sys.stderr)
            for h in hits:
                print(f"  - {h}", file=sys.stderr)
    if bad:
        print("BUNDLE NOT WRITTEN: fix the wording, not the rule — an overclaim in a procurement "
              "document is the exact business risk COMPLIANCE.md warns about.", file=sys.stderr)
        return 2
    written = []
    for name, text in artefacts.items():
        p = out / name
        p.write_text(text, encoding="utf-8")
        written.append(p)
    for p in written:
        print(f"WROTE  {p}")
    print("NOTE  " + bundle_mod.LOCKED_WORDING)
    return 0


def cmd_mcp_audit(args) -> int:
    """Phase 5: MCP server assessment — Deadbugz drift test, scope flags, exposure flags."""
    from . import mcp_audit

    try:
        snapshot = json.loads(Path(args.snapshot).read_text(encoding="utf-8"))
        report = mcp_audit.audit_snapshot(snapshot)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"REFUSED: cannot audit this snapshot: {exc}", file=sys.stderr)
        return 2
    text = mcp_audit.render_mcp_audit(report)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"WROTE  {args.out}")
    else:
        print(text)
    findings = len(report["drift"]) + len(report["exposure"]) + len(report["over_broad"])
    print(f"RESULT  {findings} flag(s) across {report['calls']} call(s); "
          f"{len(report['pinned'])} tool(s) pinned")
    return 0


def cmd_attest(args) -> int:
    """Phase 5: the agent-estate attestation — dated, hash-pinned inventory + reach evidence."""
    from . import blast as blast_mod
    from . import mcp_audit
    from .report import render_aibom

    eng = parse(json.loads(Path(args.document).read_text(encoding="utf-8")))
    try:
        snapshot = json.loads(Path(args.inventory).read_text(encoding="utf-8"))
        inventory = [{"name": t["name"], "kind": "mcp_tool", "definition": t}
                     for call in snapshot.get("calls", [{}])[:1] for t in call.get("tools", [])]
        if not inventory:
            raise ValueError("the inventory file carries no tool definitions")
    except (OSError, json.JSONDecodeError, ValueError, KeyError) as exc:
        print(f"REFUSED: cannot read the inventory: {exc}", file=sys.stderr)
        return 2
    aibom = render_aibom(eng)
    # Reach evidence from the blast engine: every declared reach entry is a DIRECT edge
    # (steps=1); the attestation records what each agent could reach at test time.
    radius = blast_mod.compute_blast_radius(eng.targets)
    reach = [{"source": agent, "target": r.key, "steps": 1}
             for agent, resources in radius.per_agent.items() for r in resources]
    attestation = mcp_audit.build_attestation(
        engagement=eng, aibom=aibom, reach=reach, inventory=inventory)
    Path(args.out).write_text(json.dumps(attestation, indent=1, ensure_ascii=False) + "\n",
                              encoding="utf-8")
    print(f"WROTE  {args.out} ({len(attestation['components'])} component(s) pinned, "
          f"{len(attestation['reach'])} reach edge(s))")
    print("NOTE  " + attestation["note"])
    return 0


def cmd_verify_attestation(args) -> int:
    """Phase 5: the verifier — re-hash the live inventory; exit 1 on any post-hoc change."""
    from . import mcp_audit

    try:
        attestation = json.loads(Path(args.attestation).read_text(encoding="utf-8"))
        snapshot = json.loads(Path(args.inventory).read_text(encoding="utf-8"))
        inventory = [{"name": t["name"], "kind": "mcp_tool", "definition": t}
                     for call in snapshot.get("calls", [{}])[:1] for t in call.get("tools", [])]
    except (OSError, json.JSONDecodeError, ValueError, KeyError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    problems = mcp_audit.verify_attestation(attestation, inventory)
    if problems:
        print("ATTESTATION VIOLATED:")
        for p in problems:
            print(f"  - {p}")
        return 1
    print(f"INTACT  {len(attestation.get('components', []))} component(s) re-hashed, "
          f"every pin matches")
    return 0


# --------------------------------------------------------------------------- capsule & proof kit

def cmd_capsule(args) -> int:
    """PLAN-v5 #11: build the Verifiable Evidence Capsule for one engagement document."""
    from . import capsule

    try:
        eng = parse(json.loads(Path(args.document).read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, SchemaError) as exc:
        print(f"REFUSED: cannot load the engagement document: {exc}", file=sys.stderr)
        return 2
    try:
        corpus_hash = args.corpus_hash or capsule.canonical_corpus_hash()
        doc = capsule.build_capsule(eng, {
            "engagement_ref": eng.ref,
            "scope_sha256": eng.scope_sha256,
            "corpus_hash": corpus_hash,
            "method": args.method,
            "created_at": args.created or _utc_now_iso(),
        })
    except ValueError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    out = Path(args.out)
    if out.parent != Path("."):
        out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"WROTE  {out}")
    print(f"HEAD   {doc['head_hash']}")
    print("ANCHOR  record the head hash in the public anchor (kessler-oss, or the site's "
          "/verify/ page) — the anchor step is a human act; the capsule is what it anchors.")
    return 0


def _utc_now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def cmd_verify_capsule(args) -> int:
    """Recompute every figure from the capsule's chained evidence; exit 1 on ANY drift.

    This is the OSS-side check a client (or their auditor, or us) runs against a delivered
    capsule. Novee exit convention as in `gate`: 0 valid, 1 tampered/invalid, 2 unusable."""
    from . import capsule

    try:
        doc = json.loads(Path(args.capsule).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"REFUSED: cannot read the capsule: {exc}", file=sys.stderr)
        return 2
    result = capsule.verify_capsule(doc)
    print(result.render())
    if result.ok:
        return 0
    return 1


def cmd_proofkit(args) -> int:
    """PLAN-v5 Wave 1: render the Receivable Proof Kit for one engagement document."""
    from . import proofkit
    from .report import assert_emittable

    try:
        eng = parse(json.loads(Path(args.document).read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, SchemaError) as exc:
        print(f"REFUSED: cannot load the engagement document: {exc}", file=sys.stderr)
        return 2
    try:
        assert_emittable(eng)   # C-4: proof artifacts are emission surfaces too
    except LintError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    existing = None
    if args.tracker:
        try:
            existing = json.loads(Path(args.tracker).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"REFUSED: cannot read the tracker export: {exc}", file=sys.stderr)
            return 2
    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    if args.certificate:
        try:
            cert = proofkit.render_retest_certificate(
                eng, issued=args.issued or _utc_now_iso()[:10],
                retest_window=args.retest_window or "retest delivered with the engagement")
        except ValueError as exc:
            print(f"REFUSED: {exc}", file=sys.stderr)
            return 2
        p = outdir / "retest-certificate.md"
        p.write_text(cert, encoding="utf-8")
        print(f"WROTE  {p}")
        return 0
    written = []
    for name, text in proofkit.render_proofkit(
            eng, existing=existing, retest_window=args.retest_window,
            verify_url=args.verify_url, previous_ref=args.previous).items():
        p = outdir / name
        p.write_text(text, encoding="utf-8")
        written.append(p)
    for p in written:
        print(f"WROTE  {p}")
    print("NOTE  the retest certificate renders only with --certificate against a document "
          "that carries a real retest block; it is not part of the bundle by default.")
    return 0


def cmd_drift(args) -> int:
    """PLAN-v5 #19: the MCP drift radar over a schedule of snapshot files."""
    from . import drift

    snapshots: list[tuple[str, dict]] = []
    for spec in args.snapshot:
        # spec: "stamp=path" (stamp rides the page; path is a kessler/mcp-snapshot/v1 file)
        stamp, _, path = spec.partition("=")
        try:
            snap = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"REFUSED: snapshot {path}: {exc}", file=sys.stderr)
            return 2
        snapshots.append((stamp, snap))
    if len(snapshots) < 2:
        print("REFUSED: the radar needs >= 2 collections (one boundary) — a single snapshot "
              "is `kessler mcp-audit`, not drift.", file=sys.stderr)
        return 2
    text = drift.render_drift_full(snapshots, public=not args.private)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"WROTE  {args.out}")
    else:
        print(text)
    return 0


def cmd_cascade(args) -> int:
    """PLAN-v5 #20: cascade chain-search over an engagement's declared reach graph."""
    from . import cascade

    try:
        eng = parse(json.loads(Path(args.document).read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, SchemaError) as exc:
        print(f"REFUSED: cannot load the engagement document: {exc}", file=sys.stderr)
        return 2
    report = cascade.attach_findings(cascade.search_chains(eng.targets), eng.findings)
    if args.json:
        out = Path(args.json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n",
                       encoding="utf-8")
        print(f"WROTE  {out}")
    text = cascade.render_cascade_md(report, top=args.top)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"WROTE  {args.out}")
    else:
        print(text)
    return 0


def cmd_memory(args) -> int:
    """PLAN-v5 #17: score an engagement's memory-pack attempts into L1/L2/L3 levels."""
    from . import memorypack

    try:
        eng = parse(json.loads(Path(args.document).read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, SchemaError) as exc:
        print(f"REFUSED: cannot load the engagement document: {exc}", file=sys.stderr)
        return 2
    score = memorypack.score_memory_pack(memorypack.attempts_to_triples(eng))
    text = memorypack.render_memory_md(score)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"WROTE  {args.out}")
    else:
        print(text)
    return 0


def cmd_containment(args) -> int:
    """PLAN-v5 #18: render a Containment Profile from measured boundary rows."""
    from . import containment

    try:
        rows = json.loads(Path(args.rows).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"REFUSED: cannot read the boundary rows: {exc}", file=sys.stderr)
        return 2
    try:
        profile = containment.score_containment(rows)
    except ValueError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    text = containment.render_containment_md(profile, estate=args.estate)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"WROTE  {args.out}")
    else:
        print(text)
    return 0


def cmd_rollup(args) -> int:
    """PLAN-v5 #21: per-target rollup of one engagement (Standing-Attestation tenants)."""
    from . import estate

    try:
        eng = parse(json.loads(Path(args.document).read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, SchemaError) as exc:
        print(f"REFUSED: cannot load the engagement document: {exc}", file=sys.stderr)
        return 2
    text = estate.render_rollup_md(estate.rollup(eng))
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"WROTE  {args.out}")
    else:
        print(text)
    return 0


def cmd_baseline(args) -> int:
    """PLAN-v5 #15: register/inspect baseline units (the comparator's source of truth)."""
    from . import baseline
    from .capsule import canonical_corpus_hash

    reg_path = Path(args.registry)
    if args.list:
        if not reg_path.exists():
            print(f"REFUSED: no registry at {reg_path}", file=sys.stderr)
            return 2
        reg = baseline.load_registry(reg_path)
        print(baseline.render_registry_md(reg))
        return 0
    try:
        eng = parse(json.loads(Path(args.document).read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, SchemaError) as exc:
        print(f"REFUSED: cannot load the engagement document: {exc}", file=sys.stderr)
        return 2
    entry = baseline.baseline_entry(args.ref, args.source, f"{eng.start} to {eng.end}",
                                   args.method, args.corpus_hash or canonical_corpus_hash(),
                                   eng.scope_sha256, eng.attempts)
    if reg_path.exists():
        reg = baseline.load_registry(reg_path)
        if any(e["ref"] == entry["ref"] for e in reg["entries"]):
            print(f"REFUSED: baseline ref {entry['ref']!r} already registered — supersede it "
                  "under a new ref (C-9: nothing retrochanges the register)", file=sys.stderr)
            return 2
    else:
        reg = {"schema": baseline.BASELINE_SCHEMA, "entries": []}
    reg["entries"].append(entry)
    reg["entries"].sort(key=lambda e: e["ref"])
    baseline.save_registry(reg, reg_path)
    print(f"REGISTERED {entry['ref']} in {reg_path}: n={entry['n']} successes={entry['successes']}")
    print("PUBLISH RULE  a cell prints a baseline rate only at n >= "
          f"{baseline.N_FLOOR} automated-oracle attempts (preregistered); below it the "
          "comparator prints 'not yet powered' and publishes nothing.")
    return 0


# --------------------------------------------------------------------------- parser

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="kessler",
        description="Kessler — agentic AI red-teaming harness. Plan, run, report, view.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("plan", help="show what would run: targets x techniques, the denominator")
    sp.add_argument("scope", help="scope file (JSON, signed; see scopes/README.md)")
    sp.add_argument("--dataset", help="datasets directory (default: the packaged corpus)")
    sp.add_argument("--techniques-only", action="store_true", dest="techniques_only",
                    help="fall back to the 25-technique unit instead of the composed "
                         "corpus (the corpus is the default unit of work, D-026)")
    sp.add_argument("--sample", type=int, default=0,
                    help="run only N composed cases, dealt round-robin so every ASI "
                         "category stays represented (0 = the whole corpus)")
    sp.add_argument("--min-per-category", type=int, default=0, dest="min_per_category",
                    help="F-6b: reserve this many sampled cases per ASI category first (the "
                         "floor a regression gate needs); the rest deals round-robin")
    sp.add_argument("--behaviors", help="behaviour-pack directory override")
    sp.add_argument("--budget", action="store_true",
                    help="project wall-clock (measured G2 s/unit) and the detection floor "
                         "for this plan before any client quote (PLAN-v5 #21)")
    sp.add_argument("--lanes", type=int, default=8,
                    help="--budget: lane count for the wall-clock projection (default 8)")
    sp.add_argument("--automated-only", action="store_true", dest="automated_only",
                    help="preview only cases whose technique carries an automated effect "
                         "oracle (the preregistered subset; matches `run --automated-only`)")
    sp.set_defaults(fn=cmd_plan)

    sp = sub.add_parser("run", help="execute the plan and record the engagement document")
    sp.add_argument("scope", help="scope file (JSON)")
    sp.add_argument("--out", default="engagement.json", help="where to write the document")
    sp.add_argument("--driver", choices=sorted(DRIVERS), default="echo",
                    help="target driver: echo = offline deterministic (default); http = LIVE "
                         "OpenAI-compatible endpoint (KESSLER_TARGET_URL + Bearer "
                         "KESSLER_TARGET_API_KEY via env, never logged)")
    sp.add_argument("--lanes", type=int, default=1,
                    help="parallel request lanes for the live driver (1 = serial; the "
                         "RECORDED set is identical at any lane count — only wall-clock "
                         "changes)")
    sp.add_argument("--dataset", help="datasets directory override")
    sp.add_argument("--ref", help="engagement reference (default KES-ENG-<today>)")
    sp.add_argument("--tester", help="tester name to record (repeatable fields come later)")
    sp.add_argument("--techniques-only", action="store_true", dest="techniques_only",
                    help="fall back to the 25-technique unit instead of the composed "
                         "corpus (the corpus is the default unit of work, D-026)")
    sp.add_argument("--sample", type=int, default=0,
                    help="run only N composed cases, dealt round-robin so every ASI "
                         "category stays represented (0 = the whole corpus)")
    sp.add_argument("--min-per-category", type=int, default=0, dest="min_per_category",
                    help="F-6b: reserve this many sampled cases per ASI category first (the "
                         "floor a regression gate needs); the rest deals round-robin")
    sp.add_argument("--automated-only", action="store_true", dest="automated_only",
                    help="run only cases whose technique carries an automated effect oracle "
                         "(the preregistered baseline/Open-Bench subset, PLAN-v5 section 2.3: "
                         "a cell publishes only automated-oracle attempts)")
    sp.add_argument("--behaviors", help="behaviour-pack directory override")
    sp.set_defaults(fn=cmd_run)

    sp = sub.add_parser("synth", help="synthesize a per-target behaviour pack from a target "
                                      "spec (PLAN-v3 3.3); never edits datasets/behaviors/")
    sp.add_argument("spec", help="target spec file: `tool: name: description` lines, optional "
                                 "`role:` and `data:` lines")
    sp.add_argument("--out", default="synthesized-behaviors.json",
                    help="pack path (refuses to overwrite; ingest with run/plan --behaviors)")
    sp.add_argument("--show", type=int, default=0, dest="show",
                    help="also print rows: N>0 = the first N categories' rows, -1 = all rows")
    sp.set_defaults(fn=cmd_synth)

    sp = sub.add_parser("review", help="serve the human-half review workbench (D-030): read "
                                       "replies, record verdicts, time the read")
    sp.add_argument("document", help="engagement JSON document (from `kessler run`)")
    sp.add_argument("--port", type=int, default=8643)
    sp.add_argument("--reviewer", dest="tester", default="",
                    help="who is reading (recorded on every verdict)")
    sp.add_argument("--no-browser", action="store_true")
    sp.set_defaults(fn=cmd_review)

    sp = sub.add_parser("corpus", help="compose and count the v2 test-case corpus (D-026)")
    sp.add_argument("--dataset", help="datasets directory override")
    sp.add_argument("--behaviors", help="behaviour-pack directory override")
    sp.add_argument("--show", type=int, default=0, dest="show",
                    help="also print the first N rendered cases")
    sp.set_defaults(fn=cmd_corpus)

    sp = sub.add_parser("validate", help="parse-check an engagement document")
    sp.add_argument("document", help="engagement JSON document")
    sp.set_defaults(fn=cmd_validate)

    sp = sub.add_parser("report", help="emit all five artefacts (C-4 gated)")
    sp.add_argument("document", help="engagement JSON document")
    sp.add_argument("--out", default="out", help="output directory")
    sp.add_argument("--baseline", help="baseline registry JSON (kessler/baseline-registry/v1); "
                                       "adds the public-baseline comparator to section 4")
    sp.add_argument("--corpus-hash", dest="corpus_hash",
                    help="the corpus pin the run was against (default: recompute the current "
                         "corpus hash; a mismatch against the registry pins makes every cell "
                         "'not comparable', which is the honest result, not an error)")
    sp.set_defaults(fn=cmd_report)

    sp = sub.add_parser("triage", help="rank/cluster candidate findings for human attention "
                                       "(the judge proposes; only a human confirms; the kernel "
                                       "computes)")
    sp.add_argument("document", help="engagement JSON document (from `kessler run`)")
    sp.add_argument("--out", help="triage artefact path (default: <document>-triage.json)")
    sp.set_defaults(fn=cmd_triage)

    sp = sub.add_parser("calibrate", help="measure the configured judge's own FP/FN error "
                                         "rate against the labelled calibration set (2.2)")
    sp.add_argument("--out", help="result path (default: ./judge-calibration-result.json)")
    sp.set_defaults(fn=cmd_calibrate)

    sp = sub.add_parser("view", help="localhost viewer over the engagement document (B4)")
    sp.add_argument("document", help="engagement JSON document")
    sp.add_argument("--port", type=int, default=8642)
    sp.add_argument("--no-browser", action="store_true")
    sp.set_defaults(fn=cmd_view)

    sp = sub.add_parser("gate", help="CI regression gate against a committed baseline "
                                     "(exit 0 pass / 1 regression / 2 refusal)")
    sp.add_argument("document", help="engagement JSON document (the baseline source with --init, "
                                     "the comparison subject without)")
    sp.add_argument("--baseline", default="kessler-baseline.json",
                    help="baseline JSON path (written by --init; default ./kessler-baseline.json)")
    sp.add_argument("--init", action="store_true",
                    help="write the baseline from this document instead of comparing")
    sp.add_argument("--url-env", default=gate_mod.DEFAULT_URL_ENV,
                    help="env var naming the live target endpoint to pin (F-8b)")
    sp.set_defaults(fn=cmd_gate)

    sp = sub.add_parser("bundle", help="compliance evidence bundle: EU AI Act Art 55 / ISO 42001 "
                                       "/ NIST AI RMF annexes + standards crosswalk (Phase 3)")
    sp.add_argument("document", help="engagement JSON document")
    sp.add_argument("--out", default="bundle", help="output directory")
    sp.set_defaults(fn=cmd_bundle)

    sp = sub.add_parser("mcp-audit", help="MCP server assessment: Deadbugz drift test over N "
                                         "tools/list snapshots, scope + exposure flags (Phase 5)")
    sp.add_argument("snapshot", help="MCP snapshot JSON (kessler/mcp-snapshot/v1)")
    sp.add_argument("--out", help="write the markdown report here (default: stdout)")
    sp.set_defaults(fn=cmd_mcp_audit)

    sp = sub.add_parser("attest", help="agent-estate attestation: dated hash-pinned inventory "
                                       "+ blast reach evidence (Phase 5)")
    sp.add_argument("document", help="engagement JSON document")
    sp.add_argument("--inventory", required=True, help="MCP snapshot JSON carrying the tools")
    sp.add_argument("--out", required=True, help="attestation JSON to write")
    sp.set_defaults(fn=cmd_attest)

    sp = sub.add_parser("verify-attestation", help="re-hash a live inventory against an "
                                                   "attestation's pins (exit 1 on drift)")
    sp.add_argument("attestation", help="attestation JSON (kessler/attestation/v1)")
    sp.add_argument("--inventory", required=True, help="current MCP snapshot JSON")
    sp.set_defaults(fn=cmd_verify_attestation)

    sp = sub.add_parser("capsule", help="Verifiable Evidence Capsule: hash-chain every attempt "
                                        "and the verdict block so a third party can recompute "
                                        "the whole report from the evidence (PLAN-v5 #11)")
    sp.add_argument("document", help="engagement JSON document")
    sp.add_argument("--out", default="capsule.json", help="capsule JSON to write")
    sp.add_argument("--method", required=True,
                    help="the method string pinned in the capsule (driver / judge / oracle)")
    sp.add_argument("--corpus-hash", dest="corpus_hash",
                    help="corpus pin (default: recompute the current corpus's hash)")
    sp.add_argument("--created", help="ISO timestamp override (deterministic builds/tests)")
    sp.set_defaults(fn=cmd_capsule)

    sp = sub.add_parser("verify-capsule", help="recompute a capsule from its chained evidence "
                                               "(exit 0 valid / 1 tampered / 2 unusable)")
    sp.add_argument("capsule", help="capsule JSON (kessler/capsule/v1)")
    sp.set_defaults(fn=cmd_verify_capsule)

    sp = sub.add_parser("proofkit", help="the Receivable Proof Kit: board summary, coverage "
                                         "heatmap, remediation log, underwriter pack, RFI annex "
                                         "(PLAN-v5 Wave 1); --certificate for the retest cert")
    sp.add_argument("document", help="engagement JSON document")
    sp.add_argument("--out", default="proofkit", help="output directory")
    sp.add_argument("--tracker", help="client tracker export JSON (finding_id -> row) to merge "
                                      "into the remediation log")
    sp.add_argument("--retest-window", dest="retest_window", default="",
                    help="retest window text (default: 30 days from window end)")
    sp.add_argument("--verify-url", dest="verify_url", default="",
                    help="the /verify URL printed on the underwriter pack")
    sp.add_argument("--previous", default="",
                    help="reference of the previous run, for 'what changed since'")
    sp.add_argument("--certificate", action="store_true",
                    help="render ONLY the retest certificate (requires a retest block)")
    sp.add_argument("--issued", default="", help="issue date for the certificate")
    sp.set_defaults(fn=cmd_proofkit)

    sp = sub.add_parser("drift", help="MCP drift radar: hash-pinned tools/list diffing over a "
                                      "schedule of snapshots (Deadbugz class, PLAN-v5 #19)")
    sp.add_argument("--snapshot", action="append", required=True, metavar="STAMP=PATH",
                    help="one collection: '2026-10-01T00:00Z=path.json'; repeat, >= 2")
    sp.add_argument("--out", help="write the markdown here (default: stdout)")
    sp.add_argument("--private", action="store_true",
                    help="alert form (names the estate's tools for the owning client)")
    sp.set_defaults(fn=cmd_drift)

    sp = sub.add_parser("cascade", help="cascade chain-search: enumerate multi-hop paths over "
                                        "the declared reach graph (ASI08, PLAN-v5 #20). A "
                                        "search result is a CANDIDATE path, never an ASR claim.")
    sp.add_argument("document", help="engagement JSON document")
    sp.add_argument("--out", help="write the markdown here (default: stdout)")
    sp.add_argument("--json", help="also write the full chain report as JSON here")
    sp.add_argument("--top", type=int, default=12, help="rows to render (default 12)")
    sp.set_defaults(fn=cmd_cascade)

    sp = sub.add_parser("memory-score", help="score an engagement's memory-pack attempts into "
                                             "L1 write-retrieval / L2 cross-session / L3 "
                                             "trigger-gated levels (PLAN-v5 #17)")
    sp.add_argument("document", help="engagement JSON document")
    sp.add_argument("--out", help="write the markdown here (default: stdout)")
    sp.set_defaults(fn=cmd_memory)

    sp = sub.add_parser("containment", help="render a Containment Profile: per-boundary "
                                            "held-rates over N runs with intervals, expiry, "
                                            "AIUC-1 mapping (PLAN-v5 #18)")
    sp.add_argument("rows", help='boundary rows JSON: [{"boundary":"egress-allowlist",'
                                 '"runs":50,"held":48}, ...]')
    sp.add_argument("--estate", default="", help="estate name to print on the profile")
    sp.add_argument("--out", help="write the markdown here (default: stdout)")
    sp.set_defaults(fn=cmd_containment)

    sp = sub.add_parser("rollup", help="per-target rollup of one engagement — the estate view "
                                       "Standing Attestation tenants key on (PLAN-v5 #21)")
    sp.add_argument("document", help="engagement JSON document")
    sp.add_argument("--out", help="write the markdown here (default: stdout)")
    sp.set_defaults(fn=cmd_rollup)

    sp = sub.add_parser("baseline", help="baseline register: --list renders it; a document "
                                         "registers one baseline unit (PLAN-v5 #15, N-floor "
                                         "publish rule printed with every add)")
    sp.add_argument("document", nargs="?", help="engagement JSON document (the run to register)")
    sp.add_argument("--registry", default="baseline-registry.json",
                    help="registry JSON path (default ./baseline-registry.json)")
    sp.add_argument("--ref", default="", help="unit reference (e.g. BASE-001)")
    sp.add_argument("--source", default="", help="what produced the run (lab/honeypot/rehearsal)")
    sp.add_argument("--method", default="manual",
                    choices=("automated-oracle", "manual", "mixed"),
                    help="the oracle class — only automated-oracle units feed the comparator")
    sp.add_argument("--corpus-hash", dest="corpus_hash", default="",
                    help="corpus pin (default: recompute the current corpus hash)")
    sp.add_argument("--list", action="store_true", help="render the register, add nothing")
    sp.set_defaults(fn=cmd_baseline)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
