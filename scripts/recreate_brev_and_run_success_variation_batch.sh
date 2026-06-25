#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

MANIFEST="${1:-${REPO_ROOT}/artifacts/manifests/success_trace_variations_2026-06-25.json}"
ENV_NAME="${2:-rca-success-variation-batch-vm}"
REMOTE_ROOT="${3:-/home/ubuntu/projects/robot-contact-assembly}"
COMPOSE_ROOT="${4:-/home/ubuntu/isaac-compose}"
TASK_NAME="${5:-RCA-PegInHole-Franka-JointPos-Contact-Play-v0}"
STEPS="${6:-${RCA_SUCCESS_VARIATION_STEPS:-220}}"
SEED="${7:-42}"

if [[ ! -f "${MANIFEST}" ]]; then
  echo "[success-variation-paid] missing manifest: ${MANIFEST}" >&2
  exit 2
fi

cat >&2 <<EOF
[success-variation-paid] This is a paid Brev create/run/cleanup wrapper.
[success-variation-paid] It delegates create, preflight, watchdog, artifact pull,
[success-variation-paid] delete, and empty-org confirmation to:
[success-variation-paid]   ${SCRIPT_DIR}/recreate_brev_and_run_final_contact_servo_trace.sh
[success-variation-paid] The shared preflight still requires explicit budget,
[success-variation-paid] credit verification, lifecycle-risk acknowledgement when active,
[success-variation-paid] and an empty Brev org before any instance is created.
EOF

RCA_SUCCESS_VARIATION_MANIFEST="${MANIFEST}" \
RCA_SUCCESS_VARIATION_TASK="${TASK_NAME}" \
RCA_SUCCESS_VARIATION_STEPS="${STEPS}" \
RCA_FINAL_CONTACT_TRACE_RUNNER="${SCRIPT_DIR}/run_remote_success_variation_batch_as_trace_runner.sh" \
RCA_FINAL_CONTACT_VALIDATE_PEG_VIDEO_CANDIDATE=0 \
RCA_FINAL_CONTACT_INSTANCE_TYPE="${RCA_SUCCESS_VARIATION_INSTANCE_TYPE:-${RCA_FINAL_CONTACT_INSTANCE_TYPE:-g6e.xlarge}}" \
RCA_FINAL_CONTACT_MIN_DISK="${RCA_SUCCESS_VARIATION_MIN_DISK:-${RCA_FINAL_CONTACT_MIN_DISK:-500}}" \
RCA_FINAL_CONTACT_CREATE_TIMEOUT="${RCA_SUCCESS_VARIATION_CREATE_TIMEOUT:-${RCA_FINAL_CONTACT_CREATE_TIMEOUT:-900}}" \
RCA_FINAL_CONTACT_WATCHDOG_MAX_MINUTES="${RCA_SUCCESS_VARIATION_WATCHDOG_MAX_MINUTES:-${RCA_FINAL_CONTACT_WATCHDOG_MAX_MINUTES:-75}}" \
RCA_FINAL_CONTACT_TRACE_TIMEOUT_SECONDS="${RCA_SUCCESS_VARIATION_TRACE_TIMEOUT_SECONDS:-${RCA_FINAL_CONTACT_TRACE_TIMEOUT_SECONDS:-3600}}" \
RCA_FINAL_CONTACT_TRACE_TIMEOUT_KILL_SECONDS="${RCA_SUCCESS_VARIATION_TRACE_TIMEOUT_KILL_SECONDS:-${RCA_FINAL_CONTACT_TRACE_TIMEOUT_KILL_SECONDS:-60}}" \
  "${SCRIPT_DIR}/recreate_brev_and_run_final_contact_servo_trace.sh" \
    "${ENV_NAME}" \
    "${REMOTE_ROOT}" \
    "${COMPOSE_ROOT}" \
    "${TASK_NAME}" \
    "${STEPS}" \
    "${SEED}"
