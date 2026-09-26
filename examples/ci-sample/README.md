# `examples/ci-sample` — the CI gate, demonstrated green then red

Everything here is **FICTIONAL** sample data (derived from `schemas/examples/engagement-sample.json`,
which says so on every artefact). It exists to prove the CI gate trips on a real regression and
passes on noise — the exact contract of `kessler gate` (PLAN-v4 Phase 2).

| File | What it is |
| --- | --- |
| `engagement.json` | the sample engagement: 8 attempts, 3 hits (overall ASR 3/8) |
| `kessler-baseline.json` | the committed baseline, written by `kessler gate engagement.json --init --baseline kessler-baseline.json` |
| `planted-regression.json` | the SAME engagement with the ASR grown to 36/40 — a regression the gate must reject |

## The proof: green, then red

```console
$ kessler gate engagement.json --baseline kessler-baseline.json
RESULT: PASS (exit 0) — no significant regression against the committed baseline

$ kessler gate planted-regression.json --baseline kessler-baseline.json
REGRESSION  __overall__: 3/8 -> 36/40 — overall current 95% interval sits wholly above the baseline's
RESULT: REGRESSION (exit 1) — the attack-success rate got significantly worse, or coverage collapsed; fix before merge
```

The repository's own CI runs both directions on every push (`.github/workflows/gate.yml`): the sample
must pass, and the planted regression must FAIL — so the gate can never silently become a rubber stamp.

## Using the Action in your own repository

```yaml
jobs:
  gate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4          # your repo, carrying your kessler-baseline.json
      - uses: AtlasNex/kessler-oss/.github/actions/kessler-gate@main
        with:
          document: path/to/engagement.json   # produced by `kessler run`
          baseline: kessler-baseline.json     # committed, produced by `kessler gate --init`
```

Zero-install: no pip, no setup-python. The core is stdlib-only (C-2), so the action runs on
whatever `python3` the runner already has. Exit codes: **0** pass, **1** regression (fail the
build), **2** refusal (the comparison itself is broken — scope drift, endpoint retargeting, or an
invalid baseline; fix before trusting either side).

## What the gate will NOT tell you

An exit 0 is "no significant regression against this baseline", not "the agent is safe". The
baseline is only as honest as the run that produced it — that run's name, scope and evidence live
in the engagement document, and a finding without evidence cannot exist there (C-1).
