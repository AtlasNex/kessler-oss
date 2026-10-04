"""s32 K0 doctrine edits (ATL-325, doc 22c K0): D1-D6, applied atomically.

Two-phase: verify every anchor count first, then write. All inserted text is asserted ASCII
(the repo forbids em dashes / non-ASCII surprises in docs edits).

D1 N/A-never-padded wording      -> report.py coverage + register page footnote
D2 zero-row interval language    -> bench.py (register), baseline.py, report.py, html_report.py
D3 model-claim vs action         -> 05-methodology.md new section
D4 client-publishable sentence   -> OFFER.md new section
D5 pass@k vocabulary             -> 05-methodology.md
D6 VEC full checklist extension  -> proofkit.py VEC_V10 rows
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

EDITS: list[tuple[str, str, str]] = []


def E(path: str, old: str, new: str) -> None:
    EDITS.append((path, old, new))


# ---------------- D6: proofkit VEC rows ----------------
E(
    "kessler/proofkit.py",
    '     "per-finding replay bundle is on the roadmap"),',
    '     "per-finding replay bundle is on the roadmap; MCP capability tracing via the drift "\n'
    '     "radar"),',
)
_VEC_NEW_ROWS = (
    '    ("Custom adversarial testing (novel findings, not recycled jailbreaks)", "YES",\n'
    '     "first-party corpus of composed cases plus per-target behaviour synthesis; the licence "\n'
    '     "gate blocks verbatim third-party reuse and every case cites its source"),\n'
    '    ("Multi-turn and stateful evaluation (memory, long-lived sessions)", "YES",\n'
    '     "multi-turn runs are conducted sequences, one attempt per sequence with the transcript "\n'
    '     "as evidence; the memory pack measures write/retrieve/trigger poisoning at L1-L3 with "\n'
    '     "rates"),\n'
    '    ("Quantitative, risk-tied metrics (pass@k family)", "YES",\n'
    '     "attack-success rate over counted attempts is a pass@k-family statistic; every rate "\n'
    '     "ships with its 95% Wilson interval and a preregistered N floor"),\n'
    '    ("Human verification of critical findings", "YES",\n'
    '     "candidate successes are hand-adjudicated before any number ships; refusals that quote "\n'
    '     "the injection are excluded by adjudication rules, not by keyword luck"),\n'
    '    ("Evaluator calibration (confusion matrix)", "PARTIAL",\n'
    '     "the triage judge is calibrated on labelled rows (FP 33% [10%, 70%], FN 0% [0%, 49%]) "\n'
    '     "and reported as judge metadata only; a broader oracle confusion matrix is on the "\n'
    '     "roadmap"),\n'
    '    ("Multi-agent / composed-topology evaluation", "PARTIAL",\n'
    '     "the cascade engine measures taint propagation across declared 2-5 node topologies "\n'
    '     "(Drill #01: 0 of 4 chains completed, every hop held), not yet a general simulator"),\n'
    '    ("Sandbox / containment validation", "PARTIAL",\n'
    '     "the containment profile pack measures per-boundary held rates over N runs; it is a "\n'
    '     "measurement, not a sandbox product"),\n'
    '    ("CI/CD integration and regression gating", "YES",\n'
    '     "kessler gate + SARIF and the GitHub Action run the same checks a client CI would; "\n'
    '     "regressions are detected against the registered baseline"),\n'
    '    ("Deterministic replay and seed control", "YES",\n'
    '     "one engagement document; sealed artefacts; kessler verify-capsule recomputes every "\n'
    '     "figure; lane counts are explicit (kessler run --lanes N)"),\n'
    '    ("Data governance (retention, isolation, on-prem)", "YES",\n'
    '     "the kernel is stdlib-only and runs on the client\'s own machine (C-2); findings never "\n'
    '     "leave the client\'s network except the report; no trackers on any surface"),\n'
    '    ("Red-flag posture (stock jailbreaks, opaque scoring, coverage claims)", "YES",\n'
    '     "no stock jailbreak libraries (licence gate), no black-box scoring (method published "\n'
    '     "and versioned), and no full-coverage claims: coverage prints tested / excluded / "\n'
    '     "unsupported"),\n'
)
E(
    "kessler/proofkit.py",
    '     "every artefact"),\n)',
    '     "every artefact"),\n' + _VEC_NEW_ROWS + ')',
)

# ---------------- D2: bench.py ----------------
E(
    "kessler/bench.py",
    '        status = "published" if powered else f"not yet powered (n={u[\'n\']} < {N_FLOOR})"',
    '        if powered:\n'
    '            status = ("published" if u["successes"]\n'
    '                      else f"published; 0 observed in n={u[\'n\']} attempts")\n'
    '        else:\n'
    '            status = f"not yet powered (n={u[\'n\']} < {N_FLOOR})"',
)
E(
    "kessler/bench.py",
    '        f"stack, and maintainer consent to a repo is not consent to attack its instance.",',
    '        f"stack, and maintainer consent to a repo is not consent to attack its instance.",\n'
    '        " A zero row reports what was not observed among the attempts run; read the "\n'
    '        "interval\'s upper bound at that n and nothing more.",',
)

# ---------------- D2: baseline.py ----------------
E(
    "kessler/baseline.py",
    '            rate = f"{e[\'asr\'] * 100:.1f}%"\n'
    '            ci = f"[{e[\'ci_low\'] * 100:.1f}%, {e[\'ci_high\'] * 100:.1f}%]"\n'
    '            status = "published"',
    '            rate = f"{e[\'asr\'] * 100:.1f}%"\n'
    '            ci = f"[{e[\'ci_low\'] * 100:.1f}%, {e[\'ci_high\'] * 100:.1f}%]"\n'
    '            status = ("published" if e["asr"]\n'
    '                      else f"published; 0 observed in n={e[\'n\']} attempts")',
)

# ---------------- D1 + D2: report.py ----------------
E(
    "kessler/report.py",
    '        "excluded, and this report should not have been emitted (see the coverage table)."',
    '        "excluded, and this report should not have been emitted (see the coverage table). A "\n'
    '        "0% row over N attempts is a measurement over that N, not a guarantee: read the "\n'
    '        "interval\'s upper bound at that N."',
)
E(
    "kessler/report.py",
    '        f"**{sum(1 for r in rows if r[\'status\'] == \'missing\')}** missing.",',
    '        f"**{sum(1 for r in rows if r[\'status\'] == \'missing\')}** missing.",\n'
    '        "Excluded categories are stated boundaries with written reasons; nothing is padded "\n'
    '        "into any number, because there is no score to pad.",',
)

# ---------------- D2: html_report.py (ASR-table-specific anchor) ----------------
E(
    "kessler/html_report.py",
    '             f"<td>{_asr_bar(overall)}</td></tr>")\n    o.append("</table></section>")',
    '             f"<td>{_asr_bar(overall)}</td></tr>")\n'
    '    o.append("<div class=\'kv\' style=\'margin-top:.4rem\'>A 0% row over its N is a "\n'
    '             "measurement, not a guarantee: read the interval\\u2019s upper bound at that "\n'
    '             "N.</div>")\n'
    '    o.append("</table></section>")',
)

# ---------------- D3 + D5: methodology page ----------------
E(
    "docs/publish/05-methodology.md",
    "## The polarity trap: why adapters cannot pass booleans",
    "## A claim is not an action\n\n"
    "A transcript is the model's own output. Where a response *claims* it performed an action, the\n"
    "claim alone never scores: the effect oracle decides success, and where the effect cannot be\n"
    "observed (black-box endpoints, claimed-but-unverifiable actions) the row is reported as a\n"
    "claim with its signals, never as a confirmed event. Non-verdicts leave the denominator\n"
    "entirely.\n\n"
    "## The polarity trap: why adapters cannot pass booleans",
)
E(
    "docs/publish/05-methodology.md",
    'per-target rates into a second "estate total".',
    'per-target rates into a second "estate total".\n\n'
    "This rate-over-N is the **pass@k-family statistic** procurement checklists ask for (the\n"
    "probability an attack succeeds within k attempts, estimated at k = the attempts run); the\n"
    "interval is the bound, stated at the same k.",
)

# ---------------- D4: OFFER licensed sentence ----------------
E(
    "docs/OFFER.md",
    "## Engagement shape",
    "## What you may say publicly (pre-approved wording)\n\n"
    "Every engagement includes a publish-ready sentence, licensed to the client, stating exactly\n"
    "what was tested and found:\n\n"
    "> [Client]'s AI agent(s) were adversarially tested by Kessler against [N] licence-gated\n"
    "> scenarios over [M] counted attempts, mapped to OWASP ASI01-ASI10, with attack-success rates\n"
    "> and 95% intervals published in the report; [Q] re-testing [as contracted].\n\n"
    "We report what was tested and found. We do not certify systems as safe, and neither this\n"
    "wording nor the underlying report is a certification by any accredited body (none exists for\n"
    "ASI01-ASI10).\n\n"
    "## Engagement shape",
)

# ---------------- D1/D2: register builder intro ----------------
E(
    "scripts/build-register-page.py",
    "publishes nothing. No cell is ever graded\npass/fail.",
    "publishes nothing. A zero row reports what was not observed among its attempts; read it with\n"
    "the interval's upper bound at that n. No cell is ever graded\npass/fail.",
)

# ---------------- apply (verify-all-then-write) ----------------
def main() -> int:
    buffers: dict[str, str] = {}
    per_file_counts: dict[str, int] = {}
    for path, old, new in EDITS:
        if path not in buffers:
            buffers[path] = (ROOT / path).read_text(encoding="utf-8")
        cnt = buffers[path].count(old)
        if cnt != 1:
            raise SystemExit(f"ANCHOR FAIL: {path}: found {cnt} matches (want 1) for:\n{old[:140]!r}")
        if not all(ord(c) < 128 for c in new):
            raise SystemExit(f"NON-ASCII in new text for {path}")
        buffers[path] = buffers[path].replace(old, new, 1)
        per_file_counts[path] = per_file_counts.get(path, 0) + 1
    for path, text in buffers.items():
        (ROOT / path).write_text(text, encoding="utf-8", newline="")
        print(f"edited {path} ({per_file_counts[path]} edits, {len(text)} bytes)")
    print("K0 edits applied:", len(EDITS), "edits across", len(buffers), "files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
