#!/usr/bin/env bash
set -euo pipefail

# Contact-physics smoke gate (2026-06-11 audit). Must pass on the Isaac
# runtime before ANY paid controller/BC/RL run. Mirrors the marker-checked
# pattern of run_launchable_headless_smoke.sh.

REPO_DIR="${RCA_LAUNCHABLE_REPO_DIR:-/workspace/robot-contact-assembly}"
ARTIFACT_ROOT="${RCA_LAUNCHABLE_ARTIFACT_ROOT:-${REPO_DIR}/artifacts}"
ISAAC_PYTHON="${RCA_ISAAC_PYTHON:-/isaac-sim/python.sh}"
TASK_NAME="${RCA_CONTACT_SMOKE_TASK:-RCA-PegInHole-Franka-IK-Abs-Contact-Play-v0}"
NUM_ENVS="${RCA_CONTACT_SMOKE_NUM_ENVS:-2}"
SEED="${RCA_CONTACT_SMOKE_SEED:-42}"
WATCHDOG_SECONDS="${RCA_CONTACT_SMOKE_WATCHDOG_SECONDS:-420}"
export RCA_FORCE_APP_LAUNCHER="${RCA_FORCE_APP_LAUNCHER:-1}"
export RCA_ARTIFACT_ROOT="${RCA_ARTIFACT_ROOT:-${ARTIFACT_ROOT}}"
LOG_DIR="${ARTIFACT_ROOT}/launchable_logs"
RUN_ID="${RCA_CONTACT_SMOKE_RUN_ID:-$(date -u +"%Y-%m-%dT%H-%M-%SZ")-$$}"
CANONICAL_LOG_PATH="${RCA_CONTACT_SMOKE_CANONICAL_LOG_PATH:-${LOG_DIR}/contact_physics_smoke.log}"
if [[ -n "${RCA_CONTACT_SMOKE_LOG_PATH:-}" ]]; then
  LOG_PATH="${RCA_CONTACT_SMOKE_LOG_PATH}"
else
  LOG_PATH="${LOG_DIR}/contact_physics_smoke_${RUN_ID}.log"
fi
RUN_INDEX="${LOG_DIR}/contact_physics_smoke_runs.tsv"
SOURCE_MANIFEST="${RCA_SOURCE_MANIFEST_PATH:-${REPO_DIR}/.rca_launchable_source_manifest.txt}"

mkdir -p "${ARTIFACT_ROOT}/hydra" "${LOG_DIR}"
: > "${LOG_PATH}"

finalize_log() {
  local status=$?
  if [[ -f "${LOG_PATH}" && "${LOG_PATH}" != "${CANONICAL_LOG_PATH}" ]]; then
    cp "${LOG_PATH}" "${CANONICAL_LOG_PATH}" 2>/dev/null || true
  fi
  printf '%s\t%s\tEXIT_%s\t%s\n' "$(date -u +"%Y-%m-%dT%H:%M:%SZ")" "${RUN_ID}" "${status}" "${LOG_PATH}" >> "${RUN_INDEX}" 2>/dev/null || true
}
trap finalize_log EXIT

log_line() {
  echo "$*" | tee -a "${LOG_PATH}"
}

git_head="$(git -C "${REPO_DIR}" rev-parse HEAD 2>/dev/null || echo unknown)"

log_line "[contact-smoke] repo=${REPO_DIR}"
log_line "[contact-smoke] task=${TASK_NAME} num_envs=${NUM_ENVS} seed=${SEED} watchdog=${WATCHDOG_SECONDS}s"
log_line "[contact-smoke] run_id=${RUN_ID}"
log_line "[contact-smoke] log_path=${LOG_PATH}"
log_line "[contact-smoke] canonical_log_path=${CANONICAL_LOG_PATH}"
log_line "[contact-smoke] git_head=${git_head}"
if [[ -f "${SOURCE_MANIFEST}" ]]; then
  log_line "[contact-smoke] source_manifest_begin"
  sed 's/^/[contact-smoke] source_manifest: /' "${SOURCE_MANIFEST}" | tee -a "${LOG_PATH}"
  log_line "[contact-smoke] source_manifest_end"
else
  log_line "[contact-smoke] source_manifest=missing"
fi

printf '%s\t%s\tSTARTED\t%s\n' "$(date -u +"%Y-%m-%dT%H:%M:%SZ")" "${RUN_ID}" "${LOG_PATH}" >> "${RUN_INDEX}"

if [[ ! -x "${ISAAC_PYTHON}" ]]; then
  log_line "[contact-smoke] missing Isaac Python: ${ISAAC_PYTHON}"
  exit 2
fi

if [[ ! -d "${REPO_DIR}/source/robot_contact_assembly_tasks" ]]; then
  log_line "[contact-smoke] missing project repo at ${REPO_DIR}"
  exit 2
fi

log_line "[contact-smoke] installing task extension"
set +e
"${ISAAC_PYTHON}" -m pip install --editable "${REPO_DIR}/source/robot_contact_assembly_tasks" \
  2>&1 | tee -a "${LOG_PATH}"
install_status=${PIPESTATUS[0]}
set -e
if [[ ${install_status} -ne 0 ]]; then
  log_line "[contact-smoke] pip install failed status=${install_status}"
  exit "${install_status}"
fi
log_line "[contact-smoke] task extension install completed"

cd "${REPO_DIR}"

set +e
"${ISAAC_PYTHON}" scripts/contact_physics_smoke.py \
  --task "${TASK_NAME}" \
  --headless \
  --num_envs "${NUM_ENVS}" \
  --seed "${SEED}" \
  --watchdog_seconds "${WATCHDOG_SECONDS}" \
  2>&1 | tee -a "${LOG_PATH}"
status=${PIPESTATUS[0]}
set -e

if grep -q "CONTACT-SMOKE .*: FAIL" "${LOG_PATH}"; then
  echo "[contact-smoke] FAIL markers present; inspect ${LOG_PATH}" >&2
  exit 1
fi

missing_marker=0
for marker in "CONTACT-SMOKE reset-joints: deterministic" \
              "CONTACT-SMOKE phase free-space-settle: end" \
              "CONTACT-SMOKE attach: PASS" "CONTACT-SMOKE free-space: PASS" \
              "CONTACT-SMOKE phase local-guide-reanchor: end" \
              "CONTACT-SMOKE contact-setup: local-guide reanchored" "CONTACT-SMOKE free-space-reanchored: PASS" \
              "CONTACT-SMOKE press-control: local-wall-sweep" \
              "CONTACT-SMOKE phase press-hold: end" \
              "CONTACT-SMOKE press-force: PASS" "CONTACT-SMOKE press-tracking: PASS" \
              "CONTACT-SMOKE press-blocked: PASS" "CONTACT-SMOKE press-no-clip: PASS" "CONTACT-SMOKE release: PASS" \
              "CONTACT-SMOKE phase retreat-hold: end" "CONTACT-SMOKE joint-integrity: PASS" \
              "CONTACT-SMOKE phase-sequence: PASS" \
              "Contact physics smoke completed: all checks passed"; do
  if ! grep -q "${marker}" "${LOG_PATH}"; then
    echo "[contact-smoke] missing marker: ${marker}; inspect ${LOG_PATH}" >&2
    missing_marker=1
  fi
done
if [[ ${missing_marker} -ne 0 ]]; then
  if [[ ${status} -ne 0 ]]; then
    echo "[contact-smoke] contact_physics_smoke failed status=${status}; inspect ${LOG_PATH}" >&2
  fi
  exit 1
fi

if [[ ${status} -ne 0 ]]; then
  log_line "[contact-smoke] isaac runner exited nonzero after semantic pass status=${status}; treating Isaac teardown as nonfatal"
fi

log_line "[contact-smoke] completed: contact physics is real"
