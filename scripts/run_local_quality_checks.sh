#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${REPO_ROOT}"
export PYTHONDONTWRITEBYTECODE=1

echo "[local-quality] repo=${REPO_ROOT}"

echo "[local-quality] contact geometry constants"
python3 scripts/check_contact_geometry_constants.py

echo "[local-quality] project structure"
python3 scripts/check_project_structure.py

echo "[local-quality] contact physics wiring"
python3 scripts/check_contact_physics_wiring.py

echo "[local-quality] project policy compliance"
python3 scripts/check_project_policy_compliance.py

echo "[local-quality] Brev support evidence consistency"
python3 scripts/check_brev_support_evidence.py

echo "[local-quality] success variation batch plan"
python3 scripts/check_success_variation_batch_plan.py

echo "[local-quality] local gate behavior tests"
python3 scripts/test_local_gates.py

echo "[local-quality] python syntax for tracked and untracked files"
python_list_file="$(mktemp)"
shell_list_file="$(mktemp)"
cleanup() {
  rm -f "${python_list_file}" "${shell_list_file}"
}
trap cleanup EXIT

{
  git ls-files --cached '*.py'
  git ls-files --others --exclude-standard '*.py'
} | sort -u > "${python_list_file}"
if [[ -s "${python_list_file}" ]]; then
  python3 - "${python_list_file}" <<'PY'
from __future__ import annotations

import pathlib
import sys

list_path = pathlib.Path(sys.argv[1])
failed = False
for raw_path in list_path.read_text(encoding="utf-8").splitlines():
    path = pathlib.Path(raw_path)
    if not raw_path:
        continue
    try:
        source = path.read_text(encoding="utf-8")
        compile(source, str(path), "exec")
    except SyntaxError as exc:
        failed = True
        print(f"{path}:{exc.lineno}:{exc.offset}: SyntaxError: {exc.msg}", file=sys.stderr)
        if exc.text:
            print(exc.text.rstrip(), file=sys.stderr)
    except UnicodeDecodeError as exc:
        failed = True
        print(f"{path}: UnicodeDecodeError: {exc}", file=sys.stderr)
if failed:
    raise SystemExit(1)
PY
fi

echo "[local-quality] shell syntax for scripts/*.sh"
find scripts -maxdepth 1 -type f -name '*.sh' -print | sort > "${shell_list_file}"
while IFS= read -r shell_file; do
  [[ -z "${shell_file}" ]] && continue
  bash -n "${shell_file}"
done < "${shell_list_file}"

echo "[local-quality] git diff whitespace"
git diff --check

echo "[local-quality] generated cache hygiene"
generated_cache="$(
  find . -path ./.git -prune -o \
    \( -name '__pycache__' -type d -o -name '*.pyc' -type f -o -name '.DS_Store' -type f -o -name '*.egg-info' -type d \) \
    -print | sort
)"
if [[ -n "${generated_cache}" ]]; then
  echo "[local-quality] generated cache files/directories are present; remove them before packaging:" >&2
  printf '%s\n' "${generated_cache}" >&2
  exit 1
fi

echo "[local-quality] passed"
