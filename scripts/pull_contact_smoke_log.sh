#!/usr/bin/env bash
set -euo pipefail

if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
  echo "Do not source this script; execute it as a command." >&2
  return 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

ENV_NAME="${1:-}"
REMOTE_ROOT="${2:-/workspace/robot-contact-assembly}"
PULL_DIR="${3:-${REPO_ROOT}/artifacts/launchable_logs/pulled_contact_smoke}"
REMOTE_LOG="${REMOTE_ROOT}/artifacts/launchable_logs/contact_physics_smoke.log"
RUN_ID="$(date -u +"%Y-%m-%dT%H-%M-%SZ")"
RSYNC_BIN="${RCA_RSYNC_BIN:-rsync}"
ARCHIVE_LOG="${RCA_CONTACT_SMOKE_ARCHIVE_PATH:-}"

fail() {
  echo "[contact-smoke-pull] BLOCKED: $*" >&2
  exit 2
}

if [[ -z "${ENV_NAME}" ]]; then
  fail "usage: scripts/pull_contact_smoke_log.sh <env-name> [remote-root] [pull-dir]"
fi

RCA_REMOTE_OPERATION_PURPOSE=contact_physics_smoke "${SCRIPT_DIR}/remote_operation_preflight.sh"

mkdir -p "${PULL_DIR}"
PULL_DIR="$(cd "${PULL_DIR}" && pwd)"
PULLED_LOG="${PULL_DIR}/contact_physics_smoke_${ENV_NAME}_${RUN_ID}.log"

echo "[contact-smoke-pull] remote log: ${ENV_NAME}:${REMOTE_LOG}"
echo "[contact-smoke-pull] pulled log: ${PULLED_LOG}"
"${RSYNC_BIN}" -av "${ENV_NAME}:${REMOTE_LOG}" "${PULLED_LOG}"

echo "[contact-smoke-pull] validating and archiving pulled log"
if [[ -n "${ARCHIVE_LOG}" ]]; then
  "${SCRIPT_DIR}/archive_contact_smoke_log.sh" "${PULLED_LOG}" "${ARCHIVE_LOG}"
else
  "${SCRIPT_DIR}/archive_contact_smoke_log.sh" "${PULLED_LOG}"
fi
echo "[contact-smoke-pull] PASS: pulled, archived, and validated contact-smoke log"
