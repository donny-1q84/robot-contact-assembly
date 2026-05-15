#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/remote_common.sh"

rca_init_remote_vars "${1:-}" "${2:-}" "${3:-}"

TASK_NAME="${4:-RCA-PegInHole-Franka-IK-Abs-Contact-Play-v0}"
NUM_ENVS="${5:-1}"
SEED="${6:-42}"
TIMEOUT_SECONDS="${7:-240}"
COMMON_AGENT_ARGS="${RCA_SCRIPTED_REACH_SWEEP_COMMON_ARGS:---deterministic-reset --socket-pos 0.22,0.04,0.19 --staged-approach --approach-xy-tol 0.04 --debug-action-steps 4}"

TIMESTAMP_UTC="$(date -u +"%Y-%m-%dT%H-%M-%SZ")"
REMOTE_SWEEP_DIR="/workspace/artifacts/evaluations/scripted_reach_sweep/${TIMESTAMP_UTC}"

case_names=(
  "waypoint_40_step012"
  "target_40"
  "waypoint_80_step030"
)
case_steps=(
  "40"
  "40"
  "80"
)
case_args=(
  "--abs-control-mode waypoint --abs-pos-step 0.012 --abs-rot-step 0.12"
  "--abs-control-mode target --abs-rot-step 0.12"
  "--abs-control-mode waypoint --abs-pos-step 0.030 --abs-rot-step 0.12"
)

echo "[scripted-reach-sweep] env=${RCA_ENV_NAME} task=${TASK_NAME} num_envs=${NUM_ENVS} seed=${SEED}"
echo "[scripted-reach-sweep] timeout_seconds=${TIMEOUT_SECONDS}"
echo "[scripted-reach-sweep] common_agent_args=${COMMON_AGENT_ARGS}"
rca_remote_container_exec "mkdir -p '${REMOTE_SWEEP_DIR}'"

for index in "${!case_names[@]}"; do
  name="${case_names[${index}]}"
  steps="${case_steps[${index}]}"
  args="${case_args[${index}]}"
  case_dir="${REMOTE_SWEEP_DIR}/${name}"
  summary_path="${case_dir}/seed_${SEED}.json"
  trace_path="${case_dir}/seed_${SEED}_trace.json"
  log_path="${case_dir}/seed_${SEED}.log"

  echo "[scripted-reach-sweep] case=${name} steps=${steps} args=${args}"
  rca_remote_container_exec "mkdir -p '${case_dir}' && rm -f '${summary_path}' '${trace_path}' '${log_path}'"
  rca_remote_repo_exec "set -o pipefail && timeout ${TIMEOUT_SECONDS} /isaac-sim/python.sh scripts/scripted_agent.py --task ${TASK_NAME} --headless --num_envs ${NUM_ENVS} --steps ${steps} --seed ${SEED} --summary-json ${summary_path} --trace-json ${trace_path} ${COMMON_AGENT_ARGS} ${args} 2>&1 | tee ${log_path}"
  rca_remote_container_exec "test -s '${summary_path}' && test -s '${trace_path}'"
done

echo "[scripted-reach-sweep] summaries:"
rca_remote_container_exec "/isaac-sim/python.sh - <<'PY'
import json
from pathlib import Path

root = Path('${REMOTE_SWEEP_DIR}')
rows = []
for path in sorted(root.glob('*/seed_${SEED}.json')):
    data = json.loads(path.read_text())
    rows.append((
        path.parent.name,
        data.get('steps_requested'),
        data.get('best_action_tip_alignment'),
        data.get('initial_lateral'),
        data.get('final_lateral'),
        data.get('best_lateral'),
        data.get('best_lateral_step'),
        data.get('final_axial'),
        data.get('best_rot'),
        data.get('final_success_rate'),
        data.get('success_step'),
    ))

header = (
    'case', 'steps', 'best_align', 'init_lat', 'final_lat', 'best_lat',
    'best_lat_step', 'final_axial', 'best_rot', 'success', 'success_step'
)
print('\\t'.join(header))
for row in rows:
    print('\\t'.join(str(value) for value in row))
PY"
echo "[scripted-reach-sweep] output dir: ${REMOTE_SWEEP_DIR}"
