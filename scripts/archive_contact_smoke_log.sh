#!/usr/bin/env bash
set -euo pipefail

if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
  echo "Do not source this script; execute it as a command." >&2
  return 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

SOURCE_LOG="${1:-}"
DEST_LOG="${2:-${REPO_ROOT}/artifacts/launchable_logs/contact_physics_smoke.log}"

fail() {
  echo "[contact-smoke-archive] BLOCKED: $*" >&2
  exit 2
}

if [[ -z "${SOURCE_LOG}" ]]; then
  fail "usage: scripts/archive_contact_smoke_log.sh <source-log> [dest-log]"
fi

if [[ ! -f "${SOURCE_LOG}" ]]; then
  fail "source log does not exist: ${SOURCE_LOG}"
fi

SOURCE_LOG="$(cd "$(dirname "${SOURCE_LOG}")" && pwd)/$(basename "${SOURCE_LOG}")"
DEST_DIR="$(dirname "${DEST_LOG}")"
mkdir -p "${DEST_DIR}"
DEST_DIR="$(cd "${DEST_DIR}" && pwd)"
DEST_LOG="${DEST_DIR}/$(basename "${DEST_LOG}")"

echo "[contact-smoke-archive] validating source log before archive:"
echo "  ${SOURCE_LOG}"
python3 "${SCRIPT_DIR}/check_phase2_contact_gate.py" --log "${SOURCE_LOG}"

if [[ "${SOURCE_LOG}" != "${DEST_LOG}" ]]; then
  tmp_log="${DEST_LOG}.tmp.$$"
  cp "${SOURCE_LOG}" "${tmp_log}"
  mv "${tmp_log}" "${DEST_LOG}"
fi

echo "[contact-smoke-archive] archived contact-smoke log:"
echo "  ${DEST_LOG}"
python3 "${SCRIPT_DIR}/check_phase2_contact_gate.py" --log "${DEST_LOG}"
echo "[contact-smoke-archive] PASS: canonical contact-smoke evidence is archived and valid"
