#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/remote_common.sh"

rca_init_remote_vars "${1:-}" "${2:-}" "${3:-}"

TASK_NAME="${4:-RCA-PegInHole-Franka-JointPos-Contact-Play-v0}"
NUM_ENVS="${5:-1}"
STEPS="${6:-1500}"
SEED_CSV="${7:-42}"
TIMEOUT_SECONDS="${8:-900}"
SOCKET_POSITIONS="${9:-${RCA_SOCKET_SWEEP_POSITIONS:-0.22,0.04,0.22;0.24,0.03,0.22;0.26,0.02,0.22;0.28,0.00,0.22}}"
EXTRA_AGENT_ARGS="${10:-${RCA_SOCKET_SWEEP_EXTRA_AGENT_ARGS:-}}"
STOP_ON_SUCCESS="${RCA_SOCKET_SWEEP_STOP_ON_SUCCESS:-1}"

if [[ -z "${SOCKET_POSITIONS}" ]]; then
  echo "[socket-sweep] no socket positions provided" >&2
  exit 2
fi

echo "[socket-sweep] env=${RCA_ENV_NAME} task=${TASK_NAME} num_envs=${NUM_ENVS} steps=${STEPS}"
echo "[socket-sweep] seeds=${SEED_CSV}"
echo "[socket-sweep] timeout_seconds=${TIMEOUT_SECONDS}"
echo "[socket-sweep] stop_on_success=${STOP_ON_SUCCESS}"
echo "[socket-sweep] positions=${SOCKET_POSITIONS}"
if [[ -n "${EXTRA_AGENT_ARGS}" ]]; then
  echo "[socket-sweep] extra_agent_args=${EXTRA_AGENT_ARGS}"
fi

first_seed="${SEED_CSV%%,*}"
IFS=';' read -r -a socket_positions <<< "${SOCKET_POSITIONS}"

for socket_pos in "${socket_positions[@]}"; do
  socket_pos="$(printf '%s' "${socket_pos}" | xargs)"
  [[ -z "${socket_pos}" ]] && continue

  echo "[socket-sweep] running socket_pos=${socket_pos}"
  run_args="${EXTRA_AGENT_ARGS} --socket-pos ${socket_pos}"
  RCA_SCRIPTED_TRACE_JSON="${RCA_SCRIPTED_TRACE_JSON:-1}" \
    RCA_SCRIPTED_EVAL_RETRIES="${RCA_SCRIPTED_EVAL_RETRIES:-0}" \
    bash "${SCRIPT_DIR}/run_remote_scripted_eval.sh" \
      "${RCA_ENV_NAME}" \
      "${RCA_REMOTE_ROOT}" \
      "${RCA_REMOTE_COMPOSE_ROOT}" \
      "${TASK_NAME}" \
      "${NUM_ENVS}" \
      "${STEPS}" \
      "${SEED_CSV}" \
      "${TIMEOUT_SECONDS}" \
      "${run_args}"

  latest_dir="$(rca_remote_container_exec "ls -td /workspace/artifacts/evaluations/scripted/* | head -1" | tr -d '\r' | tail -1)"
  echo "[socket-sweep] latest_dir=${latest_dir}"

  success_report="$(
    rca_remote_container_exec "python3 - <<'PY'
import glob
import json

latest_dir = '${latest_dir}'
successes = []
for path in sorted(glob.glob(latest_dir + '/seed_*.json')):
    with open(path, 'r', encoding='utf-8') as handle:
        data = json.load(handle)
    success_step = data.get('success_step')
    final_success_rate = float(data.get('final_success_rate') or 0.0)
    if success_step is not None or final_success_rate > 0.0:
        successes.append((path, success_step, final_success_rate))

if successes:
    print('success=1')
    for path, success_step, final_success_rate in successes:
        print(f'{path}: success_step={success_step} final_success_rate={final_success_rate}')
else:
    print('success=0')
PY"
  )"
  printf '%s\n' "${success_report}"

  if [[ "${STOP_ON_SUCCESS}" == "1" ]] && printf '%s\n' "${success_report}" | grep -qx 'success=1'; then
    echo "[socket-sweep] success detected; stopping sweep before remaining positions"
    exit 0
  fi
done

echo "[socket-sweep] completed all socket positions"
