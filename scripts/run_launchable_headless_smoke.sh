#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="${RCA_LAUNCHABLE_REPO_DIR:-/workspace/robot-contact-assembly}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
"${SCRIPT_DIR}/launchable_post_contact_gate.sh" "${REPO_DIR}"
ARTIFACT_ROOT="${RCA_LAUNCHABLE_ARTIFACT_ROOT:-${REPO_DIR}/artifacts}"
ISAAC_PYTHON="${RCA_ISAAC_PYTHON:-/isaac-sim/python.sh}"
TASK_NAME="${RCA_LAUNCHABLE_SMOKE_TASK:-RCA-PegInHole-Franka-JointPos-Contact-Play-v0}"
STEPS="${RCA_LAUNCHABLE_SMOKE_STEPS:-10}"
SEED="${RCA_LAUNCHABLE_SMOKE_SEED:-42}"
PROGRESS_EVERY="${RCA_LAUNCHABLE_SMOKE_PROGRESS_EVERY:-1}"
WATCHDOG_SECONDS="${RCA_LAUNCHABLE_SMOKE_WATCHDOG_SECONDS:-180}"
export RCA_FORCE_APP_LAUNCHER="${RCA_FORCE_APP_LAUNCHER:-1}"
export RCA_ARTIFACT_ROOT="${RCA_ARTIFACT_ROOT:-${ARTIFACT_ROOT}}"
LOG_DIR="${ARTIFACT_ROOT}/launchable_logs"
LOG_PATH="${RCA_LAUNCHABLE_SMOKE_LOG_PATH:-${LOG_DIR}/headless_smoke_zero_agent.log}"

if [[ ! -x "${ISAAC_PYTHON}" ]]; then
  echo "[launchable-smoke] missing Isaac Python: ${ISAAC_PYTHON}" >&2
  exit 2
fi

if [[ ! -d "${REPO_DIR}/source/robot_contact_assembly_tasks" ]]; then
  echo "[launchable-smoke] missing project repo at ${REPO_DIR}" >&2
  echo "[launchable-smoke] expected ${REPO_DIR}/source/robot_contact_assembly_tasks" >&2
  exit 2
fi

mkdir -p "${ARTIFACT_ROOT}/hydra" "${LOG_DIR}"

echo "[launchable-smoke] repo=${REPO_DIR}"
echo "[launchable-smoke] isaac_python=${ISAAC_PYTHON}"
echo "[launchable-smoke] task=${TASK_NAME} steps=${STEPS} seed=${SEED} watchdog=${WATCHDOG_SECONDS}s force_app_launcher=${RCA_FORCE_APP_LAUNCHER}"

"${ISAAC_PYTHON}" -m pip install --editable "${REPO_DIR}/source/robot_contact_assembly_tasks"

cd "${REPO_DIR}"

set +e
"${ISAAC_PYTHON}" scripts/zero_agent.py \
  --task "${TASK_NAME}" \
  --headless \
  --num_envs 1 \
  --steps "${STEPS}" \
  --seed "${SEED}" \
  --progress_every "${PROGRESS_EVERY}" \
  --watchdog_seconds "${WATCHDOG_SECONDS}" \
  2>&1 | tee "${LOG_PATH}"
status=${PIPESTATUS[0]}
set -e

if [[ ${status} -ne 0 ]]; then
  echo "[launchable-smoke] zero_agent failed status=${status}; inspect ${LOG_PATH}" >&2
  exit "${status}"
fi

if grep -q "\\[ERROR\\]:" "${LOG_PATH}"; then
  echo "[launchable-smoke] zero_agent emitted an error; inspect ${LOG_PATH}" >&2
  exit 1
fi

if ! grep -q "\\[INFO\\]: Environment reset completed\\." "${LOG_PATH}"; then
  echo "[launchable-smoke] reset completion marker missing; inspect ${LOG_PATH}" >&2
  exit 1
fi

if ! grep -q "\\[INFO\\]: Zero-agent step ${STEPS}/${STEPS} completed\\." "${LOG_PATH}"; then
  echo "[launchable-smoke] final step marker missing; inspect ${LOG_PATH}" >&2
  exit 1
fi

if ! grep -q "\\[INFO\\]: Zero agent smoke test completed" "${LOG_PATH}"; then
  echo "[launchable-smoke] final completion marker missing; inspect ${LOG_PATH}" >&2
  exit 1
fi

echo "[launchable-smoke] completed"
