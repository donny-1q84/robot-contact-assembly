#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="${RCA_LAUNCHABLE_REPO_DIR:-/workspace/robot-contact-assembly}"
ARTIFACT_ROOT="${RCA_LAUNCHABLE_ARTIFACT_ROOT:-${REPO_DIR}/artifacts}"
ISAAC_PYTHON="${RCA_ISAAC_PYTHON:-/isaac-sim/python.sh}"
TASK_NAME="${RCA_LAUNCHABLE_TASK:-RCA-PegInHole-Franka-JointPos-Contact-Play-v0}"
STEPS="${RCA_LAUNCHABLE_STEPS:-400}"
SEED="${RCA_LAUNCHABLE_SEED:-42}"
TIMEOUT_SECONDS="${RCA_LAUNCHABLE_TIMEOUT_SECONDS:-1200}"
PRELOAD_TRACE="${RCA_LAUNCHABLE_PRELOAD_TRACE:-${ARTIFACT_ROOT}/preload_traces/2026-05-17T23-32-18Z_seed_42_trace.json}"
ALLOW_HISTORICAL_REPLAY="${RCA_ALLOW_HISTORICAL_PRELOAD_REPLAY:-0}"
export RCA_FORCE_APP_LAUNCHER="${RCA_FORCE_APP_LAUNCHER:-1}"
export RCA_ARTIFACT_ROOT="${RCA_ARTIFACT_ROOT:-${ARTIFACT_ROOT}}"
RUN_ID="$(date -u +"%Y-%m-%dT%H-%M-%SZ")"
EVAL_DIR="${ARTIFACT_ROOT}/evaluations/contact_handoff_baseline/${RUN_ID}_preload-direction"
SUMMARY_JSON="${EVAL_DIR}/summary.json"
TRACE_JSON="${EVAL_DIR}/trace.json"
LOG_PATH="${EVAL_DIR}/eval.log"
COMMAND_PATH="${EVAL_DIR}/eval_command.txt"

if [[ ! -x "${ISAAC_PYTHON}" ]]; then
  echo "[launchable-preload] missing Isaac Python: ${ISAAC_PYTHON}" >&2
  exit 2
fi

if [[ ! -d "${REPO_DIR}/source/robot_contact_assembly_tasks" ]]; then
  echo "[launchable-preload] missing project repo at ${REPO_DIR}" >&2
  exit 2
fi

if [[ ! -s "${PRELOAD_TRACE}" ]]; then
  echo "[launchable-preload] missing preload trace: ${PRELOAD_TRACE}" >&2
  echo "[launchable-preload] copy artifacts/preload_traces/2026-05-17T23-32-18Z_seed_42_trace.json into ${ARTIFACT_ROOT}/preload_traces first" >&2
  exit 2
fi

if [[ "${ALLOW_HISTORICAL_REPLAY}" != "1" ]]; then
  echo "[launchable-preload] refusing historical preload replay by default." >&2
  echo "[launchable-preload] The 2026-05-17T23-32-18Z raw_action trace drifted under Isaac Lab 2.3." >&2
  echo "[launchable-preload] Use ./scripts/run_launchable_phase2_fresh_preload_direction.sh instead." >&2
  echo "[launchable-preload] For an intentional replay-drift diagnostic, set RCA_ALLOW_HISTORICAL_PRELOAD_REPLAY=1." >&2
  exit 2
fi

mkdir -p "${EVAL_DIR}" "${ARTIFACT_ROOT}/hydra"

echo "[launchable-preload] repo=${REPO_DIR}"
echo "[launchable-preload] task=${TASK_NAME} steps=${STEPS} seed=${SEED}"
echo "[launchable-preload] force_app_launcher=${RCA_FORCE_APP_LAUNCHER}"
echo "[launchable-preload] preload_trace=${PRELOAD_TRACE}"
echo "[launchable-preload] eval_dir=${EVAL_DIR}"

"${ISAAC_PYTHON}" -m pip install --editable "${REPO_DIR}/source/robot_contact_assembly_tasks"

cd "${REPO_DIR}"

cat > "${COMMAND_PATH}" <<EOF
${ISAAC_PYTHON} scripts/evaluate_contact_bc_policy.py --task ${TASK_NAME} --headless --num_envs 1 --steps ${STEPS} --seed ${SEED} --controller preload-direction --preload-trace-json ${PRELOAD_TRACE} --preload-trace-end-step 1543 --summary-json ${SUMMARY_JSON} --trace-json ${TRACE_JSON} --deterministic-reset --socket-pos 0.22,0.04,0.22 --success-xy-tol 0.005 --success-z-tol 0.045 --success-rot-tol 0.18 --success-min-contact-force 0.5 --near-contact-xy-tol 0.015 --near-contact-z-tol 0.060 --near-contact-rot-tol 0.35 --near-contact-min-force 0.2 --max-action-delta 0.02 --preload-direction-hold-gain 0.35 --preload-direction-scale 1.0
EOF

set +e
timeout "${TIMEOUT_SECONDS}" "${ISAAC_PYTHON}" scripts/evaluate_contact_bc_policy.py \
  --task "${TASK_NAME}" \
  --headless \
  --num_envs 1 \
  --steps "${STEPS}" \
  --seed "${SEED}" \
  --controller preload-direction \
  --preload-trace-json "${PRELOAD_TRACE}" \
  --preload-trace-end-step 1543 \
  --summary-json "${SUMMARY_JSON}" \
  --trace-json "${TRACE_JSON}" \
  --deterministic-reset \
  --socket-pos 0.22,0.04,0.22 \
  --success-xy-tol 0.005 \
  --success-z-tol 0.045 \
  --success-rot-tol 0.18 \
  --success-min-contact-force 0.5 \
  --near-contact-xy-tol 0.015 \
  --near-contact-z-tol 0.060 \
  --near-contact-rot-tol 0.35 \
  --near-contact-min-force 0.2 \
  --max-action-delta 0.02 \
  --preload-direction-hold-gain 0.35 \
  --preload-direction-scale 1.0 \
  2>&1 | tee "${LOG_PATH}"
status=${PIPESTATUS[0]}
set -e

if [[ ${status} -ne 0 ]]; then
  echo "[launchable-preload] failed status=${status}; inspect ${LOG_PATH}" >&2
  exit "${status}"
fi

if grep -q "\\[ERROR\\]:\\|Traceback (most recent call last)" "${LOG_PATH}"; then
  echo "[launchable-preload] eval log contains an error; inspect ${LOG_PATH}" >&2
  exit 1
fi

if [[ ! -s "${SUMMARY_JSON}" ]]; then
  echo "[launchable-preload] missing summary after eval; inspect ${LOG_PATH}" >&2
  exit 1
fi

echo "[launchable-preload] summary=${SUMMARY_JSON}"
echo "[launchable-preload] trace=${TRACE_JSON}"
echo "[launchable-preload] command=${COMMAND_PATH}"
