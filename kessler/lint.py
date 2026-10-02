"""The report linter — mechanical enforcement of C-4, and the reason "no blanks" is credible.

`docs/CONSTRAINTS.md` C-4 says coverage cannot be silently shrunk: every ASI category is `tested`, or
`excluded` with a written reason, or it is `missing`. Until this module existed that was a promise.
Now it is a gate: `assert_emittable()` raises and the report does not go out.

Why a linter rather than careful writing: a hand-written report is exactly where a category quietly
disappears between draft one and the final PDF. The failure is invisible in review because a missing row
looks like a formatting choice. The plan calls this "the highest-leverage single component" for that
reason — it is cheap and it closes the failure mode that would end the practice.

What it checks
--------------
Blockers (the report must not emit):
1. any ASI category is `missing` — not tested and not excluded;
2. any exclusion has a blank reason — an unrecorded scope cut is not coverage;
3. a finding with no evidence;
4. a finding mapped to a category that was never tested — a claim with no measurement behind it;
5. a retest that does not cover a category the baseline tested (a fix claimed with no after-attempts);
6. a duplicated `adapter_ref` — the double-counting symptom (see the garak adapter's trap 1; two rows
   sharing one scanner attempt id means one attempt was counted twice);
7. an ASR percentage in the prose that matches no computed ASR.

What it deliberately does NOT check (stated so nobody assumes otherwise)
-----------------------------------------------------------------------
- **`scope_sha256` is not verified against a real file.** Doing that needs the scope document, which
  the linter does not have. The CLI can; this module does not pretend to.
- **It does not judge severity, wording, or remediation quality.** Those are human calls, and a linter
  that pretended to grade them would invite trust it has not earned.
- **It does not check that findings are *true*.** It checks that they are *evidenced*. The distinction
  is the whole product.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .asi import coverage_is_complete, retest_delta


@dataclass(frozen=True)
class Issue:
    """One reason a report must not emit."""

    code: str
    where: str
    message: str

    def __str__(self) -> str:
        return f"[{self.code}] {self.where}: {self.message}"


class LintError(Exception):
    """Raised by `assert_emittable` when the report must not be emitted."""

    def __init__(self, issues: list[Issue]):
        self.issues = list(issues)
        body = "\n".join(f"  - {i}" for i in self.issues)
        super().__init__(
            f"report REFUSED: {len(self.issues)} blocker(s). Coverage is not complete, so emitting "
            f"this report would claim scope it did not deliver:\n{body}"
        )


#: Matches an attack-success claim in prose, e.g. "overall ASR of 23.4%".
#:
#: Two exclusions, both added because the first version produced a FALSE POSITIVE on the generator's
#: own correct output and would have blocked every report we ever produced:
#:   * `|` is excluded from the gap, so a markdown table header ("| ASR | 95% interval |") cannot be
#:     read as a claim of 95% attack success — the header is scaffolding, not a result;
#:   * a following "interval" is a negative lookahead, so a confidence level is not mistaken for a rate.
#: The ASR *table itself* is generated from the data, so this rule is only guarding hand-written prose.
_ASR_CLAIM = re.compile(
    r"(?i)(?:asr|attack[\s-]success(?:\s+rate)?)[^\n%.|]{0,40}?(\d{1,3}(?:\.\d+)?)\s*%(?!\s*interval)"
)


def _check_coverage(engagement) -> list[Issue]:
    issues: list[Issue] = []
    rows = engagement.coverage()
    for row in rows:
        if row["status"] == "missing":
            issues.append(Issue(
                "C4-MISSING-CATEGORY",
                row["category"],
                f"{row['name']} is neither tested nor excluded. A blank row reads as a formatting "
                "choice; it is an undelivered scope item.",
            ))
        elif row["status"] == "excluded" and not (row["reason"] or "").strip():
            issues.append(Issue(
                "C4-BLANK-EXCLUSION-REASON",
                row["category"],
                "excluded with no written reason — an unrecorded scope cut is not coverage.",
            ))
    if not coverage_is_complete(rows) and not issues:
        issues.append(Issue("C4-COVERAGE", "coverage", "coverage table is incomplete"))
    # coverage() lets attempts win over exclusions, so one attempt under an excluded category
    # silently turns "excluded (reason)" into "tested". That is either testing outside the signed
    # scope or a mis-mapped adapter row; both must stop the report (session-14 review).
    exclusions = getattr(engagement, "exclusions", None) or {}
    stray: dict[str, int] = {}
    for a in engagement.attempts:
        if a.category in exclusions:
            stray[a.category] = stray.get(a.category, 0) + 1
    for cid, n in sorted(stray.items()):
        issues.append(Issue(
            "C4-ATTEMPT-IN-EXCLUDED-CATEGORY",
            cid,
            f"{n} attempt(s) recorded under a category the scope EXCLUDES. Either the test ran "
            "outside the signed scope, or an adapter mapped rows to the wrong category. Remove the "
            "attempts or amend the scope before emitting.",
        ))
    return issues


def _check_findings(engagement) -> list[Issue]:
    issues: list[Issue] = []
    tested = {a.category for a in engagement.attempts}
    for n, f in enumerate(engagement.findings):
        where = f"findings[{n}] {f.category}"
        if not (f.evidence or "").strip():
            issues.append(Issue(
                "C1-FINDING-NO-EVIDENCE", where,
                "finding carries no evidence; an unevidenced claim is not a deliverable (C-1).",
            ))
        if f.category not in tested:
            issues.append(Issue(
                "C5-FINDING-UNTESTED-CATEGORY", where,
                f"finding is mapped to {f.category} but no attempt was recorded against it — "
                "a claim with no measurement behind it.",
            ))
    return issues


def _check_retest(engagement) -> list[Issue]:
    """A retest must compare against something.

    Note on the model: there is no field in which a report can *assert* "we fixed X" —
    `fix_demonstrated` is computed from the attempts, so it can never disagree with them. What CAN go
    wrong is a retest block that compares a category against a baseline that never tested it, or a
    retest block with no attempts at all. Both read as evidence of a fix while being evidence of
    nothing, so both are blockers.

    Deliberately NOT a rule: "the retest must cover every baseline category". A retest covers what was
    fixed; requiring full re-coverage would make the honest retest impossible and push people to skip
    the block entirely.
    """
    issues: list[Issue] = []
    if engagement.retest is None:
        return issues
    after = engagement.retest["attempts"]
    if not after:
        issues.append(Issue(
            "C4-RETEST-EMPTY", "retest",
            "a retest block with no attempts reads as evidence of a fix while being evidence of "
            "nothing.",
        ))
        return issues
    delta = retest_delta(engagement.attempts, after)
    for cid, d in delta.items():
        if cid == "__overall__":
            continue
        if d["after_attempts"] and not d["before_attempts"]:
            issues.append(Issue(
                "C4-RETEST-WITHOUT-BASELINE", f"retest {cid}",
                f"the retest covers {cid} but the baseline recorded no attempt against it — "
                "that compares a result to nothing.",
            ))
    return issues


def _check_duplicate_adapter_refs(engagement) -> list[Issue]:
    """The double-count symptom, generalised across every scanner.

    If two rows share a scanner's own attempt id, that attempt was counted twice — which doubles the
    denominator and halves the reported ASR. garak's report format makes this easy to do by accident
    (see the five traps in kessler/adapters/garak.py), and no downstream number would look wrong.
    """
    seen: dict[str, int] = {}
    for a in engagement.attempts:
        if a.adapter_ref:
            seen[a.adapter_ref] = seen.get(a.adapter_ref, 0) + 1
    return [
        Issue("C5-DUPLICATE-ADAPTER-REF", ref,
              f"ref appears {n} times — one scanner attempt counted {n} times inflates the denominator "
              "and understates the attack-success rate.")
        for ref, n in sorted(seen.items()) if n > 1
    ]


def _check_prose_asr(engagement, prose: str) -> list[Issue]:
    """Every ASR percentage in the prose must match a computed one.

    This is the check that catches a number typed by hand into the narrative and never recomputed
    after the data moved.
    """
    if not prose:
        return []
    computed = {a for a in _all_computed_asr(engagement)}
    issues: list[Issue] = []
    for m in _ASR_CLAIM.finditer(prose):
        claimed = float(m.group(1)) / 100.0
        if not any(abs(claimed - c) <= 0.00105 for c in computed):
            issues.append(Issue(
                "C5-PROSE-ASR-MISMATCH", f"prose: {m.group(0).strip()!r}",
                "no computed ASR matches this figure; either it was hand-written or the data moved "
                "after it was written.",
            ))
    return issues


def _all_computed_asr(engagement) -> list[float]:
    from .asi import compute_asr

    values = [row["asr"] for row in compute_asr(engagement.attempts).values()]
    if engagement.retest is not None:
        values += [row["after_asr"] for row in
                   retest_delta(engagement.attempts, engagement.retest["attempts"]).values()]
    # Baseline comparator figures are measured numbers too (PLAN-v5 #15): a published
    # baseline rate quoted in section 4's comparator column is not "hand-written prose".
    values += getattr(engagement, "_baseline_asr_values", [])
    return values


def lint(engagement, *, prose: str = "") -> list[Issue]:
    """Return every blocker for this engagement. An empty list means it may be emitted."""
    issues: list[Issue] = []
    issues += _check_coverage(engagement)
    issues += _check_findings(engagement)
    issues += _check_retest(engagement)
    issues += _check_duplicate_adapter_refs(engagement)
    issues += _check_prose_asr(engagement, prose)
    return issues


def assert_emittable(engagement, *, prose: str = "") -> None:
    """Raise `LintError` listing EVERY blocker. Fails closed; there is no override flag.

    No `--force`: once an escape hatch exists it gets used under deadline pressure, and the first
    report containing an undelivered scope claim ends the practice.
    """
    issues = lint(engagement, prose=prose)
    if issues:
        raise LintError(issues)
