#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="${RCA_LAUNCHABLE_REPO_DIR:-/workspace/robot-contact-assembly}"
ARTIFACT_ROOT="${RCA_LAUNCHABLE_ARTIFACT_ROOT:-${REPO_DIR}/artifacts}"
ISAAC_PYTHON="${RCA_ISAAC_PYTHON:-/isaac-sim/python.sh}"
RUN_ID="$(date -u +"%Y-%m-%dT%H-%M-%SZ")"
DIAG_DIR="${ARTIFACT_ROOT}/launchable_diagnostics/${RUN_ID}_rca_smoke_matrix"
CASE_TIMEOUT_SECONDS="${RCA_LAUNCHABLE_DIAG_CASE_TIMEOUT_SECONDS:-300}"
WATCHDOG_SECONDS="${RCA_LAUNCHABLE_DIAG_WATCHDOG_SECONDS:-180}"
STEPS="${RCA_LAUNCHABLE_DIAG_STEPS:-3}"
SEED="${RCA_LAUNCHABLE_DIAG_SEED:-42}"
export RCA_FORCE_APP_LAUNCHER="${RCA_FORCE_APP_LAUNCHER:-1}"
export RCA_ARTIFACT_ROOT="${RCA_ARTIFACT_ROOT:-${ARTIFACT_ROOT}}"

if [[ ! -x "${ISAAC_PYTHON}" ]]; then
  echo "[launchable-diag] missing Isaac Python: ${ISAAC_PYTHON}" >&2
  exit 2
fi

if [[ ! -d "${REPO_DIR}/source/robot_contact_assembly_tasks" ]]; then
  echo "[launchable-diag] missing project repo at ${REPO_DIR}" >&2
  exit 2
fi

mkdir -p "${DIAG_DIR}" "${ARTIFACT_ROOT}/hydra"

echo "[launchable-diag] repo=${REPO_DIR}"
echo "[launchable-diag] diag_dir=${DIAG_DIR}"
echo "[launchable-diag] steps=${STEPS} seed=${SEED} case_timeout=${CASE_TIMEOUT_SECONDS}s watchdog=${WATCHDOG_SECONDS}s"
echo "[launchable-diag] force_app_launcher=${RCA_FORCE_APP_LAUNCHER}"

"${ISAAC_PYTHON}" -m pip install --editable "${REPO_DIR}/source/robot_contact_assembly_tasks"

cd "${REPO_DIR}"

run_case() {
  local case_name="$1"
  local task_name="$2"
  shift 2
  local log_path="${DIAG_DIR}/${case_name}.log"
  local status_path="${DIAG_DIR}/${case_name}.status"
  local command_path="${DIAG_DIR}/${case_name}.command.txt"

  echo "[launchable-diag] case=${case_name} task=${task_name}"
  printf '%q ' timeout "${CASE_TIMEOUT_SECONDS}" "${ISAAC_PYTHON}" scripts/zero_agent.py \
    --task "${task_name}" \
    --headless \
    --num_envs 1 \
    --steps "${STEPS}" \
    --seed "${SEED}" \
    --progress_every 1 \
    --watchdog_seconds "${WATCHDOG_SECONDS}" \
    "$@" > "${command_path}"
  printf '\n' >> "${command_path}"

  set +e
  timeout "${CASE_TIMEOUT_SECONDS}" "${ISAAC_PYTHON}" scripts/zero_agent.py \
    --task "${task_name}" \
    --headless \
    --num_envs 1 \
    --steps "${STEPS}" \
    --seed "${SEED}" \
    --progress_every 1 \
    --watchdog_seconds "${WATCHDOG_SECONDS}" \
    "$@" \
    2>&1 | tee "${log_path}"
  local status=${PIPESTATUS[0]}
  set -e

  if grep -q "\\[ERROR\\]:" "${log_path}"; then
    status=1
  fi
  if ! grep -q "\\[INFO\\]: Zero-agent step ${STEPS}/${STEPS} completed\\." "${log_path}"; then
    status=1
  fi
  if ! grep -q "\\[INFO\\]: Zero agent smoke test completed" "${log_path}"; then
    status=1
  fi

  echo "${status}" > "${status_path}"
  echo "[launchable-diag] case=${case_name} status=${status}"
}

run_case "00_builtin_reach_franka" "Isaac-Reach-Franka-v0"
run_case "10_rca_ik_rel_play" "RCA-PegInHole-Franka-IK-Rel-Play-v0"
run_case "20_rca_jointpos_contact_play" "RCA-PegInHole-Franka-JointPos-Contact-Play-v0"
run_case "21_rca_jointpos_contact_play_no_interval" "RCA-PegInHole-Franka-JointPos-Contact-Play-v0" --disable_peg_sync_interval

echo "[launchable-diag] statuses:"
for status_file in "${DIAG_DIR}"/*.status; do
  printf '  %s: %s\n' "$(basename "${status_file}" .status)" "$(cat "${status_file}")"
done

echo "[launchable-diag] completed diagnostics at ${DIAG_DIR}"
