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
LOG_PATH="${RCA_CONTACT_SMOKE_LOG_PATH:-${LOG_DIR}/contact_physics_smoke.log}"

if [[ ! -x "${ISAAC_PYTHON}" ]]; then
  echo "[contact-smoke] missing Isaac Python: ${ISAAC_PYTHON}" >&2
  exit 2
fi

if [[ ! -d "${REPO_DIR}/source/robot_contact_assembly_tasks" ]]; then
  echo "[contact-smoke] missing project repo at ${REPO_DIR}" >&2
  exit 2
fi

mkdir -p "${ARTIFACT_ROOT}/hydra" "${LOG_DIR}"

echo "[contact-smoke] repo=${REPO_DIR}"
echo "[contact-smoke] task=${TASK_NAME} num_envs=${NUM_ENVS} seed=${SEED} watchdog=${WATCHDOG_SECONDS}s"

"${ISAAC_PYTHON}" -m pip install --editable "${REPO_DIR}/source/robot_contact_assembly_tasks"

cd "${REPO_DIR}"

set +e
"${ISAAC_PYTHON}" scripts/contact_physics_smoke.py \
  --task "${TASK_NAME}" \
  --headless \
  --num_envs "${NUM_ENVS}" \
  --seed "${SEED}" \
  --watchdog_seconds "${WATCHDOG_SECONDS}" \
  2>&1 | tee "${LOG_PATH}"
status=${PIPESTATUS[0]}
set -e

if [[ ${status} -ne 0 ]]; then
  echo "[contact-smoke] contact_physics_smoke failed status=${status}; inspect ${LOG_PATH}" >&2
  exit "${status}"
fi

if grep -q "CONTACT-SMOKE .*: FAIL" "${LOG_PATH}"; then
  echo "[contact-smoke] FAIL markers present; inspect ${LOG_PATH}" >&2
  exit 1
fi

for marker in "CONTACT-SMOKE attach: PASS" "CONTACT-SMOKE free-space: PASS" \
              "CONTACT-SMOKE press-force: PASS" "CONTACT-SMOKE press-blocked: PASS" \
              "CONTACT-SMOKE release: PASS" "CONTACT-SMOKE joint-integrity: PASS" \
              "Contact physics smoke completed: all checks passed"; do
  if ! grep -q "${marker}" "${LOG_PATH}"; then
    echo "[contact-smoke] missing marker: ${marker}; inspect ${LOG_PATH}" >&2
    exit 1
  fi
done

echo "[contact-smoke] completed: contact physics is real"
