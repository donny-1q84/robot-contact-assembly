#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/remote_common.sh"

rca_init_remote_vars "${1:-}" "${2:-}" "${3:-}"

TASK_NAME="${4:-RCA-PegInHole-Franka-JointPos-Contact-Play-v0}"
NUM_ENVS="${5:-1}"
STEPS="${6:-400}"
SEED="${7:-42}"
CONTROLLER="${8:-current-joint}"
TIMEOUT_SECONDS="${9:-900}"
EXTRA_EVAL_ARGS="${10:-}"
TRACE_JSON_ENABLED="${RCA_BASELINE_TRACE_JSON:-1}"
LOCAL_PRELOAD_TRACE="${RCA_BASELINE_LOCAL_PRELOAD_TRACE:-}"
REMOTE_PRELOAD_TRACE="${RCA_BASELINE_REMOTE_PRELOAD_TRACE:-}"

case "${CONTROLLER}" in
  current-joint|last-preload-action) ;;
  *)
    echo "[handoff-baseline] unsupported controller=${CONTROLLER}; use current-joint or last-preload-action" >&2
    exit 2
    ;;
esac

if [[ -z "${LOCAL_PRELOAD_TRACE}" && -z "${REMOTE_PRELOAD_TRACE}" ]]; then
  echo "[handoff-baseline] a preload trace is required for post-handoff baseline eval" >&2
  echo "[handoff-baseline] set RCA_BASELINE_LOCAL_PRELOAD_TRACE or RCA_BASELINE_REMOTE_PRELOAD_TRACE" >&2
  exit 2
fi

"${SCRIPT_DIR}/sync_to_brev.sh" "${RCA_ENV_NAME}" "${RCA_REMOTE_ROOT}"

TIMESTAMP_UTC="$(date -u +"%Y-%m-%dT%H-%M-%SZ")"
REMOTE_EVAL_DIR="/workspace/artifacts/evaluations/contact_handoff_baseline/${TIMESTAMP_UTC}_${CONTROLLER}"
REMOTE_LOG_PATH="${REMOTE_EVAL_DIR}/eval.log"
REMOTE_SUMMARY_PATH="${REMOTE_EVAL_DIR}/summary.json"
REMOTE_TRACE_PATH="${REMOTE_EVAL_DIR}/trace.json"
REMOTE_COMMAND_PATH="${REMOTE_EVAL_DIR}/eval_command.txt"
TRACE_ARG=""
if [[ "${TRACE_JSON_ENABLED}" == "1" ]]; then
  TRACE_ARG="--trace-json '${REMOTE_TRACE_PATH}'"
fi

if [[ -n "${LOCAL_PRELOAD_TRACE}" ]]; then
  if [[ ! -s "${LOCAL_PRELOAD_TRACE}" ]]; then
    echo "[handoff-baseline] local preload trace missing or empty: ${LOCAL_PRELOAD_TRACE}" >&2
    exit 2
  fi
  if [[ -z "${REMOTE_PRELOAD_TRACE}" ]]; then
    REMOTE_PRELOAD_TRACE="/workspace/artifacts/preload_traces/$(basename "${LOCAL_PRELOAD_TRACE}")"
  fi
fi
if [[ "${REMOTE_PRELOAD_TRACE}" != /workspace/artifacts/* ]]; then
  echo "[handoff-baseline] REMOTE_PRELOAD_TRACE must live under /workspace/artifacts: ${REMOTE_PRELOAD_TRACE}" >&2
  exit 2
fi

echo "[handoff-baseline] env=${RCA_ENV_NAME} task=${TASK_NAME} controller=${CONTROLLER} num_envs=${NUM_ENVS} steps=${STEPS} seed=${SEED}"
echo "[handoff-baseline] preload_trace=${REMOTE_PRELOAD_TRACE}"
echo "[handoff-baseline] timeout_seconds=${TIMEOUT_SECONDS}"

if [[ -n "${LOCAL_PRELOAD_TRACE}" ]]; then
  REMOTE_PRELOAD_RELATIVE_PATH="${REMOTE_PRELOAD_TRACE#/workspace/artifacts/}"
  REMOTE_PRELOAD_HOST_PATH="${RCA_REMOTE_ROOT}/artifacts/${REMOTE_PRELOAD_RELATIVE_PATH}"
  REMOTE_PRELOAD_HOST_DIR="$(dirname "${REMOTE_PRELOAD_HOST_PATH}")"
  ssh "${RCA_ENV_NAME}" "sudo mkdir -p '${REMOTE_PRELOAD_HOST_DIR}'"
  rsync -az --rsync-path="sudo rsync" "${LOCAL_PRELOAD_TRACE}" "${RCA_ENV_NAME}:${REMOTE_PRELOAD_HOST_PATH}"
  ssh "${RCA_ENV_NAME}" "sudo chmod 0644 '${REMOTE_PRELOAD_HOST_PATH}'"
fi

rca_remote_container_exec "mkdir -p '${REMOTE_EVAL_DIR}'"
rca_remote_container_exec "cat > '${REMOTE_COMMAND_PATH}' <<'EOF'
/isaac-sim/python.sh scripts/evaluate_contact_bc_policy.py --task '${TASK_NAME}' --headless --num_envs '${NUM_ENVS}' --steps '${STEPS}' --seed '${SEED}' --controller '${CONTROLLER}' --preload-trace-json '${REMOTE_PRELOAD_TRACE}' --summary-json '${REMOTE_SUMMARY_PATH}' ${TRACE_ARG} ${EXTRA_EVAL_ARGS}
EOF"

set +e
rca_remote_repo_exec "set -o pipefail && timeout ${TIMEOUT_SECONDS} /isaac-sim/python.sh scripts/evaluate_contact_bc_policy.py --task '${TASK_NAME}' --headless --num_envs '${NUM_ENVS}' --steps '${STEPS}' --seed '${SEED}' --controller '${CONTROLLER}' --preload-trace-json '${REMOTE_PRELOAD_TRACE}' --summary-json '${REMOTE_SUMMARY_PATH}' ${TRACE_ARG} ${EXTRA_EVAL_ARGS} 2>&1 | tee '${REMOTE_LOG_PATH}'"
status=$?
set -e
if [[ ${status} -ne 0 ]]; then
  echo "[handoff-baseline] evaluation failed with status=${status}" >&2
  echo "[handoff-baseline] inspect ${REMOTE_LOG_PATH}" >&2
  exit "${status}"
fi

echo "[handoff-baseline] eval dir: ${REMOTE_EVAL_DIR}"
echo "[handoff-baseline] summary:  ${REMOTE_SUMMARY_PATH}"
if [[ "${TRACE_JSON_ENABLED}" == "1" ]]; then
  echo "[handoff-baseline] trace:    ${REMOTE_TRACE_PATH}"
fi
echo "[handoff-baseline] command:  ${REMOTE_COMMAND_PATH}"
