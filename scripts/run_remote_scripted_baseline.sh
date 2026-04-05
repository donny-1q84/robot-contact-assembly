#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/remote_common.sh"

rca_init_remote_vars "${1:-}" "${2:-}" "${3:-}"

TASK_NAME="${4:-RCA-PegInHole-Franka-IK-Rel-Play-v0}"
NUM_ENVS="${5:-1}"
STEPS="${6:-120}"
EXTRA_AGENT_ARGS="${7:-}"

echo "[scripted-baseline] env=${RCA_ENV_NAME} task=${TASK_NAME} num_envs=${NUM_ENVS} steps=${STEPS}"
if [[ -n "${EXTRA_AGENT_ARGS}" ]]; then
  echo "[scripted-baseline] extra_agent_args=${EXTRA_AGENT_ARGS}"
fi
rca_remote_repo_exec "/isaac-sim/python.sh scripts/scripted_agent.py --task ${TASK_NAME} --headless --num_envs ${NUM_ENVS} --steps ${STEPS} --approach-height 0.0 --approach-xy-tol 1.0 --approach-rot-tol 10.0 --settle-pos-gain 0.5 --settle-pos-clamp 0.012 --settle-rot-gain 3.0 --settle-rot-clamp 0.24 ${EXTRA_AGENT_ARGS}"
