"""K3 misc edits (asserted, atomic): doors + sample-packet through the shared writer,
pricing ladder-glance section, serve.py og+script, index.html og+version bumps,
budget cap, deploy chain additions."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
H = Path("E:/Sanjay Files/StartUp/AtlasNex/atlasnex-hq")


def edit(path: Path, pairs: list[tuple[str, str]]) -> int:
    t = path.read_text(encoding="utf-8")
    for old, new in pairs:
        cnt = t.count(old)
        if cnt != 1:
            raise SystemExit(f"ANCHOR FAIL {path.name}: {cnt} for {old[:80]!r}")
        t = t.replace(old, new, 1)
    path.write_text(t, encoding="utf-8", newline="")
    print(f"edited {path.name}")
    return len(pairs)


# 1) doors -> shared writer (og slugs start-r1 / start-recheck)
edit(ROOT / "scripts" / "build-doors.py", [(
    '    html = PAGE.format(title=title, body=markdown.markdown(src, extensions=["tables"]))',
    '    html = _br.html_for(title, markdown.markdown(src, extensions=["tables"]),\n'
    '                         og="start-" + d, kind="Commission")',
)])

# 2) sample-packet views -> shared writer (one og card for all sample views)
edit(ROOT / "scripts" / "build-sample-packet.py", [(
    '        _br.PAGE.format(title=f"{_name} (sample) | Kessler by AtlasNex", body=_body),',
    '        _br.html_for(f"{_name} (sample) | Kessler by AtlasNex", _body,\n'
    '                     og="sample", kind="Sample artifact"),',
)])

# 3) pricing: ladder-at-a-glance + reach/limits, derived from the OFFER block
edit(ROOT / "scripts" / "build-pricing-page.py", [(
    'block = "\\n".join(add_inr(ln) if (ln.startswith("|") and "$" in ln) else ln\n'
    '                  for ln in block.splitlines())',
    'block = "\\n".join(add_inr(ln) if (ln.startswith("|") and "$" in ln) else ln\n'
    '                  for ln in block.splitlines())\n'
    '\n'
    '# --- the ladder at a glance (S-14): bars + implied rate, parsed from OFFER itself ---\n'
    'LADDER = []\n'
    'for m in re.finditer(r"^\\| ([^|]+?) \\| \\*\\*\\$([\\d,]+)[^|]*\\*\\*[^|]* \\| [^|]*?<= (\\d+) h \\|",\n'
    '                     block, re.M):\n'
    '    LADDER.append((m.group(1).strip(), int(m.group(2).replace(",", "")), int(m.group(3))))\n'
    'assert len(LADDER) >= 4, f"ladder parse found {len(LADDER)} rows"\n'
    '_names = " ".join(nm for nm, _, _ in LADDER)\n'
    'for _must in ("R1 Light", "R2 Standard", "R3 Multi-agent"):\n'
    '    assert _must in _names, f"missing {_must} in ladder parse"\n'
    'assert "one retest round" in block and "blast-radius" in block, "reach copy drifted"\n'
    'for _nm, _usd, _h in LADDER:\n'
    '    assert _usd / _h >= 150, f"floor rule violated: {_nm} {_usd}/{_h}"\n'
    '_maxh = max(h for _, _, h in LADDER)\n'
    '_bars = "".join(\n'
    '    f\'<tr><td>{nm}</td><td class="kx-nowrap">${usd:,} <span class="kx-ctext">({_lakh(usd)})'
    '</span></td>\'\n'
    '    f\'<td class="kx-nowrap"><span class="kx-bar"><i style="width:{h / _maxh * 100:.1f}%">'
    '</i></span> {h}h cap</td>\'\n'
    '    f\'<td class="kx-nowrap">${usd / h:,.0f}/h</td></tr>\'\n'
    '    for nm, usd, h in LADDER)\n'
    'glance = (\n'
    '    "## The ladder at a glance\\n\\n"\n'
    '    "<table>\\n<thead><tr><th>Rung</th><th>Price</th><th>Hours cap</th>"\n'
    '    "<th>Implied rate</th></tr></thead>\\n<tbody>" + _bars + "</tbody></table>\\n\\n"\n'
    '    f"*Bars scale to the largest cap ({_maxh}h). The implied-rate column is the floor rule "\n'
    '    "working: no rung prices below $150/h.*\\n\\n"\n'
    '    "## Reach and limits, per rung\\n\\n"\n'
    '    "<table>\\n<thead><tr><th>Rung</th><th>Reaches for</th><th>Does not include</th></tr>"\n'
    '    "</thead>\\n<tbody>\\n"\n'
    '    "<tr><td>R1 Light</td><td>One agent; intervalled ASR; the findings table; the coverage "\n'
    '    "denominator; attestation letter + proof kit</td><td>multi-agent estate; blast-radius "\n'
    '    "analysis; MCP assessment; a retest round (the standalone retest lane is separate)"\n'
    '    "</td></tr>\\n"\n'
    '    "<tr><td>R2 Standard</td><td>Everything in R1; full ASI coverage; one retest round</td>"\n'
    '    "<td>the estate-wide blast radius and MCP dossier of R3; continuous monitoring (R4)"\n'
    '    "</td></tr>\\n"\n'
    '    "<tr><td>R3 Multi-agent</td><td>The estate: full blast-radius, MCP assessment, estate "\n'
    '    "attestation; the drill, cascade and baseline comparator ship inside R3</td>"\n'
    '    "<td>anything past the hours cap without a written change order; ongoing monitoring"\n'
    '    "</td></tr>\\n</tbody></table>\\n")',
), (
    "\n{block}\n\n## Why the hours are capped and the scope is not",
    "\n{block}\n\n{glance}\n\n## Why the hours are capped and the scope is not",
)])

# 4) serve.py: kx.css v3 + og block + kx.js v3 (all page templates carry </body>)
edit(ROOT / "site" / "serve.py", [(
    '<link rel="stylesheet" href="/kx.css?v=2">',
    '<link rel="stylesheet" href="/kx.css?v=3">\n'
    '<meta property="og:site_name" content="Kessler by AtlasNex">\n'
    '<meta property="og:title" content="Kessler by AtlasNex">\n'
    '<meta property="og:image" content="https://kessler.atlasnex.com/og/home.png">\n'
    '<meta name="twitter:card" content="summary_large_image">',
), (
    "</body>",
    '<script src="/kx.js?v=3" defer></script>\n</body>',
)])

# 5) index.html: og block + v3 bumps
edit(ROOT / "site" / "index.html", [(
    '<meta name="description" content="Kessler attacks AI agents that hold tools, memory and '
    'credentials, and ships the number with its interval, its evidence chain and a verifier. '
    'Never a yes or no.">',
    '<meta name="description" content="Kessler attacks AI agents that hold tools, memory and '
    'credentials, and ships the number with its interval, its evidence chain and a verifier. '
    'Never a yes or no.">\n'
    '<meta property="og:site_name" content="Kessler by AtlasNex">\n'
    '<meta property="og:type" content="website">\n'
    '<meta property="og:title" content="Kessler: adversarial measurement you can check.">\n'
    '<meta property="og:image" content="https://kessler.atlasnex.com/og/home.png">\n'
    '<meta name="kx:kind" content="Adversarial measurement for agentic AI">\n'
    '<meta name="twitter:card" content="summary_large_image">',
), (
    '<link rel="stylesheet" href="/kx.css?v=2">',
    '<link rel="stylesheet" href="/kx.css?v=3">',
), (
    '<script src="/kx.js?v=2" defer></script>',
    '<script src="/kx.js?v=3" defer></script>',
)])

# 6) budget cap for kx.js growth
edit(ROOT / "scripts" / "check-site-budget.py", [(
    '    ("kx.js raw", SITE / "kx.js", 12 * 1024),',
    '    ("kx.js raw", SITE / "kx.js", 16 * 1024),',
)])

# 7) deploy chain: register + doors + playground + og after the reports build
edit(H / "scripts" / "deploy_kessler_site.sh", [(
    '(cd "$K" && uv run --no-project --with markdown python scripts/build-reports.py) || '
    '{ echo "report build failed"; exit 1; }',
    '(cd "$K" && uv run --no-project --with markdown python scripts/build-reports.py) || '
    '{ echo "report build failed"; exit 1; }\n'
    '(cd "$K" && uv run --no-project --with markdown python scripts/build-register-page.py) || '
    '{ echo "register build failed"; exit 1; }\n'
    '(cd "$K" && uv run --no-project --with markdown python scripts/build-doors.py) || '
    '{ echo "doors build failed"; exit 1; }\n'
    '(cd "$K" && uv run --no-project --with markdown python scripts/build-playground-page.py) || '
    '{ echo "playground build failed"; exit 1; }\n'
    '(cd "$K" && python scripts/build-og.py) || echo "warning: og render skipped"',
)])

print("K3 misc edits applied")
