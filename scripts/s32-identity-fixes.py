"""s32 identity + dash fixes (public sample artifacts must carry no personal name; shipped
copy carries no em dash). Applied atomically with anchor assertions.

1. run-selftest/a7-engagement.json: testers -> entity credit ("AtlasNex", the convention the
   test fixtures already use). ALL public renders (report/board/attestation/capsule) derive
   from this field, so this is the one source fix; regen follows.
2. site/security.txt + .well-known/security.txt: em dash in the header comment -> hyphen.
3. site/serve.py: 6 em-dash literals (empty-cell glyphs + a comment) -> hyphen, matching the
   register page's normalization convention for shipped copy.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

EDITS: list[tuple[str, str, str, int]] = []   # path, old, new, expected_count


def E(path, old, new, n=1):
    EDITS.append((path, old, new, n))


E("run-selftest/a7-engagement.json", '"R.U. Sanjay Kumar"', '"AtlasNex"')
E("site/security.txt",
  "\u2014 security contact and disclosure policy",
  "- security contact and disclosure policy")
E("site/.well-known/security.txt",
  "\u2014 security contact and disclosure policy",
  "- security contact and disclosure policy")

EM = "\u2014"


def main() -> int:
    buffers: dict[str, str] = {}
    for path, old, new, n in EDITS:
        t = (ROOT / path).read_text(encoding="utf-8")
        cnt = t.count(old)
        if cnt != n:
            raise SystemExit(f"ANCHOR FAIL: {path}: {cnt} matches (want {n}) for {old[:80]!r}")
        if not all(ord(c) < 128 for c in new):
            raise SystemExit(f"NON-ASCII in new text for {path}")
        buffers[path] = t.replace(old, new)
    # serve.py: replace every em dash (asserted count first)
    sp = "site/serve.py"
    t = (ROOT / sp).read_text(encoding="utf-8")
    cnt = t.count(EM)
    if cnt != 6:
        raise SystemExit(f"serve.py: {cnt} em dashes (want 6) - inspect before replacing")
    buffers[sp] = t.replace(EM, "-")
    for path, text in buffers.items():
        (ROOT / path).write_text(text, encoding="utf-8", newline="")
        print(f"fixed {path}")
    print("identity/dash fixes applied:", len(buffers), "files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
