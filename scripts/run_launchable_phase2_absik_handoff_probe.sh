#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="${RCA_LAUNCHABLE_REPO_DIR:-/workspace/robot-contact-assembly}"
ARTIFACT_ROOT="${RCA_LAUNCHABLE_ARTIFACT_ROOT:-${REPO_DIR}/artifacts}"
ISAAC_PYTHON="${RCA_ISAAC_PYTHON:-/isaac-sim/python.sh}"
TASK_NAME="${RCA_LAUNCHABLE_TASK:-RCA-PegInHole-Franka-IK-Abs-Contact-Play-v0}"
SCRIPTED_STEPS="${RCA_LAUNCHABLE_SCRIPTED_STEPS:-1200}"
SEED="${RCA_LAUNCHABLE_SEED:-42}"
TIMEOUT_SECONDS="${RCA_LAUNCHABLE_TIMEOUT_SECONDS:-1500}"
HANDOFF_MAX_STRICT_MISS="${RCA_LAUNCHABLE_HANDOFF_MAX_STRICT_MISS:-1.0}"
ABS_CONTROL_MODE="${RCA_LAUNCHABLE_ABS_CONTROL_MODE:-waypoint}"
MDP_ABS_ORIENTATION_COMMAND_MODE="${RCA_LAUNCHABLE_MDP_ABS_ORIENTATION_COMMAND_MODE:-target}"
MDP_ABS_IK_METHOD="${RCA_LAUNCHABLE_MDP_ABS_IK_METHOD:-}"
INITIAL_JOINT_POS="${RCA_LAUNCHABLE_INITIAL_JOINT_POS:-}"
TARGET_ACTION_POS_OFFSET="${RCA_LAUNCHABLE_TARGET_ACTION_POS_OFFSET:-}"
DISABLE_SOCKET_WALL_COLLISIONS="${RCA_LAUNCHABLE_DISABLE_SOCKET_WALL_COLLISIONS:-0}"
FAIL_CLOSED_EXIT_ZERO="${RCA_LAUNCHABLE_FAIL_CLOSED_EXIT_ZERO:-0}"
export RCA_FORCE_APP_LAUNCHER="${RCA_FORCE_APP_LAUNCHER:-1}"
export RCA_ARTIFACT_ROOT="${RCA_ARTIFACT_ROOT:-${ARTIFACT_ROOT}}"

RUN_ID="$(date -u +"%Y-%m-%dT%H-%M-%SZ")"
SCRIPTED_DIR="${ARTIFACT_ROOT}/evaluations/scripted/${RUN_ID}_absik-handoff-probe"
SCRIPTED_SUMMARY_JSON="${SCRIPTED_DIR}/seed_${SEED}.json"
SCRIPTED_TRACE_JSON="${SCRIPTED_DIR}/seed_${SEED}_trace.json"
HANDOFF_JSON="${SCRIPTED_DIR}/handoff_selection.json"
PROBE_SUMMARY_JSON="${SCRIPTED_DIR}/probe_summary.json"
TRACKING_ANALYSIS_JSON="${SCRIPTED_DIR}/tracking_analysis.json"
COMMAND_PATH="${SCRIPTED_DIR}/command.txt"

if [[ ! -x "${ISAAC_PYTHON}" ]]; then
  echo "[launchable-absik-probe] missing Isaac Python: ${ISAAC_PYTHON}" >&2
  exit 2
fi

if [[ ! -d "${REPO_DIR}/source/robot_contact_assembly_tasks" ]]; then
  echo "[launchable-absik-probe] missing project repo at ${REPO_DIR}" >&2
  exit 2
fi

mkdir -p "${SCRIPTED_DIR}" "${ARTIFACT_ROOT}/hydra"

DEFAULT_SCRIPTED_ARGS=(
  --deterministic-reset
  --socket-pos 0.22,0.04,0.19
  --scripted-control-mode mdp
  --abs-control-mode "${ABS_CONTROL_MODE}"
  --mdp-abs-action-frame root
  --mdp-abs-orientation-command-mode "${MDP_ABS_ORIENTATION_COMMAND_MODE}"
  --abs-pos-step 0.030
  --abs-rot-step 0.12
  --orientation-target-mode axis-align-current
  --staged-approach
  --rotate-before-descend
  --rotate-control-mode target
  --approach-xy-tol 0.040
  --insert-xy-tol 0.0015
  --insert-rot-tol 0.12
  --insert-abort-xy-tol 0.080
  --insert-abort-rot-tol 0.50
  --insert-abort-grace-steps 8
  --insert-after-alignment
  --insert-descent-mode vertical
  --insert-vertical-step 0.020
  --insert-pos-step 0.004
  --insert-rot-step 0.02
  --hold-orientation-during-insert
  --polish-xy-tol 0.020
  --polish-z-tol 0.050
  --polish-rot-tol 0.20
  --polish-rotation-mode current
  --settle-xy-tol 0.0045
  --settle-rot-tol 0.18
  --settle-rot-gain 0.55
  --settle-rot-clamp 0.025
  --settle-contact-retention
  --settle-contact-min-force 0.0
  --settle-contact-preload-step 0.010
  --settle-contact-force-aware-xy
  --settle-contact-force-scale 1.0
  --settle-contact-force-xy-gain 0.003
  --settle-contact-force-xy-clamp 0.002
  --settle-contact-force-xy-sign 1.0
  --settle-contact-xy-tol 0.005
  --settle-contact-z-tol 0.045
  --settle-contact-rot-tol 0.20
  --settle-contact-exit-xy-tol 0.008
  --settle-contact-exit-z-tol 0.055
  --settle-contact-exit-rot-tol 0.24
  --branch-jump-xy-tol 0.08
  --success-xy-tol 0.005
  --success-z-tol 0.045
  --success-rot-tol 0.18
  --success-min-contact-force 0.5
  --debug-action-steps 4
)

if [[ -n "${MDP_ABS_IK_METHOD}" ]]; then
  DEFAULT_SCRIPTED_ARGS+=(--mdp-abs-ik-method "${MDP_ABS_IK_METHOD}")
fi

if [[ -n "${INITIAL_JOINT_POS}" ]]; then
  DEFAULT_SCRIPTED_ARGS+=(--initial-joint-pos "${INITIAL_JOINT_POS}")
fi

if [[ -n "${TARGET_ACTION_POS_OFFSET}" ]]; then
  DEFAULT_SCRIPTED_ARGS+=(--target-action-pos-offset "${TARGET_ACTION_POS_OFFSET}")
fi

if [[ "${DISABLE_SOCKET_WALL_COLLISIONS}" == "1" ]]; then
  DEFAULT_SCRIPTED_ARGS+=(--disable-socket-wall-collisions)
fi

if [[ -n "${RCA_LAUNCHABLE_SCRIPTED_AGENT_ARGS:-}" ]]; then
  # shellcheck disable=SC2206
  SCRIPTED_ARGS=(${RCA_LAUNCHABLE_SCRIPTED_AGENT_ARGS})
else
  SCRIPTED_ARGS=("${DEFAULT_SCRIPTED_ARGS[@]}")
fi

echo "[launchable-absik-probe] repo=${REPO_DIR}"
echo "[launchable-absik-probe] task=${TASK_NAME} scripted_steps=${SCRIPTED_STEPS} seed=${SEED}"
echo "[launchable-absik-probe] force_app_launcher=${RCA_FORCE_APP_LAUNCHER}"
echo "[launchable-absik-probe] abs_control_mode=${ABS_CONTROL_MODE}"
echo "[launchable-absik-probe] mdp_abs_ik_method=${MDP_ABS_IK_METHOD:-<task-default>}"
echo "[launchable-absik-probe] mdp_abs_orientation_command_mode=${MDP_ABS_ORIENTATION_COMMAND_MODE}"
echo "[launchable-absik-probe] initial_joint_pos=${INITIAL_JOINT_POS:-<default>}"
echo "[launchable-absik-probe] target_action_pos_offset=${TARGET_ACTION_POS_OFFSET:-<none>}"
echo "[launchable-absik-probe] disable_socket_wall_collisions=${DISABLE_SOCKET_WALL_COLLISIONS}"
echo "[launchable-absik-probe] handoff_max_strict_miss=${HANDOFF_MAX_STRICT_MISS}"
echo "[launchable-absik-probe] fail_closed_exit_zero=${FAIL_CLOSED_EXIT_ZERO}"
echo "[launchable-absik-probe] scripted_trace=${SCRIPTED_TRACE_JSON}"

"${ISAAC_PYTHON}" -m pip install --editable "${REPO_DIR}/source/robot_contact_assembly_tasks"

cd "${REPO_DIR}"

cat > "${COMMAND_PATH}" <<EOF
${ISAAC_PYTHON} scripts/scripted_agent.py --task ${TASK_NAME} --headless --num_envs 1 --steps ${SCRIPTED_STEPS} --seed ${SEED} --summary-json ${SCRIPTED_SUMMARY_JSON} --trace-json ${SCRIPTED_TRACE_JSON} ${SCRIPTED_ARGS[*]}
${ISAAC_PYTHON} scripts/select_preload_handoff_step.py --trace-json ${SCRIPTED_TRACE_JSON} --json
EOF

set +e
timeout "${TIMEOUT_SECONDS}" "${ISAAC_PYTHON}" scripts/scripted_agent.py \
  --task "${TASK_NAME}" \
  --headless \
  --num_envs 1 \
  --steps "${SCRIPTED_STEPS}" \
  --seed "${SEED}" \
  --summary-json "${SCRIPTED_SUMMARY_JSON}" \
  --trace-json "${SCRIPTED_TRACE_JSON}" \
  "${SCRIPTED_ARGS[@]}" \
  2>&1 | tee "${SCRIPTED_DIR}/scripted.log"
scripted_status=${PIPESTATUS[0]}
set -e

if [[ ${scripted_status} -ne 0 ]]; then
  echo "[launchable-absik-probe] scripted probe failed status=${scripted_status}; inspect ${SCRIPTED_DIR}/scripted.log" >&2
  exit "${scripted_status}"
fi

if [[ ! -s "${SCRIPTED_TRACE_JSON}" ]]; then
  echo "[launchable-absik-probe] missing scripted trace: ${SCRIPTED_TRACE_JSON}" >&2
  exit 1
fi

"${ISAAC_PYTHON}" scripts/select_preload_handoff_step.py \
  --trace-json "${SCRIPTED_TRACE_JSON}" \
  --json > "${HANDOFF_JSON}"
echo "[launchable-absik-probe] handoff_selection=${HANDOFF_JSON}"
cat "${HANDOFF_JSON}"
echo

"${ISAAC_PYTHON}" scripts/summarize_absik_handoff_probe.py \
  --trace-json "${SCRIPTED_TRACE_JSON}" \
  --summary-json "${SCRIPTED_SUMMARY_JSON}" \
  --handoff-json "${HANDOFF_JSON}" \
  --max-strict-miss "${HANDOFF_MAX_STRICT_MISS}" \
  | tee "${PROBE_SUMMARY_JSON}"
echo "[launchable-absik-probe] probe_summary=${PROBE_SUMMARY_JSON}"

"${ISAAC_PYTHON}" scripts/analyze_absik_probe_trace.py \
  --trace-json "${SCRIPTED_TRACE_JSON}" \
  --summary-json "${SCRIPTED_SUMMARY_JSON}" \
  --handoff-json "${HANDOFF_JSON}" \
  | tee "${TRACKING_ANALYSIS_JSON}"
echo "[launchable-absik-probe] tracking_analysis=${TRACKING_ANALYSIS_JSON}"

"${ISAAC_PYTHON}" - "${HANDOFF_JSON}" "${HANDOFF_MAX_STRICT_MISS}" "${FAIL_CLOSED_EXIT_ZERO}" <<'PY'
import json
import sys

handoff = json.load(open(sys.argv[1], encoding="utf-8"))
max_miss = float(sys.argv[2])
exit_zero = sys.argv[3].strip().lower() in {"1", "true", "yes", "y"}
miss = float(handoff["strict_miss_score"])
if miss > max_miss:
    message = (
        f"[launchable-absik-probe] selected handoff strict_miss_score={miss:.6f} "
        f"exceeds RCA_LAUNCHABLE_HANDOFF_MAX_STRICT_MISS={max_miss:.6f}"
    )
    if exit_zero:
        print(message)
        print("[launchable-absik-probe] fail_closed_exit_zero enabled; preserving artifacts and exiting 0")
        raise SystemExit(0)
    raise SystemExit(
        message
    )
print("[launchable-absik-probe] handoff strict-miss guard passed")
PY

echo "[launchable-absik-probe] scripted_summary=${SCRIPTED_SUMMARY_JSON}"
echo "[launchable-absik-probe] scripted_trace=${SCRIPTED_TRACE_JSON}"
echo "[launchable-absik-probe] probe_summary=${PROBE_SUMMARY_JSON}"
echo "[launchable-absik-probe] tracking_analysis=${TRACKING_ANALYSIS_JSON}"
echo "[launchable-absik-probe] command=${COMMAND_PATH}"
