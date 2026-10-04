"""K4/S-2: capture real CLI --help outputs and install the recorded shell section on index.html.
Idempotent guard: refuses if the section already exists (this is a one-shot surgery; rerun on a
fresh index)."""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
idx = ROOT / "site" / "index.html"
t = idx.read_text(encoding="utf-8")
if 'id="shell"' in t:
    raise SystemExit("already applied: index.html carries the shell section")

CMDS = {
    "help": ["--help"],
    "run --help": ["run", "--help"],
    "plan --help": ["plan", "--help"],
    "report --help": ["report", "--help"],
    "bench --help": ["bench", "--help"],
    "verify-capsule --help": ["verify-capsule", "--help"],
    "gate --help": ["gate", "--help"],
    "baseline --help": ["baseline", "--help"],
    "threat-index --help": ["threat-index", "--help"],
}
ansi = re.compile(r"\x1b\[[0-9;]*m")
cmds = {}
for name, argv in CMDS.items():
    r = subprocess.run([sys.executable, "-m", "kessler.cli"] + argv, cwd=ROOT,
                       capture_output=True, text=True, timeout=60,
                       env={**__import__("os").environ, "NO_COLOR": "1"})
    out = ansi.sub("", (r.stdout or r.stderr).strip())
    if not out.startswith("usage:"):
        raise SystemExit(f"capture failed for {name!r}: {out[:120]!r}")
    cmds[name] = out
    print(f"captured {name} ({len(out)} chars)")

island = json.dumps({"cmds": cmds}, sort_keys=True)
assert "</" not in island, "island carries a closing tag; escape needed"

section = (
    '<section class="ax-white ax-section" id="shell"><div class="ax-wrap">\n'
    '<span class="ax-mono ax-kicker">Try it</span>\n'
    '<h2>The harness answers for itself.</h2>\n'
    '<p class="ax-sub" style="max-width:62ch">Type a real command. The output is a recording '
    'captured from the open-source kernel at build time - commands are real; nothing here runs '
    'on a server, and where a command needs a target the help text says so instead of inventing '
    'a run.</p>\n'
    '<div class="kx-shell" data-shell>\n'
    '<div class="bar"><i></i><i></i><i></i><span>recorded output - kessler by atlasnex</span></div>\n'
    '<div class="kx-sh-log" role="log" aria-live="polite" aria-label="Shell transcript"></div>\n'
    '<form class="kx-sh-form" autocomplete="off"><span class="kx-sh-prompt">kessler&gt;</span>'
    '<input class="kx-sh-in" aria-label="Type a kessler command" spellcheck="false">'
    '<button class="kx-copy kx-sh-run" type="submit">run</button></form>\n'
    '</div>\n'
    '<script type="application/json" id="kx-shell-data">' + island + "</script>\n"
    "</div></section>\n\n"
)

# nav link
old_nav = '<a href="#method">Method</a><a href="pricing/">Pricing</a>'
new_nav = '<a href="#method">Method</a><a href="#shell">Try it</a><a href="pricing/">Pricing</a>'
assert t.count(old_nav) == 1, "nav anchor"
t = t.replace(old_nav, new_nav, 1)

# section before #measurement
old_anchor = '<section class="ax-white ax-section" id="measurement">'
assert t.count(old_anchor) == 1, "measurement anchor"
t = t.replace(old_anchor, section + old_anchor, 1)

idx.write_text(t, encoding="utf-8", newline="")
print(f"index.html: shell section installed ({len(section)} bytes, 9 commands)")
