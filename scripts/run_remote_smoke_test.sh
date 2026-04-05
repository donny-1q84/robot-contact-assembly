#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/remote_common.sh"

rca_init_remote_vars "${1:-}" "${2:-}" "${3:-}"

echo "[smoke] compose status on ${RCA_ENV_NAME}"
rca_brev_exec "cd \"${RCA_REMOTE_COMPOSE_ROOT}\" && ${RCA_COMPOSE_BASE} ps"

echo "[smoke] listing registered peg-in-hole environments on ${RCA_ENV_NAME}"
rca_remote_repo_exec "/isaac-sim/python.sh scripts/list_envs.py --keyword PegInHole"

echo "[smoke] running zero-action smoke test"
rca_remote_repo_exec "/isaac-sim/python.sh scripts/zero_agent.py --task RCA-PegInHole-Franka-IK-Rel-Play-v0 --headless --num_envs 1 --steps 5"
