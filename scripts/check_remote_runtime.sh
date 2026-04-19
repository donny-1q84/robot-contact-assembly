#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/remote_common.sh"

rca_init_remote_vars "${1:-}" "${2:-}" "${3:-}"

echo "[runtime] compose status on ${RCA_ENV_NAME}"
rca_brev_exec "cd \"${RCA_REMOTE_COMPOSE_ROOT}\" && ${RCA_COMPOSE_BASE} ps"

echo "[runtime] task container on ${RCA_ENV_NAME}"
rca_brev_exec "sudo docker ps --filter \"name=^/${RCA_REMOTE_TASK_CONTAINER}$\" --format \"table {{.Names}}\t{{.Status}}\t{{.Image}}\""

echo "[runtime] key package versions inside ${RCA_REMOTE_TASK_CONTAINER}"
rca_remote_container_exec "/isaac-sim/python.sh -m pip show numpy pillow lxml h5py hydra-core isaaclab isaaclab-rl 2>/dev/null | egrep '^(Name|Version):'"

echo "[runtime] registered peg-in-hole environments"
rca_remote_repo_exec "/isaac-sim/python.sh scripts/list_envs.py --keyword PegInHole"
