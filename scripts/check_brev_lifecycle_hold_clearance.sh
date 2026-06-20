#!/usr/bin/env bash
set -euo pipefail

if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
  echo "Do not source this script; execute it as a command." >&2
  return 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

BREV_BIN="${RCA_BREV_CLI:-${BREV_BIN:-/Users/Shenghan/bin/brev}}"
HOLD_FILE="${RCA_BREV_LIFECYCLE_HOLD_FILE:-${REPO_ROOT}/docs/brev_launchable_lifecycle_hold.md}"
SUPPORT_DRAFT="${RCA_BREV_SUPPORT_DRAFT:-${REPO_ROOT}/docs/brev_support_followup_2026-06-20.md}"

log() {
  echo "[brev-hold-clearance] $*" >&2
}

fail() {
  echo "[brev-hold-clearance] BLOCKED: $*" >&2
  exit 2
}

if [[ ! -x "${BREV_BIN}" ]]; then
  fail "Brev CLI is not executable: ${BREV_BIN}"
fi

if [[ ! -f "${HOLD_FILE}" ]]; then
  echo "[brev-hold-clearance] PASS: no lifecycle hold file is active"
  exit 0
fi

log "checking visible Brev instance list"
if ! brev_json="$("${BREV_BIN}" ls instances --json --all 2>&1)"; then
  printf '%s\n' "${brev_json}" >&2
  fail "Brev CLI query failed; do not clear hold"
fi

instance_count="$(
  BREV_INSTANCES_JSON="${brev_json}" python3 - <<'PY'
import json
import os
import sys

raw = os.environ.get("BREV_INSTANCES_JSON", "").strip()
try:
    data = json.loads(raw) if raw else None
except json.JSONDecodeError:
    print("invalid")
    sys.exit(20)

if isinstance(data, dict):
    instances = data.get("workspaces") or data.get("instances") or []
elif isinstance(data, list):
    instances = data
else:
    instances = []

if instances is None:
    instances = []
print(len(instances))
PY
)"
if [[ ! "${instance_count}" =~ ^[0-9]+$ ]]; then
  printf '%s\n' "${brev_json}" >&2
  fail "Brev instance JSON could not be parsed"
fi
if (( instance_count > 0 )); then
  printf '%s\n' "${brev_json}" >&2
  fail "visible Brev instance list is not empty (${instance_count}); do not clear hold"
fi

if [[ ! -f "${SUPPORT_DRAFT}" ]]; then
  fail "support follow-up draft is missing: ${SUPPORT_DRAFT}"
fi

report="$(
  set +e
  python3 "${SCRIPT_DIR}/project_status_report.py" 2>&1
)"
if [[ "${report}" != *"Brev lifecycle hold | BLOCKED"* ]]; then
  printf '%s\n' "${report}" >&2
  fail "project status report does not show the lifecycle hold as active"
fi
if [[ "${report}" != *"Contact-smoke bundle | READY"* ]]; then
  printf '%s\n' "${report}" >&2
  fail "current contact-smoke bundle is not READY"
fi

set +e
preflight_output="$(
  RCA_BREV_CLI="${BREV_BIN}" \
  RCA_ALLOW_PAID_BREV_CREATE=1 \
  RCA_BREV_CREDITS_VERIFIED=1 \
  RCA_PAID_BUDGET_EUR=1 \
  RCA_PAID_ESTIMATED_EUR_PER_HOUR=1 \
  RCA_PAID_MAX_MINUTES=5 \
  RCA_PAID_RUN_PURPOSE=contact_physics_smoke \
    "${SCRIPT_DIR}/paid_compute_preflight.sh" 2>&1
)"
preflight_status=$?
set -e
if (( preflight_status != 2 )) || [[ "${preflight_output}" != *"Brev/Launchable lifecycle hold is active"* ]]; then
  printf '%s\n' "${preflight_output}" >&2
  fail "paid preflight is not fail-closed on the lifecycle hold"
fi

cat <<EOF
[brev-hold-clearance] READY_FOR_HUMAN_REVIEW
visible_instances=0
hold_file=${HOLD_FILE}
support_draft=${SUPPORT_DRAFT}
paid_preflight_hold_block=confirmed

This script does not remove the hold. Keep the hold active until Brev service
recovery is confirmed or a deliberate one-run retry is chosen with
RCA_ACK_BREV_LIFECYCLE_RISK=1.
EOF
