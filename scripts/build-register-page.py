#!/usr/bin/env python3
"""Build site/register/index.html (PLAN-v5 #15) — the public baseline register page.

Content is rendered from the two machine registers (baseline + Open Bench), the comparator
publish rule, and the estate-fingerprint explanation from sds.py — never hand-typed numbers.
Re-run after registering units; the page cannot drift from the data it shows."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import importlib.util as _ilu
_spec = _ilu.spec_from_file_location("_br", ROOT / "scripts" / "build-reports.py")
_br = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_br)
PAGE = _br.PAGE
import markdown

from kessler import baseline, bench, sds
from kessler.baseline import N_FLOOR

reg = (baseline.load_registry(ROOT / "baseline-registry.json")
       if (ROOT / "baseline-registry.json").exists() else {"entries": []})
try:
    benchreg = bench.load_register(ROOT / "bench-register.json")
except (OSError, ValueError):
    benchreg = {"units": [], "preregistration": bench.PREREGISTRATION,
                "schema": bench.BENCH_SCHEMA}

md = f"""# The baseline register

Every number we publish about an agent estate needs a comparable baseline to sit beside ;
and a baseline is only honest if you can see its N, its method, and its corpus version.
This page is the register of the measurement units that feed the comparator column in
Kessler reports. {N_FLOOR} automated-oracle attempts minimum per cell to publish a rate;
below it a cell prints "not yet powered" and publishes nothing. No cell is ever graded
pass/fail.

## Baseline units

{baseline.render_registry_md(reg) if reg["entries"] else "_No units registered yet; the first rows land with the honeypot rehearsals this week._"}

## Open Bench v0 units

{bench.render_bench_md(benchreg) if benchreg["units"] else "_No bench units registered yet. v0 seeds from our own lab and the g2 honeypots; consented entries open with the scope-law form._"}

The preregistration (frozen in the kernel, checked on load): automated-oracle subset only,
per-cell floor n>={N_FLOOR}, Wilson 95%, evidence-gated, no verdicts.

## Comparability and estate fingerprints

Two runs are comparable when they share the corpus version and the method. Beyond that,
reports can be aligned **per estate** through the Susceptibility Data Sheet's estate
fingerprint: a SHA-256 over the scope hash plus the target inventory (ids, kinds, declared
reach). It is an identity, not a score — it lets you (and an auditor) tell whether two
sheets describe the same estate across time without revealing the estate itself. Nothing
here is a certification: no accredited body certifies against OWASP ASI01-ASI10, and AIUC-1
certificates are issued by AIUC through accredited auditors.

## Add a unit

Own lab or honeypot: run `kessler baseline <document.json> --ref ... --source ...
--method automated-oracle` against this register and commit the row; a bench unit needs
`kessler bench` with a scope-law kind (`own-lab`, `g2-honeypot`, `oss-selfhosted`,
`opt-in-consented`) and its authorization record. Third-party hosted targets are not
registrable — maintainer consent to a repository is not permission to attack its hosted
instance. Vendor-paid entries are refused (kill list 7).

Kernel: [github.com/AtlasNex/kessler-oss](https://github.com/AtlasNex/kessler-oss) ·
method: [measurement, not verdicts](../reports/05-methodology.html).
"""

out = ROOT / "site" / "register"
out.mkdir(exist_ok=True)
html = PAGE.format(title="Baseline register | Kessler by AtlasNex",
                   body=markdown.markdown(md.replace("—", " -"), extensions=["tables"]))
assert "\u2014" not in html, "em dash in shipped copy"
(out / "index.html").write_text(html, encoding="utf-8")
print("built site/register/index.html,", len(html), "bytes")
