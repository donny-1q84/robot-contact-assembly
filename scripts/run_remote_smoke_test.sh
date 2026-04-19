#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/remote_common.sh"

rca_init_remote_vars "${1:-}" "${2:-}" "${3:-}"

TASK_NAME="${4:-RCA-PegInHole-Franka-IK-Rel-Play-v0}"
ZERO_STEPS="${5:-5}"
RANDOM_STEPS="${6:-10}"
SCRIPTED_STEPS="${7:-120}"
EXTRA_SCRIPTED_ARGS="${8:-}"

"${SCRIPT_DIR}/sync_to_brev.sh" "${RCA_ENV_NAME}" "${RCA_REMOTE_ROOT}"

echo "[smoke] compose status on ${RCA_ENV_NAME}"
rca_brev_exec "cd \"${RCA_REMOTE_COMPOSE_ROOT}\" && ${RCA_COMPOSE_BASE} ps"

echo "[smoke] listing registered peg-in-hole environments on ${RCA_ENV_NAME}"
rca_remote_repo_exec "/isaac-sim/python.sh scripts/list_envs.py --keyword PegInHole"

echo "[smoke] zero-action sanity rollout"
rca_remote_repo_exec "/isaac-sim/python.sh scripts/zero_agent.py --task ${TASK_NAME} --headless --num_envs 1 --steps ${ZERO_STEPS}"

echo "[smoke] random-action sanity rollout"
rca_remote_repo_exec "/isaac-sim/python.sh scripts/random_agent.py --task ${TASK_NAME} --headless --num_envs 1 --steps ${RANDOM_STEPS}"

echo "[smoke] scripted baseline sanity rollout"
if [[ -n "${EXTRA_SCRIPTED_ARGS}" ]]; then
  echo "[smoke] scripted extra args: ${EXTRA_SCRIPTED_ARGS}"
fi
rca_remote_repo_exec "/isaac-sim/python.sh scripts/scripted_agent.py --task ${TASK_NAME} --headless --num_envs 1 --steps ${SCRIPTED_STEPS} --approach-height 0.0 --approach-xy-tol 1.0 --approach-rot-tol 10.0 --settle-pos-gain 0.5 --settle-pos-clamp 0.012 --settle-rot-gain 3.0 --settle-rot-clamp 0.24 ${EXTRA_SCRIPTED_ARGS}"

echo "[smoke] completed sanity sequence for ${TASK_NAME}"
