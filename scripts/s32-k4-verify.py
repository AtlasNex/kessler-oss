"""K4/S-3: install the in-browser verify widget on the /verify/ page (serve.py)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
p = ROOT / "site" / "serve.py"
t = p.read_text(encoding="utf-8")
if "data-kx-verify" in t:
    raise SystemExit("already applied: serve.py carries the verify widget")


def swap(old: str, new: str) -> None:
    global t
    cnt = t.count(old)
    if cnt != 1:
        raise SystemExit(f"ANCHOR FAIL ({cnt}): {old[:90]!r}")
    t = t.replace(old, new, 1)


WIDGET = '''VERIFY_WIDGET = """
<div class="kx-verify" data-kx-verify data-capsule="__CAPSULE__">
<h3>Verify it in your browser</h3>
<p class="kx-note">Same arithmetic the CLI runs: canonical JSON, the SHA-256 chain over every
record, and the Wilson interval recomputed from the attempt rows - executed locally on the
capsule file itself. The open-source CLI remains the source of truth.</p>
<p><button type="button" class="ax-btn primary" data-kx-verify-run>Recompute the chain</button>
<span class="kx-count" data-kx-verify-status aria-live="polite"></span></p>
<div class="kx-verify-links" data-kx-verify-links></div>
<div class="kx-verify-detail" data-kx-verify-detail></div>
<p><button type="button" class="kx-copy" data-kx-verify-tamper>simulate tampering</button>
<span class="kx-note">(mutates a copy in your browser only; the published file is never
touched)</span></p>
<pre class="kx-verify-cmd"><code>kessler verify-capsule __CAPNAME__</code></pre>
</div>
"""


'''

swap("def verify_page() -> str:", WIDGET + "def verify_page() -> str:")

swap(
    "    if not rows:\n"
    "        rows = ['<p class=\"kx-note\">No capsules anchored yet.</p>']\n",
    "    if not rows:\n"
    "        rows = ['<p class=\"kx-note\">No capsules anchored yet.</p>']\n"
    "    _caps = (sorted(f.name for f in VERIFY_DIR.glob('*.capsule.json'))\n"
    "             if VERIFY_DIR.is_dir() else [])\n"
    "    widget = (VERIFY_WIDGET.replace('__CAPSULE__', '/verify/' + _caps[0])\n"
    "              .replace('__CAPNAME__', _caps[0])) if _caps else ''\n",
)

swap(
    "            + f'<div class=\"kx-board\">{\"\".join(rows)}</div>\\n'\n",
    "            + widget\n"
    "            + f'<div class=\"kx-board\">{\"\".join(rows)}</div>\\n'\n",
)

p.write_text(t, encoding="utf-8", newline="")
print("serve.py: verify widget installed")
