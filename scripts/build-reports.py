"""Render docs/publish/*.md to the site's report pages (PLAN-v4 Phase 1).

The publish drafts stay canonical Markdown in the repo; this script renders them onto the
landing site's chrome (the AtlasNex house design system ui/v1, like site/index.html) and writes
site/reports/<slug>.html. Uses the `markdown` package (build-time only; the C-2 stdlib-only
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
     "Teardown 01: EchoLeak (CVE-2025-32711)"),
    ("docs/publish/03-mcp-vetting-method.md", "03-mcp-vetting-method.html",
     "How we vet an MCP server: three checks, each with named evidence"),
]

PAGE = """<!doctype html>
<html lang="en" data-product="kessler">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} | Kessler by AtlasNex</title>
<meta name="description" content="Published work from Kessler by AtlasNex: adversarial testing for agentic AI.">
<meta name="theme-color" content="#060E22">
<link rel="icon" href="https://atlasnex.com/favicon.svg" type="image/svg+xml">
<link rel="stylesheet" href="https://atlasnex.com/ui/v1/atlasnex-ui.css">
<style>
.kx-brand{{display:flex;align-items:baseline;gap:10px;text-decoration:none;color:var(--ax-star)}}
.kx-brand b{{font-family:var(--ax-display);font-size:1.15rem;letter-spacing:-.02em}}
.kx-brand span{{color:var(--ax-lunar);font-size:.85rem}}
.ax-prose{{padding:48px 0 72px}}
.ax-prose h1{{font-size:clamp(1.9rem,4.5vw,2.8rem)}}
.ax-prose a{{color:var(--ax-beacon-ink)}}
.ax-prose pre{{background:var(--ax-midnight);color:var(--ax-mist);border-radius:10px;padding:14px 16px;overflow-x:auto;font-size:.82rem;line-height:1.65}}
.ax-prose pre code{{background:none;padding:0;color:inherit}}
.ax-prose table{{border-collapse:collapse;width:100%;font-size:.9rem;background:var(--ax-paper);border:1px solid var(--ax-line);display:block;overflow-x:auto}}
.ax-prose th,.ax-prose td{{text-align:left;padding:9px 12px;border-bottom:1px solid var(--ax-line);vertical-align:top}}
.ax-prose th{{font-family:var(--ax-mono);font-weight:500;font-size:.72rem;letter-spacing:.06em;text-transform:uppercase;color:var(--ax-muted);background:#FBFAF7}}
.ax-prose blockquote{{border-left:3px solid var(--ax-beacon);margin:0 0 1em;padding-left:1em;color:var(--ax-muted)}}
.ax-prose hr{{border:0;border-top:1px solid var(--ax-line);margin:2em 0}}
</style>
</head>
<body>
<a class="ax-skip" href="#main">Skip to content</a>
<header class="ax-header"><div class="ax-wrap">
<a class="kx-brand" href="/"><b>Kessler</b><span>by AtlasNex</span></a>
<nav class="ax-nav" aria-label="Main"><a href="/#writeups">Writeups</a><a class="ax-btn primary" href="https://github.com/AtlasNex/kessler-oss">Get the harness</a></nav>
</div></header>
<main id="main" class="ax-light"><div class="ax-wrap">
<article class="ax-prose">
{body}
</article>
</div></main>
<footer class="ax-footer"><div class="ax-wrap">
<div class="ax-fine" style="border:0;margin:0;padding:0">Published by Kessler by AtlasNex. Findings are measured, dated and scoped; nothing here is a
  certification. <a href="mailto:security@atlasnex.com">security@atlasnex.com</a> · <a href="https://atlasnex.com">atlasnex.com</a></div>
</div></footer>
</body>
</html>
"""


def no_em_dash(text: str) -> str:
    """House rule: no em dashes in shipped copy. A paired dash is a parenthetical; a single one
    becomes a comma before a conjunction and a colon otherwise."""
    em = "\u2014"
    text = re.sub(rf" {em} ([^{em}\n.]{{1,120}}?) {em} ", r" (\1) ", text)
    text = re.sub(rf" {em} (?=(and|but|or|so|which|not|in fact)\b)", ", ", text)
    return text.replace(f" {em} ", ": ").replace(em, ": ")


def render(md_path: Path, slug: str, title: str) -> Path:
    text = no_em_dash(md_path.read_text(encoding="utf-8"))
    # leading <!-- ... --> blocks are internal notes about the publish copy; never render them
    text = re.sub(r"^\s*(<!--.*?-->\s*)+", "", text, flags=re.S)
    body = markdown.markdown(text, extensions=["tables", "fenced_code"])
    out = OUT / slug
    out.parent.mkdir(parents=True, exist_ok=True)
    html = PAGE.format(title=title, body=body)
    if "\u2014" in html:
        raise SystemExit(f"{slug}: em dash survived; fix the source")
    out.write_text(html, encoding="utf-8")
    return out


def main() -> int:
    for src, slug, title in PAGES:
        out = render(ROOT / src, slug, title)
        print(f"built {out.relative_to(ROOT)} ({out.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
