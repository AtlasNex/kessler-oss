"""K9: the Konsole door. Adds /console/ to the nav on all three nav sources and to the
deploy chain (before the og pass so its card generates)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
K = ROOT
DEPLOY = Path("E:/Sanjay Files/StartUp/AtlasNex/atlasnex-hq/scripts/deploy_kessler_site.sh")

NAV_OLD = '<a href="/#shell">Try it</a>'
NAV_NEW = '<a href="/#shell">Try it</a><a href="/console/">Console</a>'

for rel in ("site/index.html", "scripts/build-reports.py", "site/serve.py"):
    p = K / rel
    t = p.read_text(encoding="utf-8")
    n = t.count(NAV_OLD)
    if n != 1:
        raise SystemExit(f"nav anchor {rel}: {n}")
    t = t.replace(NAV_OLD, NAV_NEW, 1)
    p.write_text(t, encoding="utf-8", newline="")
    print("nav door added:", rel)

d = DEPLOY.read_text(encoding="utf-8")
line = "(cd \"$K\" && uv run --no-project --with markdown python scripts/build-portal.py) || { echo \"portal build failed\"; exit 1; }"
if "build-console.py" in d:
    print("deploy chain already carries build-console")
else:
    n = d.count(line)
    if n != 1:
        raise SystemExit(f"deploy anchor: {n}")
    add = line + "\n(cd \"$K\" && python scripts/build-console.py) || { echo \"console build failed\"; exit 1; }"
    d = d.replace(line, add, 1)
    DEPLOY.write_text(d, encoding="utf-8", newline="")
    print("deploy chain: build-console.py added after portal")

print("K9 console door done")
