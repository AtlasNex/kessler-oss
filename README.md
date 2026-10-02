# Kessler — an evidence-disciplined attack harness for agentic AI

Kessler attacks AI agents that hold **tools, memory and credentials**, and reports what worked as
a **measured attack-success rate (ASR) with a 95% Wilson interval over a stated N** — never a
yes/no, never "resists attacks". This repository is the harness itself: the stdlib-only core,
the adapters, and the composed attack corpus. It is published as a proof artifact — the
methodology behind Kessler's published measurements (see
[kessler.atlasnex.com](https://kessler.atlasnex.com)).

## The one rule the code enforces

**An attempt marked succeeded without observed evidence cannot exist.** (`C-1`: the
`Attempt` dataclass raises on construction.) Every finding carries the target's own verbatim
reply that demonstrates the objective was achieved, plus a reproduction script. Nothing in a
report is hand-written; every figure traces to attempt records.

## What is here

| | |
| --- | --- |
| `kessler/` | the core: ASI taxonomy + ASR kernel (Wilson intervals), evidence-gated attempts/findings (KES contract), live HTTP driver with deterministic parallel lanes, multi-turn conduction, report/SARIF/AIBOM renderers, **compliance evidence bundles** (EU AI Act Art 55 / ISO 42001 / NIST AI RMF) with an anti-certification lint rule, **`kessler gate`** — a CI regression gate over committed baselines, **the Verifiable Evidence Capsule** (`capsule` builds it, `verify-capsule` recomputes it), baseline register + comparator, proof kit (board summary, heatmap, retest certificate, underwriter pack), memory L1/L2/L3 scorer, containment profile, MCP drift radar, cascade chain-search, estate rollup + run cost/power meter, blast-radius engine, localhost viewer, adapter importers (garak, PyRIT, DeepTeam, mcp-scanner, AI Infra Guard), MCP tool-chain auditor |
| `datasets/` | 25 ASI techniques + 126 attacker behaviours (first-party frames + InjecAgent and AgentDojo objectives verbatim, all MIT) composed into **3,758 test cases** across 7 channels; `python -m kessler.cli corpus` prints the census, so count them yourself; licence gate refuses unprovenanced packs |
| `examples/ci-sample/` | green→red proof for the CI gate (and what this repo's CI runs) |

## Quickstart (zero-install: Python 3.10+, nothing else)

```bash
python -m kessler.cli plan    scopes/example-scope.json          # what would be tested
python -m kessler.cli run     scopes/example-scope.json --tester "Your Name" --driver echo
python -m kessler.cli report  run-selftest/<ref>.json --out out/ # five artefacts + bundle
```

The `echo` driver is the offline default: it records only what was actually attempted and never
fabricates a success. The live driver (`--driver http`, `KESSLER_TARGET_URL`) conducts real attacks
against endpoints you are authorised to test. This repo's CI runs the whole pipeline plus the
gate's green→red proof on every push — zero-install, bare interpreter.

## CI gate

```yaml
- uses: AtlasNex/kessler-oss/.github/actions/kessler-gate@main
  with:
    document: engagement.json        # from `kessler run`
    baseline: kessler-baseline.json  # committed, from `kessler gate --init`
```

Exit 0 = no significant regression (Wilson intervals must separate before a verdict), 1 = the
ASR rose significantly or a category lost coverage, 2 = the comparison itself is broken and
refuses to score. This repository's own CI proves both directions on every push.

## Verify a number someone handed you

```bash
python -m kessler.cli verify-capsule capsule.json   # exit 0 valid / 1 tampered / 2 unusable
```

A Verifiable Evidence Capsule is a hash-chained record of one engagement: the scope facts, every
attempt with its verbatim evidence, and the computed ASR block — each record chained to the last
by SHA-256. `verify-capsule` rebuilds every attempt through the kernel's own constructors and
recomputes every rate from the chain. It proves arithmetic and tamper-evidence; it is not a
security verdict and not a certification. If any byte of the evidence was edited, the check says
so loudly. Build one for your own runs with `kessler capsule <document.json> --method "..."`.

## What this is NOT

This is not a scanner that spits CVEs, not a certification, and not legal or regulatory advice.
A low ASR is "the defences held under this corpus, at this N, on this date" — a floor for
attackers, never a ceiling. The compliance bundle attests to **testing performed**, never that a
system meets a framework.

## Licence

Apache-2.0. Attack-behaviour packs under `datasets/behaviors/` carry their own upstream licences
(MIT) and provenance in `datasets/LICENSES/`.

Kessler is built by [AtlasNex](https://atlasnex.com/kessler). Contact:
security@atlasnex.com.
