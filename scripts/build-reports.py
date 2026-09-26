"""Render docs/publish/*.md to the site's report pages (PLAN-v4 Phase 1).

The publish drafts stay canonical Markdown in the repo; this script renders them onto the
landing site's chrome (amber-on-black, same CSS vocabulary as site/index.html) and writes
site/reports/<slug>.html. Uses the `markdown` package (build-time only — the C-2 stdlib-only
rule governs the kessler core and tests, not the site builder).

Usage:  python scripts/build-reports.py        # regenerates site/reports/
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "site" / "reports"

#: (source markdown, output slug, page title)
PAGES = [
    ("docs/publish/01-a7-writeup.md", "01-a7-writeup.html",
     "The first measurement: Kessler's A7 self-test"),
    ("docs/publish/02-teardown-01-echoleak.md", "02-teardown-01-echoleak.html",
     "Teardown 01 — EchoLeak (CVE-2025-32711)"),
    ("docs/publish/03-mcp-vetting-method.md", "03-mcp-vetting-method.html",
     "How we vet an MCP server: three checks, each with named evidence"),
]

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} · Kessler</title>
<meta name="description" content="Published work from Kessler — adversarial testing for agentic AI.">
<style>
:root {{
  --bg:#0b0d10; --bg2:#11151b; --border:#1c1c1c; --border2:#2a2a2a;
  --text:#e8e8e8; --dim:#8b949e; --muted:#555;
  --amber:#ffb627; --amber2:#ffc752; --crit:#ff4a5f; --ok:#5fd97a;
  --mono:ui-monospace,'JetBrains Mono',Menlo,Consolas,monospace;
}}
*{{box-sizing:border-box;margin:0;padding:0}}
html{{scroll-behavior:smooth}}
body{{background:var(--bg);color:var(--text);font-family:var(--mono);font-size:15px;
     line-height:1.7;-webkit-font-smoothing:antialiased}}
body::before{{content:'';position:fixed;inset:0;pointer-events:none;z-index:0;
  background-image:linear-gradient(rgba(255,255,255,.012) 1px,transparent 1px),
                   linear-gradient(90deg,rgba(255,255,255,.012) 1px,transparent 1px);
  background-size:48px 48px}}
main{{position:relative;z-index:1;max-width:820px;margin:0 auto;padding:0 1.5rem 4rem}}
nav{{display:flex;gap:1.2rem;padding:1.4rem 0;font-size:.85rem}}
nav .brand{{font-weight:700;color:var(--amber);font-size:1rem;margin-right:auto}}
nav .brand span{{color:var(--muted);font-weight:400}}
a{{color:var(--amber2);text-decoration:none}}
a:hover{{border-bottom:1px dashed var(--amber2)}}
h1{{color:var(--amber);font-size:clamp(1.5rem,4vw,2.2rem);line-height:1.2;margin:2rem 0 1rem;letter-spacing:-.02em}}
h2{{color:var(--amber);font-size:1.15rem;margin:2.4rem 0 1rem;letter-spacing:-.02em}}
h3{{color:var(--amber2);font-size:1rem;margin:1.8rem 0 .6rem}}
p{{margin:0 0 1rem}}
code{{color:var(--amber2);font-size:.92em}}
pre{{background:var(--bg2);border:1px solid var(--border2);border-radius:8px;
     padding:1rem 1.2rem;overflow-x:auto;margin:0 0 1.2rem;font-size:.82rem;line-height:1.7;color:var(--dim)}}
pre code{{color:var(--dim)}}
table{{border-collapse:collapse;width:100%;margin:0 0 1.4rem;font-size:.85rem}}
th,td{{border:1px solid var(--border2);padding:.5rem .7rem;text-align:left;vertical-align:top}}
th{{color:var(--amber);font-weight:600}}
blockquote{{border-left:2px solid var(--amber);padding-left:1rem;color:var(--dim);margin:0 0 1rem}}
ul,ol{{margin:0 0 1rem 1.4rem}}
li{{margin:.25rem 0}}
hr{{border:none;border-top:1px solid var(--border2);margin:2rem 0}}
.meta{{color:var(--muted);font-size:.85rem;margin:0 0 2rem}}
footer{{margin-top:4rem;padding-top:1.5rem;border-top:1px solid var(--border2);color:var(--muted);font-size:.8rem}}
</style>
</head>
<body>
<main>
<nav>
  <a class="brand" href="/">KESSLER <span>/ reports</span></a>
  <a href="/">home</a>
</nav>
<article class="prose">
{body}
</article>
<footer>
  Published by Kessler (AtlasNex). Findings are measured, dated and scoped; nothing here is a
  certification. · <a href="mailto:security@atlasnex.com">security@atlasnex.com</a>
</footer>
</main>
</body>
</html>
"""


def render(md_path: Path, slug: str, title: str) -> Path:
    text = md_path.read_text(encoding="utf-8")
    # leading <!-- ... --> blocks are internal notes about the publish copy — never render them
    text = re.sub(r"^\s*(<!--.*?-->\s*)+", "", text, flags=re.S)
    body = markdown.markdown(text, extensions=["tables", "fenced_code"])
    out = OUT / slug
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(PAGE.format(title=title, body=body), encoding="utf-8")
    return out


def main() -> int:
    for src, slug, title in PAGES:
        out = render(ROOT / src, slug, title)
        print(f"built {out.relative_to(ROOT)} ({out.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
