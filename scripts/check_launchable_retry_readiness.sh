#!/usr/bin/env bash
set -euo pipefail

if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
  echo "Do not source this script; execute it as a command." >&2
  return 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

BREV_BIN="${RCA_BREV_CLI:-${BREV_BIN:-/Users/Shenghan/bin/brev}}"
BUDGET_EUR="${RCA_PAID_BUDGET_EUR:-}"
ESTIMATED_EUR_PER_HOUR="${RCA_PAID_ESTIMATED_EUR_PER_HOUR:-${RCA_BREV_UI_PRICE_EUR_PER_HOUR:-}}"
MAX_MINUTES="${RCA_PAID_MAX_MINUTES:-${RCA_CONTACT_SMOKE_MAX_MINUTES:-60}}"
CREDITS_VERIFIED="${RCA_BREV_CREDITS_VERIFIED:-0}"
ACK_LIFECYCLE_RISK="${RCA_ACK_BREV_LIFECYCLE_RISK:-0}"
SKIP_LOCAL_QUALITY="${RCA_RETRY_READINESS_SKIP_LOCAL_QUALITY:-0}"
LOCAL_QUALITY_LOG="${RCA_RETRY_READINESS_LOCAL_QUALITY_LOG:-${REPO_ROOT}/artifacts/brev_lifecycle_incidents/retry_readiness_local_quality.log}"

log() {
  echo "[launchable-retry-readiness] $*" >&2
}

fail() {
  echo "[launchable-retry-readiness] BLOCKED: $*" >&2
  exit 2
}

cd "${REPO_ROOT}"

if [[ ! -x "${BREV_BIN}" ]]; then
  fail "Brev CLI is not executable: ${BREV_BIN}"
fi

if [[ -z "${BUDGET_EUR}" ]]; then
  fail "set RCA_PAID_BUDGET_EUR before checking retry readiness"
fi

if [[ -z "${ESTIMATED_EUR_PER_HOUR}" ]]; then
  fail "set RCA_PAID_ESTIMATED_EUR_PER_HOUR to the conservative Launchable UI EUR/hour estimate"
fi

if [[ "${SKIP_LOCAL_QUALITY}" == "1" ]]; then
  log "skipping local quality only because RCA_RETRY_READINESS_SKIP_LOCAL_QUALITY=1"
else
  log "running local no-Isaac quality gate"
  mkdir -p "$(dirname "${LOCAL_QUALITY_LOG}")"
  "${SCRIPT_DIR}/run_local_quality_checks.sh" >"${LOCAL_QUALITY_LOG}"
  log "local quality log=${LOCAL_QUALITY_LOG}"
fi

log "checking Brev safety snapshot"
safety_output="$(RCA_BREV_CLI="${BREV_BIN}" "${SCRIPT_DIR}/brev_paid_safety_status.sh" 2>&1)"
printf '%s\n' "${safety_output}"
if [[ "${safety_output}" != *"status=SAFE_NO_VISIBLE_PAID_INSTANCE"* ]]; then
  fail "Brev safety status is not SAFE_NO_VISIBLE_PAID_INSTANCE"
fi

log "checking current project status"
status_output="$(python3 "${SCRIPT_DIR}/project_status_report.py" 2>&1)"
printf '%s\n' "${status_output}"
if [[ "${status_output}" != *"Contact-smoke bundle | READY"* ]]; then
  fail "current contact-smoke bundle is not READY"
fi
if [[ "${status_output}" == *"Phase 2 contact gate | PASS"* ]]; then
  fail "Phase 2 contact gate already passes; do not spend paid compute on another smoke"
fi
if [[ "${status_output}" != *"Phase 2 contact gate | BLOCKED"* ]]; then
  fail "Phase 2 contact gate is not in the expected BLOCKED pre-smoke state"
fi

if [[ "${ACK_LIFECYCLE_RISK}" != "1" ]]; then
  set +e
  hold_output="$(
    RCA_BREV_CLI="${BREV_BIN}" \
    RCA_ALLOW_PAID_BREV_CREATE=1 \
    RCA_BREV_CREDITS_VERIFIED=1 \
    RCA_PAID_BUDGET_EUR="${BUDGET_EUR}" \
    RCA_PAID_ESTIMATED_EUR_PER_HOUR="${ESTIMATED_EUR_PER_HOUR}" \
    RCA_PAID_MAX_MINUTES="${MAX_MINUTES}" \
    RCA_PAID_RUN_PURPOSE=contact_physics_smoke \
      "${SCRIPT_DIR}/paid_compute_preflight.sh" 2>&1
  )"
  hold_status=$?
  set -e
  printf '%s\n' "${hold_output}"
  if (( hold_status != 2 )) || [[ "${hold_output}" != *"Brev/Launchable lifecycle hold is active"* ]]; then
    fail "paid preflight did not fail closed on the lifecycle hold"
  fi
  fail "lifecycle risk has not been acknowledged; set RCA_ACK_BREV_LIFECYCLE_RISK=1 only for one deliberate short contact-smoke retry"
fi

log "running final paid preflight with lifecycle-risk acknowledgement"
  RCA_BREV_CLI="${BREV_BIN}" \
  RCA_ALLOW_PAID_BREV_CREATE=1 \
  RCA_BREV_CREDITS_VERIFIED="${CREDITS_VERIFIED}" \
  RCA_ACK_BREV_LIFECYCLE_RISK=1 \
RCA_PAID_BUDGET_EUR="${BUDGET_EUR}" \
RCA_PAID_ESTIMATED_EUR_PER_HOUR="${ESTIMATED_EUR_PER_HOUR}" \
RCA_PAID_MAX_MINUTES="${MAX_MINUTES}" \
RCA_PAID_RUN_PURPOSE=contact_physics_smoke \
  "${SCRIPT_DIR}/paid_compute_preflight.sh"

cat <<EOF
[launchable-retry-readiness] READY_FOR_ONE_CONTACT_SMOKE_RETRY
repo=${REPO_ROOT}
budget_eur=${BUDGET_EUR}
estimated_eur_per_hour=${ESTIMATED_EUR_PER_HOUR}
credits_verified=${CREDITS_VERIFIED}
max_minutes=${MAX_MINUTES}

This script is read-only. It did not create, start, stop, or delete any paid
resource. If you proceed, run exactly one contact-smoke retry with the org
watchdog already running, then pull/archive the smoke log and delete the
Launchable instance immediately.
EOF
