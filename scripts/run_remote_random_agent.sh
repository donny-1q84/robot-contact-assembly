#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/remote_common.sh"

rca_init_remote_vars "${1:-}" "${2:-}" "${3:-}"

TASK_NAME="${4:-RCA-PegInHole-Franka-IK-Rel-Play-v0}"
NUM_ENVS="${5:-1}"
STEPS="${6:-5}"

echo "[random-agent] env=${RCA_ENV_NAME} task=${TASK_NAME} num_envs=${NUM_ENVS} steps=${STEPS}"
rca_remote_repo_exec "/isaac-sim/python.sh scripts/random_agent.py --task ${TASK_NAME} --headless --num_envs ${NUM_ENVS} --steps ${STEPS}"
