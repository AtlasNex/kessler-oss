"""ATL-328 Group 2 (v2): pricing / sample / verify / register copy into the brand voice.
Newline-flexible anchors (repo is eol=lf; built copies CRLF); serve.py edits stay WITHIN
its source lines so no string-literal structure is touched. Sealed artefacts untouched."""
from pathlib import Path

def edit(path, pairs):
    p = Path(path)
    h = p.read_text(encoding="utf-8")
    done = 0
    for old, new in pairs:
        hit = False
        for o, n in ((old.replace("<NL>", "\r\n"), new.replace("<NL>", "\r\n")),
                     (old.replace("<NL>", "\n"), new.replace("<NL>", "\n"))):
            c = h.count(o)
            if c == 1:
                h = h.replace(o, n); done += 1; hit = True; break
            assert c == 0, f"{path}: anchor matched {c}x: {old[:60]}"
        assert hit, f"{path}: anchor not found in either newline form: {old[:70]}"
    p.write_text(h, encoding="utf-8", newline="")
    print(f"{path}: {done}/{len(pairs)} edits")

# 1) pricing source doc -> site/pricing/index.html
edit("docs/publish/06-pricing.md", [
    ("Four of twenty-five AI-security vendors publish prices; twelve are fully opaque. We publish,<NL>because a price you can check is part of a measurement practice.",
     "Four of twenty-five AI-security vendors publish prices; twelve do not. We publish,<NL>because a price you can check is part of measuring honestly."),
    ("**The floor rule in one line:<NL>every rung prices at >= $150 per hour at its planned delivery hours; we never discount, we<NL>reduce scope.**",
     "**The floor rule in one line: every rung prices at >= $150 per hour at its planned hours;<NL>we never discount, we reduce scope.**"),
])

# 2) sample-intro source doc -> site/sample/index.html
edit("docs/publish/08-sample-engagement.md", [
    ("25 adversarial attempts we ran against a disposable lab agent we<NL>own, in September 2026.",
     "25 attacks we ran against a lab agent we own,<NL>in September 2026."),
    ("corpus-unit sampling (6,022 composed test cases to draw from), every attempt counted, every hit<NL>evidenced by the verbatim reply, and the report refuses to emit while any category is neither<NL>tested nor excluded with a written reason.",
     "the corpus holds 6,022 test cases to draw from, every attempt is counted, every hit carries<NL>the reply that proves it, and the report refuses to emit while any category is neither tested<NL>nor excluded in writing."),
])

# 3) /verify/ ledes (site/serve.py, server-rendered) - word-level, within-line only
edit("site/serve.py", [
    ("<h1>Verify a Kessler number</h1>", "<h1>Check a Kessler number yourself</h1>"),
    ("evidence document. The kernel that recomputes it is open source: download the ",
     "evidence file. The checker is open source: download the "),
    ("capsule, run one command, and compare the result against the published report. ",
     "capsule, run one command, and compare what you get with the published report. "),
    ("A capsule proves arithmetic and tamper-evidence; it is not a security verdict ",
     "A capsule proves the arithmetic and that nothing was altered; it is not a verdict "),
    ("<h2>Verify it in your browser</h2>", "<h2>Check it right here</h2>"),
    ("Same arithmetic the CLI runs:", "The same arithmetic the command line runs:"),
])

# 4) register intro (scripts/build-register-page.py)
edit("scripts/build-register-page.py", [
    ("Every number we publish about an agent estate needs a comparable baseline to sit beside; and a<NL>baseline is only honest if you can see its N, its method, and its corpus version. This page is<NL>the register of the measurement units that feed the comparator column in Kessler reports.",
     "Every number we publish about an agent estate needs a baseline to sit beside, and a<NL>baseline is only honest when you can see its N, its method, and its corpus version. This page<NL>is the register: the measurements that feed the comparator column in Kessler reports."),
])

print("GROUP 2 COMPLETE")
