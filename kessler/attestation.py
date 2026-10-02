"""Standing Attestation digest (PLAN-v5 #12) — the compounding sale, in one artifact.

What it is
----------
The client runs the PINNED baseline in THEIR CI (gate + SARIF + baseline JSON already ship).
Every period, the same command emits a digest: the runs since last time, their intervalled
rates against the pinned baseline, and the two countersign fields — Kessler's and the client's.
When the countersigners sign it, the digest IS the quarterly evidence an insurer or auditor
consumes (AIUC's quarterly-test condition, R4's spine). When a number moves significantly, the
client's own gate goes RED first — the attestation never launders a regression into a pass:
this module renders what the gate already scored, and says plainly which rows were refusals.

Design rules inherited, stated once here:
* the digest is a VIEW over recorded engagement documents; it measures nothing new (one
  measurement, many surfaces — never a second number for the same run);
* `countersign` fields start EMPTY and the render says "unsigned" until someone signs. An
  attestation that pre-fills its own signature is the fraud this module exists to prevent;
* expiry is computed from the period date, printed, and the digest never claims coverage
  past it (the attestation letter's 90-day rule, at digest scale);
* no verdicts (kill list 6): per-category rows carry ASR + interval + gate outcome, and the
  outcome vocabulary is the gate's own (pass/regression/refused) — never "secure".
"""
from __future__ import annotations

from datetime import date, timedelta

from .asi import compute_asr
from .gate import GATE_SCHEMA  # the baseline's own schema id — verified before we read it

DIGEST_SCHEMA = "kessler/attestation-digest/v1"
VALID_DAYS = 90  # the letter's rule, shared constant by import from the render below

#: The client-side CI bundle instructions (written beside the digest by `kessler standing`).
CLIENT_CI_README = """# Kessler Standing Attestation — your CI runs the pinned measurement

Your repo needs three things (all delivered with this bundle):

1. the pinned **baseline.json** (committed; produced by `kessler gate --init` at engagement
   handover — your team never edits it; a change is a new engagement line item);
2. each period, a fresh run of the pinned corpus against your estate
   (`kessler run <scope> --driver http ...` in your environment or ours, per contract);
3. the gate step in CI (the composite action, or the one-liner):

```bash
PYTHONPATH=kessler-oss python3 -m kessler.cli gate run-this-period.json --baseline baseline.json
# exit 0 pass · 1 significant regression (Wilson intervals must separate; noise never trips) ·
# 2 refusal: scope/endpoint drift, or the comparison is invalid — treat a 2 like a red build.
```

The quarterly digest (`digest.md` here) is the artifact your insurer/auditor consumes: run
references, intervalled numbers, gate outcomes, and the two countersign fields. The gate going
red in YOUR CI is the point: the attestation cannot drift behind your own regression without
becoming a false countersignature. Kessler's kernel is Apache-2.0 and stdlib-only — the
recomputation in CI is auditable by anyone who can read Python, including the counterparty.
"""


def build_digest(*, client: str, estate: str, period: str,
                 baseline: dict, runs: list, gate_outcomes: list[dict],
                 corpus_hash: str, method_version: str) -> dict:
    """runs: engagement documents already recorded (parse()ed); gate_outcomes: one per run
    from `kessler gate` — {document_ref, exit_code} (0/1/2, the gate's own vocabulary)."""
    if baseline.get("schema") != GATE_SCHEMA:
        raise ValueError(f"baseline schema {baseline.get('schema')!r} is not the gate baseline")
    per_run = []
    for eng, outcome in zip(runs, gate_outcomes):
        asr = compute_asr(eng.attempts)
        per_run.append({
            "document_ref": eng.ref,
            "window": {"start": eng.start, "end": eng.end},
            "overall": {k: asr["__overall__"][k] for k in
                        ("attempts", "successes", "asr", "ci_low", "ci_high")},
            "gate_exit": int(outcome["exit_code"]),
        })
    issued = date.today()
    return {
        "schema": DIGEST_SCHEMA,
        "client": client,
        "estate": estate,
        "period": period,
        "corpus_hash": corpus_hash,
        "method_version": method_version,
        "baseline_ref": baseline.get("ref") or baseline.get("engagement_ref", ""),
        "runs": per_run,
        "regressions": [r["document_ref"] for r in per_run if r["gate_exit"] == 1],
        "refusals": [r["document_ref"] for r in per_run if r["gate_exit"] == 2],
        "countersign": {"kessler": "", "client": ""},
        "issued": issued.isoformat(),
        "valid_until": (issued + timedelta(days=VALID_DAYS)).isoformat(),
        "limits": ("A digest attests that the pinned baseline was re-run on the stated estate "
                   "in the stated period with the stated corpus and method; it is not a "
                   "certification and not a security verdict. Gate exits: 0 pass, 1 regression, "
                   "2 refusal-to-compare — a refusal row means NO evidence this period, and it "
                   "renders as such."),
    }


def countersign(digest: dict, *, kessler_sig: str = "", client_sig: str = "") -> dict:
    """Append-only signatures. Re-signing an already-signed side RAISES: a countersigned digest
    is a record; replacing a signature is editing history."""
    cs = digest["countersign"]
    if kessler_sig:
        if cs["kessler"]:
            raise ValueError("kessler signature already present — supersede under a new digest")
        cs["kessler"] = kessler_sig
    if client_sig:
        if cs["client"]:
            raise ValueError("client signature already present — supersede under a new digest")
        cs["client"] = client_sig
    return digest


def render_digest_md(digest: dict) -> str:
    lines = [
        f"# Quarterly attestation digest — {digest['client']} · {digest['estate']}",
        "",
        f"**Period** {digest['period']} · **Baseline** `{digest['baseline_ref']}` · "
        f"**Corpus** `{digest['corpus_hash'][:12]}…` · **Method** {digest['method_version']} · "
        f"**Issued** {digest['issued']} · **Valid until** {digest['valid_until']}",
        "",
        "| Run | Window | Attempts | Successes | ASR | 95% interval | Gate |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in digest["runs"]:
        o = r["overall"]
        ci = ("—" if o["ci_low"] is None
              else f"[{o['ci_low'] * 100:.1f}%, {o['ci_high'] * 100:.1f}%]")
        rate = "—" if o["asr"] is None else f"{o['asr'] * 100:.1f}%"
        gate = {0: "pass", 1: "**REGRESSION**", 2: "refused (not comparable)"}[r["gate_exit"]]
        lines.append(f"| `{r['document_ref']}` | {r['window']['start']} to {r['window']['end']} | "
                     f"{o['attempts']} | {o['successes']} | {rate} | {ci} | {gate} |")
    if digest["regressions"]:
        lines += ["", f"**Regressions this period:** {', '.join(digest['regressions'])} — the "
                      "client's gate went red on these; this digest records it, it does not "
                      "excuse it."]
    if digest["refusals"]:
        lines += ["", f"**Refused comparisons:** {', '.join(digest['refusals'])} — retargeted or "
                      "unreadable runs. A refusal is not a pass; it means no evidence this "
                      "period."]
    lines += [
        "",
        f"Countersigned (Kessler): {digest['countersign']['kessler'] or '(unsigned)'}",
        f"Countersigned (client): {digest['countersign']['client'] or '(unsigned)'}",
        "",
        f"*{digest['limits']}*",
    ]
    return "\n".join(lines)
