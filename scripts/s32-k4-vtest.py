"""K4/S-3 truth test: proves the browser canonicalizer+chain-walk matches the kernel on the
REAL capsule, and that the tamper simulation detects a one-character edit.

Method: python computes the expected hash for every link (the kernel's own _canon); a scratch
page loads the real kx.js widget with fetch stubbed to the capsule text, auto-clicks recompute,
then auto-clicks tamper; results land in #probe and are compared here. Exit 0 only on full
agreement."""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from kessler.capsule import _canon  # the same canonicalizer the kernel hashes with
import hashlib

CAP = ROOT / "site" / "verify" / "SELFTEST-A7-001.capsule.json"
cap_text = CAP.read_text(encoding="utf-8")
cap = json.loads(cap_text)

# --- python truth -------------------------------------------------------------
expected = []
prev = "0" * 64
for i, link in enumerate(cap["chain"]):
    body = {k: v for k, v in link.items() if k != "hash"}
    h = hashlib.sha256(_canon(body)).hexdigest()
    expected.append({"i": i, "kind": link["record"]["kind"], "hash": h,
                     "matches": h == link["hash"], "links": link["prev_hash"] == prev})
    prev = link["hash"]
truth = {
    "n": len(expected),
    "all_hashes_match": all(e["matches"] for e in expected),
    "all_links_ok": all(e["links"] for e in expected),
    "head": cap["head_hash"],
    "last": expected[-1]["hash"],
}
print("python truth:", json.dumps(truth))

# --- scratch page -------------------------------------------------------------
SC = Path("C:/Users/sanja/AppData/Local/hermes/cache/scratch/k4v")
if SC.exists():
    shutil.rmtree(SC)
SC.mkdir(parents=True)
shutil.copy2(ROOT / "site" / "kx.js", SC / "kx.js")
shutil.copy2(ROOT / "site" / "kx.css", SC / "kx.css")

page = """<!doctype html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="kx.css">
<script>
window.__CAP__ = __CAPTEXT__;
window.fetch = function () {
  return Promise.resolve({ text: function () { return Promise.resolve(window.__CAP__); } });
};
</script></head><body>
<div class="kx-verify" data-kx-verify data-capsule="SELFTEST-A7-001.capsule.json">
<h3>Verify it in your browser</h3>
<button type="button" data-kx-verify-run>Recompute the chain</button>
<span data-kx-verify-status></span>
<div data-kx-verify-links></div>
<div data-kx-verify-detail></div>
<button type="button" data-kx-verify-tamper>simulate tampering</button>
</div>
<script src="kx.js" defer></script>
<script>
function probe(id, obj) {
  var s = document.createElement("pre");
  s.id = id;
  s.textContent = JSON.stringify(obj);
  document.body.appendChild(s);
}
window.addEventListener("load", function () {
  setTimeout(function () {
    document.querySelector("[data-kx-verify-run]").click();
    setTimeout(function () {
      probe("probe", {
        status: document.querySelector("[data-kx-verify-status]").textContent,
        ok: document.querySelectorAll("[data-kx-verify-links] .kx-vlink[data-ok='1']").length,
        bad: document.querySelectorAll("[data-kx-verify-links] .kx-vlink[data-ok='0']").length
      });
      document.querySelector("[data-kx-verify-tamper]").click();
      setTimeout(function () {
        probe("probe2", {
          status: document.querySelector("[data-kx-verify-status]").textContent,
          ok: document.querySelectorAll("[data-kx-verify-links] .kx-vlink[data-ok='1']").length,
          bad: document.querySelectorAll("[data-kx-verify-links] .kx-vlink[data-ok='0']").length,
          detail: document.querySelector("[data-kx-verify-detail]").textContent.slice(0, 900)
        });
      }, 1500);
    }, 1500);
  }, 300);
});
</script></body></html>"""
page = page.replace("__CAPTEXT__", json.dumps(cap_text))
(SC / "index.html").write_text(page, encoding="utf-8")

CHROME = "C:/Program Files/Google/Chrome/Application/chrome.exe"
url = "file:///" + str(SC).replace("\\", "/") + "/index.html"
r = subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-first-run",
                    "--virtual-time-budget=15000", "--dump-dom", url],
                   capture_output=True, text=True, timeout=120)
dom = r.stdout
p1 = re.search(r'<pre id="probe">([^<]*)</pre>', dom)
p2 = re.search(r'<pre id="probe2">([^<]*)</pre>', dom)
fails = []
if not p1:
    fails.append("no probe result (widget did not run)")
    r1 = {}
else:
    r1 = json.loads(p1.group(1))
    if f"VALID" not in r1.get("status", ""):
        fails.append(f"published capsule: expected VALID, got {r1.get('status')!r}")
    if r1.get("ok") != truth["n"] or r1.get("bad") != 0:
        fails.append(f"published capsule: links ok={r1.get('ok')} bad={r1.get('bad')}, want {truth['n']}/0")
if not p2:
    fails.append("no tamper result")
    r2 = {}
else:
    r2 = json.loads(p2.group(1))
    if "FAILED" not in r2.get("status", ""):
        fails.append(f"tampered copy: expected FAILED, got {r2.get('status')!r}")
    if not (0 < r2.get("bad", 0) <= truth["n"]):
        fails.append(f"tampered copy: bad links={r2.get('bad')}, want 1..{truth['n']}")
print("probe1:", json.dumps(r1))
print("probe2:", json.dumps(r2))
print("TRUTH TEST:", "ALL PASS" if not fails and truth["all_hashes_match"] else f"FAILURES: {fails}")
sys.exit(0 if (not fails and truth["all_hashes_match"]) else 1)
