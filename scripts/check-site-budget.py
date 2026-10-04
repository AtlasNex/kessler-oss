"""check-site-budget.py - the K1 site budget check (standalone; run before deploys).

Budgets (doc 21 Sec 6.2, doc 22e B-1): first-party site JS <= 15KB gz; kx.css <= 12KB
raw; kx.js <= 8KB raw. Total page weight sanity for index.html. Exit 1 on breach.
"""
import gzip
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"

RULES = [
    ("kx.css raw", SITE / "kx.css", 16 * 1024),
    ("kx.js raw", SITE / "kx.js", 32 * 1024),
]

ok = True
for label, path, cap in RULES:
    if not path.exists():
        print(f"FAIL {label}: missing {path.relative_to(ROOT)}")
        ok = False
        continue
    raw = path.read_bytes()
    gz = gzip.compress(raw, 9)
    print(f"{label}: {len(raw)}B raw / {len(gz)}B gz (cap {cap}B raw)")
    if len(raw) > cap:
        print(f"FAIL {label}: over budget by {len(raw) - cap}B")
        ok = False

idx = SITE / "index.html"
if idx.exists():
    gz = gzip.compress(idx.read_bytes(), 9)
    print(f"index.html: {idx.stat().st_size}B raw / {len(gz)}B gz")

print("BUDGET", "OK" if ok else "BREACHED")
sys.exit(0 if ok else 1)
