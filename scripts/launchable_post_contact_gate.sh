#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="${1:-${RCA_LAUNCHABLE_REPO_DIR:-/workspace/robot-contact-assembly}}"
PYTHON_BIN="${RCA_GATE_PYTHON:-python3}"

if [[ ! -f "${REPO_DIR}/scripts/check_phase2_contact_gate.py" ]]; then
  echo "[launchable-post-contact-gate] BLOCKED: missing ${REPO_DIR}/scripts/check_phase2_contact_gate.py" >&2
  exit 2
fi

set +e
gate_output="$("${PYTHON_BIN}" "${REPO_DIR}/scripts/check_phase2_contact_gate.py" --repo-root "${REPO_DIR}" 2>&1)"
gate_status=$?
set -e
printf '%s\n' "${gate_output}"

if [[ "${gate_status}" -ne 0 ]]; then
  echo "[launchable-post-contact-gate] BLOCKED: contact-physics gate is not PASS; run run_launchable_contact_physics_smoke.sh first" >&2
  exit 2
fi

echo "[launchable-post-contact-gate] PASS: contact-physics gate is satisfied"
