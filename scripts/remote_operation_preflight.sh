#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
GATE_REPO_ROOT="${RCA_CONTACT_GATE_REPO_ROOT:-${REPO_ROOT}}"
PURPOSE="${RCA_REMOTE_OPERATION_PURPOSE:-post_contact_gate}"

case "${PURPOSE}" in
  post_contact_gate)
    if ! gate_output="$(python3 "${SCRIPT_DIR}/check_phase2_contact_gate.py" --repo-root "${GATE_REPO_ROOT}" 2>&1)"; then
      echo "[remote-op-preflight] BLOCKED: Phase 2 contact gate is not PASS; refusing post-contact remote operation" >&2
      printf '%s\n' "${gate_output}" >&2
      exit 2
    fi
    ;;
  contact_physics_smoke)
    echo "[remote-op-preflight] contact_physics_smoke remote operation allowed before gate PASS" >&2
    ;;
  *)
    echo "[remote-op-preflight] unknown RCA_REMOTE_OPERATION_PURPOSE=${PURPOSE}; use contact_physics_smoke or post_contact_gate" >&2
    exit 2
    ;;
esac

echo "[remote-op-preflight] PASS purpose=${PURPOSE} repo=${GATE_REPO_ROOT}" >&2
