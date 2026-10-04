#!/usr/bin/env python3
"""K8 audit: axe-core against the LIVE Kessler pages, run locally.

Fetch each live page's HTML, rewrite root-relative asset URLs to absolute so the page renders
with its real styles, embed axe (pinned 4.10.2) plus a runner that writes results into
<pre id="kx-axe">, then render in headless Chrome with a virtual-time budget and read the JSON
back out of the dumped DOM. This is the same file://+budget pattern the K4 truth test used
(the browser harness on this box cannot attach; this needs no harness).

Usage: python scripts/audit-axe.py [url ...]     (default: the nine public surfaces)
Exit 0 always (an audit reports; it does not gate). Results also saved to audit-axe.json
beside this script's scratch."""
import json
import re
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHROME = "C:/Program Files/Google/Chrome/Application/chrome.exe"
HOST = "https://kessler.atlasnex.com"
DEFAULT_PAGES = ["/", "/log/", "/register/", "/verify/", "/playground/", "/sample/",
                 "/pricing/", "/reports/09-threat-index-001.html", "/reports/05-methodology.html"]

RUNNER = """
<script>
window.addEventListener("load", function () {
  setTimeout(function () {
    axe.run(document).then(function (r) {
      var out = { violations: r.violations.map(function (v) {
        return { id: v.id, impact: v.impact, help: v.help, n: v.nodes.length,
                 sample: ((v.nodes[0] || {}).target || [""])[0],
                 snippet: ((v.nodes[0] || {}).html || "").slice(0, 90) };
      }), passes: r.passes.length, incomplete: r.incomplete.length };
      var pre = document.getElementById("kx-axe");
      pre.textContent = JSON.stringify(out);
    }).catch(function (e) {
      document.getElementById("kx-axe").textContent = JSON.stringify({ error: String(e) });
    });
  }, 200);
});
</script>
"""


def audit(url: str, axe_src: str, tmp: Path) -> dict:
    html = subprocess.run(["curl", "-s", "-m", "30", "-A", "kessler-audit", HOST + url], capture_output=True).stdout.decode("utf-8")
    if not html: raise RuntimeError("curl page fetch failed")
    html = re.sub(r'(href|src)="/(?!/)', r'\1="' + HOST + "/", html)
    inject = ('<pre id="kx-axe">pending</pre>' + RUNNER + "<script>" + axe_src + "</script>")
    if "</main>" in html:
        html = html.replace("</main>", inject + "</main>", 1)
    else:
        html = html.replace("</body>", inject + "</body>", 1)
    page = tmp / "page.html"
    page.write_text(html, encoding="utf-8")
    r = subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-first-run",
                        "--allow-file-access-from-files", "--virtual-time-budget=25000",
                        "--dump-dom", "file:///" + page.as_posix()],
                       capture_output=True, text=True, timeout=120)
    m = re.search(r'<pre id="kx-axe">(.*?)</pre>', r.stdout, re.S)
    if not m or m.group(1) == "pending":
        return {"page": url, "error": "axe did not finish"}
    try:
        return {"page": url, **json.loads(m.group(1))}
    except json.JSONDecodeError:
        return {"page": url, "error": "unparseable axe output"}


def main() -> int:
    pages = sys.argv[1:] or DEFAULT_PAGES
    axe_src = urllib.request.urlopen(
        "https://cdnjs.cloudflare.com/ajax/libs/axe-core/4.10.2/axe.min.js",
        timeout=60).read().decode("utf-8")
    print(f"axe-core 4.10.2 ({len(axe_src)} chars); {len(pages)} page(s)")
    results = []
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        for u in pages:
            res = audit(u, axe_src, tmp)
            results.append(res)
            vs = res.get("violations", [])
            if res.get("error"):
                print(f"  {u}: ERROR {res['error']}")
            elif not vs:
                print(f"  {u}: CLEAN ({res['passes']} rules passed, {res['incomplete']} incomplete)")
            else:
                print(f"  {u}: {len(vs)} violation type(s)")
                for v in vs:
                    print(f"    - [{v['impact']}] {v['id']} x{v['n']} @ {v['sample']}"
                          + (f" :: {v['snippet']}" if v.get("snippet") else ""))
    out = ROOT / "audit-axe.json"
    out.write_text(json.dumps(results, indent=1), encoding="utf-8")
    print(f"saved {out.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
