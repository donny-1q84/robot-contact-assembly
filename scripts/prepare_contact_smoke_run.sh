#!/usr/bin/env bash
set -euo pipefail

if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
  echo "Do not source this script; execute it as a command." >&2
  return 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

MAX_MINUTES="${RCA_CONTACT_SMOKE_MAX_MINUTES:-${RCA_PAID_MAX_MINUTES:-60}}"
BUDGET_EUR="${RCA_PAID_BUDGET_EUR:-}"
ESTIMATED_EUR_PER_HOUR="${RCA_PAID_ESTIMATED_EUR_PER_HOUR:-${RCA_BREV_UI_PRICE_EUR_PER_HOUR:-}}"
CREDITS_VERIFIED="${RCA_BREV_CREDITS_VERIFIED:-0}"
START_WATCHDOG="${RCA_CONTACT_SMOKE_START_WATCHDOG:-0}"
RUN_ID="$(date -u +"%Y-%m-%dT%H-%M-%SZ")"
BUNDLE_PATH="${RCA_CONTACT_SMOKE_BUNDLE_PATH:-${REPO_ROOT}/artifacts/launchable/robot-contact-assembly-contact-smoke-${RUN_ID}.tar.gz}"

cd "${REPO_ROOT}"

log() {
  echo "[contact-smoke-prepare] $*" >&2
}

fail() {
  echo "[contact-smoke-prepare] BLOCKED: $*" >&2
  exit 2
}

if [[ -z "${BUDGET_EUR}" ]]; then
  fail "set RCA_PAID_BUDGET_EUR to the explicit budget for this smoke run"
fi

if [[ -z "${ESTIMATED_EUR_PER_HOUR}" ]]; then
  fail "set RCA_PAID_ESTIMATED_EUR_PER_HOUR to a conservative EUR/hour estimate from the Launchable UI price"
fi

if [[ "${RCA_CONTACT_SMOKE_TEST_SKIP_LOCAL_QUALITY:-0}" == "1" ]]; then
  log "skipping local no-Isaac quality gate for offline script test"
else
  log "running local no-Isaac quality gate"
  "${SCRIPT_DIR}/run_local_quality_checks.sh"
fi

log "checking whether the contact gate is already satisfied"
set +e
phase_output="$(python3 "${SCRIPT_DIR}/check_phase2_contact_gate.py" 2>&1)"
phase_status=$?
set -e
printf '%s\n' "${phase_output}"

case "${phase_status}" in
  0)
    log "contact gate already passes; do not spend paid compute on another smoke"
    exit 0
    ;;
  2)
    log "contact gate is blocked as expected; one short contact-smoke run is the only allowed paid action"
    ;;
  *)
    fail "contact gate check failed unexpectedly with status=${phase_status}"
    ;;
esac

log "running paid preflight for contact_physics_smoke"
RCA_ALLOW_PAID_BREV_CREATE="${RCA_ALLOW_PAID_BREV_CREATE:-1}" \
RCA_BREV_CREDITS_VERIFIED="${CREDITS_VERIFIED}" \
RCA_PAID_RUN_PURPOSE=contact_physics_smoke \
RCA_PAID_MAX_MINUTES="${MAX_MINUTES}" \
  "${SCRIPT_DIR}/paid_compute_preflight.sh"

log "creating current Launchable bundle with source manifest"
"${SCRIPT_DIR}/create_launchable_bundle.sh" "${BUNDLE_PATH}"

cat <<EOF
[contact-smoke-prepare] READY

Prepared bundle:

   ${BUNDLE_PATH}

Next commands:

1. Start the org-scope watchdog before creating the UI Launchable:

   RCA_ALLOW_PAID_BREV_CREATE=1 \\
   RCA_BREV_CREDITS_VERIFIED=1 \\
   RCA_PAID_BUDGET_EUR=${BUDGET_EUR} \\
   RCA_PAID_ESTIMATED_EUR_PER_HOUR=${ESTIMATED_EUR_PER_HOUR} \\
   RCA_BREV_WATCHDOG_MAX_MINUTES=${MAX_MINUTES} \\
     ./scripts/start_brev_ui_launchable_watchdog.sh

2. Create the official AWS Isaac Launchable in the Brev UI.

3. Upload this exact bundle to the Launchable instance, then extract it:

   cd /workspace
   tar -xzf $(basename "${BUNDLE_PATH}") -C /workspace
   cd /workspace/robot-contact-assembly

4. Run only:

   ./scripts/run_launchable_contact_physics_smoke.sh

5. Pull, archive, and validate the smoke log:

   ./scripts/pull_contact_smoke_log.sh <launchable-env-name> /workspace/robot-contact-assembly

6. Delete the instance immediately and confirm the visible instance list is empty.
EOF

if [[ "${START_WATCHDOG}" == "1" ]]; then
  log "starting watchdog because RCA_CONTACT_SMOKE_START_WATCHDOG=1"
  RCA_ALLOW_PAID_BREV_CREATE=1 \
  RCA_BREV_CREDITS_VERIFIED="${CREDITS_VERIFIED}" \
  RCA_PAID_BUDGET_EUR="${BUDGET_EUR}" \
  RCA_PAID_ESTIMATED_EUR_PER_HOUR="${ESTIMATED_EUR_PER_HOUR}" \
  RCA_BREV_WATCHDOG_MAX_MINUTES="${MAX_MINUTES}" \
    exec "${SCRIPT_DIR}/start_brev_ui_launchable_watchdog.sh"
fi
