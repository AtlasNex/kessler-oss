"""ATL-328 Group 1: homepage copy into the brand voice (plain, short, calm).
Sentence-level replaces only; every anchor must match exactly once or the run aborts.
Locked strings stay locked: hero line, 'Measure the blast radius...' triple,
honesty table, prices, labels."""
from pathlib import Path

P = Path("site/index.html")
h = P.read_text(encoding="utf-8")

EDITS = [
    # hero lede
    ("Every AI security vendor shows you a dashboard.",
     "Every security vendor shows you a dashboard."),
    ("We hand you a number a third party can recompute: attack-success rates over counted attempts with 95% intervals, evidence-gated, hash-chained, and re-runnable from our open-source kernel.",
     "We hand you a number anyone can recompute: the share of attacks that got through, attempt by attempt, with a 95% error bar, recomputable from our open-source kernel."),
    # method lede
    ("Classic pentesting targets deterministic code: same request, same response.",
     "Pentesting grew up on code that answers the same way every time."),
    ("Agents are probabilistic; the same attack can succeed and fail on consecutive runs.",
     "Agents do not: the same attack can work on one run and fail on the next."),
    ("We count attempts, we count successes, we publish both, the interval is the honest part, and every delivered number ships re-computable from its own evidence chain.",
     "We count attempts, we count successes, we publish both, and the error bar is the honest part. Every number ships with its evidence chain, recomputable."),
    ("Every assessment covers all ten OWASP agentic categories (ASI01 to ASI10) or records why one is out of scope.",
     "Every assessment covers all ten OWASP agentic categories (ASI01 to ASI10), or says in writing why one is out."),
    ("Coverage gaps are published, not hidden. The report REFUSES to emit while any is blank.",
     "Gaps are published, not hidden: the report refuses to emit while one is blank."),
    ("Every scheduled unit produces exactly one counted attempt.",
     "Every scheduled unit (one test case) produces exactly one counted attempt."),
    ("Successes carry the verbatim reply that proves them, and the harness refuses an unevidenced success in code.",
     "A success carries the reply that proves it, verbatim; the harness rejects a success with no evidence, in code."),
    ("Each rate ships with a 95% Wilson score interval, and every figure re-computes from a hash-chained evidence capsule.",
     "Each rate ships with a 95% Wilson interval, the honest error bar for small counts, and every figure recomputes from a hash-chained evidence capsule."),
    ("Three mild issues that compose into account takeover is the finding that matters.",
     "Three small issues that chain into account takeover is the finding that matters."),
    ("The chain is written as a story, every step evidenced; the cascade is searched, not remembered.",
     "The chain reads like a story, and every step carries evidence; the cascade is searched, not remembered."),
    # try-it shell
    ("The output is a recording captured from the open-source kernel at build time - commands are real; nothing here runs on a server, and where a command needs a target the help text says so instead of inventing a run.",
     "What you see is a recording captured from the open-source kernel at build time - nothing here runs on a server, and where a command needs a target, the help text says so instead of making a run up."),
    # a7 section
    ("Before we measure anyone else, we publish a measurement of ourselves: 25 live attempts from the open corpus against a disposable lab agent we own, every limitation stated.",
     "Before we measure anyone else, we measured ourselves, in public: 25 live attempts from the open corpus against a lab agent we own, every limitation stated."),
    # deliverables
    ("On the verifiable edition, the capsule:",
     "On the verifiable edition, the capsule, a tamper-evident evidence file:"),
    ("It proves arithmetic and tamper-evidence; it never says \"secure\".",
     "It proves the arithmetic and that nothing was altered; it never says \"secure\"."),
    # closing CTA + intake
    ("they share an exfiltration surface, and almost certainly nobody has measured it.",
     "they share one way out for your data, and almost certainly nobody has measured it."),
    ("formal invoicing follows the entity registration",
     "invoicing follows the entity registration"),
]

applied = 0
for old, new in EDITS:
    n = h.count(old)
    assert n == 1, f"anchor count {n} (want 1): {old[:70]}"
    h = h.replace(old, new)
    applied += 1

P.write_text(h, encoding="utf-8", newline="")
print(f"applied {applied}/{len(EDITS)} edits to site/index.html")
print("em dashes now:", h.count("\u2014"))
