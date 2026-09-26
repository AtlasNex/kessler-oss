#!/usr/bin/env bash
# Fetch and install the third-party red teaming tools into vendor/.
# Idempotent: safe to re-run. Follows D-003 (gitignored vendor) and D-004/D-010 (per-tool envs).
#
# WHY ONE ENVIRONMENT PER TOOL — there is no shared resolution, and this was verified, not assumed:
#   garak 0.17.0 requires datasets>=3.0.0,<4.0
#   pyrit 1.1.0  requires datasets>=4.8.0          <-- mutually exclusive with garak
#   deepteam     requires click<8.4.0 via deepeval
#   pyrit pulls  click 8.5.0                       <-- mutually exclusive with deepteam
#   huggingface-hub requires click>=8.4.2          <-- contradicts deepeval
# Any single environment silently breaks a tool. So: three venvs, one per family.
#
# WINDOWS NOTE: native Python cannot read MSYS paths like /e/Projects/... . Everything handed
# to python/git is converted to a native path with cygpath -m first, or venv creation silently
# produces nothing.
set -euo pipefail

HERE_MSYS="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# native Windows path for anything a native binary must open
if command -v cygpath >/dev/null 2>&1; then
  HERE="$(cygpath -m "$HERE_MSYS")"
else
  HERE="$HERE_MSYS"
fi
V="$HERE/vendor"
PY="${PYTHON:-python}"
mkdir -p "$V"

echo "root: $HERE"

clone() {
  if [ -d "$V/$2/.git" ]; then
    echo "  [=] $2 already cloned"
  else
    echo "  [+] cloning $2"
    git clone --depth 1 -q "https://github.com/$1.git" "$V/$2"
  fi
}

# locate the interpreter inside a venv (Windows layout first, POSIX second).
# -f not -x: MSYS reports .exe executability inconsistently.
venv_py() {
  if [ -f "$1/Scripts/python.exe" ]; then echo "$1/Scripts/python.exe"
  elif [ -f "$1/bin/python" ];     then echo "$1/bin/python"
  else echo ""; fi
}

make_env() {
  local dir="$1" name="$2"
  if [ -z "$(venv_py "$dir")" ]; then
    echo "  [+] creating $name"
    "$PY" -m venv "$dir"
  else
    echo "  [=] $name exists"
  fi
  local p; p="$(venv_py "$dir")"
  if [ -z "$p" ]; then
    echo "  FAIL could not create a usable venv at $dir" >&2
    exit 1
  fi
  "$p" -m pip install -q --upgrade pip
  echo "$p"
}

echo "== clones =="
clone Tencent/AI-Infra-Guard       ai-infra-guard
clone apisec-inc/mcp-audit         mcp-audit
clone cisco-ai-defense/mcp-scanner mcp-scanner
clone Awarexone/Agentic-Bug-Hunter bughunter

echo "== env: garak =="
GARAK_PY="$(make_env "$V/venv-garak" venv-garak | tail -1)"
"$GARAK_PY" -m pip install -q "garak==0.17.0"

echo "== env: pyrit =="
PYRIT_PY="$(make_env "$V/venv-pyrit" venv-pyrit | tail -1)"
"$PYRIT_PY" -m pip install -q pyrit

echo "== env: deepteam (+ its deepeval/click pins, + sentry_sdk it forgets to declare) =="
DT_PY="$(make_env "$V/venv-deepteam" venv-deepteam | tail -1)"
"$DT_PY" -m pip install -q deepteam sentry_sdk

echo
echo "== verification =="
fail=0
"$GARAK_PY" -c "import garak, importlib.metadata as m; print('  garak   ', m.version('garak'))" || { echo "  FAIL garak"; fail=1; }
"$PYRIT_PY" -c "import pyrit, importlib.metadata as m; print('  pyrit   ', m.version('pyrit'))" || { echo "  FAIL pyrit"; fail=1; }
"$DT_PY"    -c "import deepteam, importlib.metadata as m; print('  deepteam', m.version('deepteam'))" || { echo "  FAIL deepteam"; fail=1; }
# the conflict is *supposed* to exist across envs; prove it does NOT exist within one
"$GARAK_PY" -c "import datasets; assert datasets.__version__.startswith('3.'), datasets.__version__; print('  garak datasets pin held:', datasets.__version__)" || fail=1
for d in ai-infra-guard mcp-audit mcp-scanner bughunter; do
  [ -d "$V/$d" ] && echo "  $d present" || { echo "  FAIL $d missing"; fail=1; }
done

echo
[ "$fail" -ne 0 ] && { echo "RESULT: FAILED — see above"; exit 1; }
echo "RESULT: ALL TOOLS PRESENT AND IMPORTABLE"
echo "vendor/ is gitignored — re-run this script after a fresh clone."
