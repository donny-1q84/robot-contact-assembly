#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="${RCA_LAUNCHABLE_REPO_DIR:-/workspace/robot-contact-assembly}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
"${SCRIPT_DIR}/launchable_post_contact_gate.sh" "${REPO_DIR}"
ARTIFACT_ROOT="${RCA_LAUNCHABLE_ARTIFACT_ROOT:-${REPO_DIR}/artifacts}"
ISAAC_PYTHON="${RCA_ISAAC_PYTHON:-/isaac-sim/python.sh}"
TASK_NAME="${RCA_LAUNCHABLE_TASK:-RCA-PegInHole-Franka-JointPos-Contact-Play-v0}"
SCRIPTED_STEPS="${RCA_LAUNCHABLE_SCRIPTED_STEPS:-900}"
SEED="${RCA_LAUNCHABLE_SEED:-42}"
TIMEOUT_SECONDS="${RCA_LAUNCHABLE_TIMEOUT_SECONDS:-1500}"
HANDOFF_MAX_STRICT_MISS="${RCA_LAUNCHABLE_HANDOFF_MAX_STRICT_MISS:-1.0}"
ABS_CONTROL_MODE="${RCA_LAUNCHABLE_ABS_CONTROL_MODE:-waypoint}"
JOINT_IK_STEP="${RCA_LAUNCHABLE_JOINT_IK_STEP:-0.035}"
JOINT_STEP_LIMIT_MODE="${RCA_LAUNCHABLE_JOINT_STEP_LIMIT_MODE:-after-xy-global}"
JOINT_LIMIT_MARGIN="${RCA_LAUNCHABLE_JOINT_LIMIT_MARGIN:-0.020}"
INSERT_JOINT_LIMIT_MARGIN="${RCA_LAUNCHABLE_INSERT_JOINT_LIMIT_MARGIN:-}"
JOINT_LIMIT_NULLSPACE_GAIN="${RCA_LAUNCHABLE_JOINT_LIMIT_NULLSPACE_GAIN:-0.050}"
JOINT_LIMIT_NULLSPACE_ACTIVATION_MARGIN="${RCA_LAUNCHABLE_JOINT_LIMIT_NULLSPACE_ACTIVATION_MARGIN:-0.250}"
JOINT_LIMIT_NULLSPACE_STEP="${RCA_LAUNCHABLE_JOINT_LIMIT_NULLSPACE_STEP:-0.030}"
JOINT_LIMIT_NULLSPACE_DAMPING="${RCA_LAUNCHABLE_JOINT_LIMIT_NULLSPACE_DAMPING:-0.050}"
JOINT_LIMIT_GUARD_GAIN="${RCA_LAUNCHABLE_JOINT_LIMIT_GUARD_GAIN:-0.000}"
JOINT_LIMIT_GUARD_ACTIVATION_MARGIN="${RCA_LAUNCHABLE_JOINT_LIMIT_GUARD_ACTIVATION_MARGIN:-0.200}"
JOINT_LIMIT_GUARD_STEP="${RCA_LAUNCHABLE_JOINT_LIMIT_GUARD_STEP:-0.050}"
REACHABLE_APPROACH="${RCA_LAUNCHABLE_REACHABLE_APPROACH:-0}"
REACHABLE_APPROACH_START_RADIUS="${RCA_LAUNCHABLE_REACHABLE_APPROACH_START_RADIUS:-0.060}"
REACHABLE_APPROACH_MIN_RADIUS="${RCA_LAUNCHABLE_REACHABLE_APPROACH_MIN_RADIUS:-0.000}"
REACHABLE_APPROACH_SHRINK_STEP="${RCA_LAUNCHABLE_REACHABLE_APPROACH_SHRINK_STEP:-0.002}"
REACHABLE_APPROACH_SHRINK_XY_TOL="${RCA_LAUNCHABLE_REACHABLE_APPROACH_SHRINK_XY_TOL:-0.015}"
REACHABLE_APPROACH_JOINT_MARGIN_MIN="${RCA_LAUNCHABLE_REACHABLE_APPROACH_JOINT_MARGIN_MIN:-0.080}"
ROTATE_DESCENT_MODE="${RCA_LAUNCHABLE_ROTATE_DESCENT_MODE:-hold}"
ROTATE_XY_RETENTION="${RCA_LAUNCHABLE_ROTATE_XY_RETENTION:-0}"
ROTATE_XY_RETENTION_TOL="${RCA_LAUNCHABLE_ROTATE_XY_RETENTION_TOL:-0.012}"
DESCEND_XY_RETENTION="${RCA_LAUNCHABLE_DESCEND_XY_RETENTION:-0}"
DESCEND_XY_RETENTION_TOL="${RCA_LAUNCHABLE_DESCEND_XY_RETENTION_TOL:-0.012}"
HOLD_ORIENTATION_DURING_INSERT="${RCA_LAUNCHABLE_HOLD_ORIENTATION_DURING_INSERT:-1}"
INSERT_ROTATION_GATED_DESCENT="${RCA_LAUNCHABLE_INSERT_ROTATION_GATED_DESCENT:-0}"
INSERT_DESCENT_ROT_TOL="${RCA_LAUNCHABLE_INSERT_DESCENT_ROT_TOL:-}"
INSERT_ROTATION_GATE_DESCENT_SCALE="${RCA_LAUNCHABLE_INSERT_ROTATION_GATE_DESCENT_SCALE:-0.0}"
INSERT_ROTATION_GATE_MIN_DESCENT_STEP="${RCA_LAUNCHABLE_INSERT_ROTATION_GATE_MIN_DESCENT_STEP:-0.0}"
INSERT_ROTATION_GATE_NEAR_DEPTH_Z_TOL="${RCA_LAUNCHABLE_INSERT_ROTATION_GATE_NEAR_DEPTH_Z_TOL:-}"
INSERT_ROTATION_GATE_NEAR_DEPTH_ROT_TOL="${RCA_LAUNCHABLE_INSERT_ROTATION_GATE_NEAR_DEPTH_ROT_TOL:-}"
INSERT_ROTATION_GATE_NEAR_DEPTH_DESCENT_SCALE="${RCA_LAUNCHABLE_INSERT_ROTATION_GATE_NEAR_DEPTH_DESCENT_SCALE:-}"
INSERT_ROTATION_GATE_NEAR_DEPTH_MIN_DESCENT_STEP="${RCA_LAUNCHABLE_INSERT_ROTATION_GATE_NEAR_DEPTH_MIN_DESCENT_STEP:-}"
DEPTH_ROTATION_POLISH="${RCA_LAUNCHABLE_DEPTH_ROTATION_POLISH:-0}"
DEPTH_ROTATION_POLISH_XY_TOL="${RCA_LAUNCHABLE_DEPTH_ROTATION_POLISH_XY_TOL:-}"
DEPTH_ROTATION_POLISH_Z_TOL="${RCA_LAUNCHABLE_DEPTH_ROTATION_POLISH_Z_TOL:-}"
DEPTH_ROTATION_POLISH_CONTACT_MIN_FORCE="${RCA_LAUNCHABLE_DEPTH_ROTATION_POLISH_CONTACT_MIN_FORCE:-}"
DEPTH_ROTATION_POLISH_EXIT_CONTACT_MIN_FORCE="${RCA_LAUNCHABLE_DEPTH_ROTATION_POLISH_EXIT_CONTACT_MIN_FORCE:-}"
DEPTH_ROTATION_POLISH_ORIENTATION_MODE="${RCA_LAUNCHABLE_DEPTH_ROTATION_POLISH_ORIENTATION_MODE:-target}"
DEPTH_ROTATION_POLISH_EXIT_XY_TOL="${RCA_LAUNCHABLE_DEPTH_ROTATION_POLISH_EXIT_XY_TOL:-0.012}"
DEPTH_ROTATION_POLISH_EXIT_Z_TOL="${RCA_LAUNCHABLE_DEPTH_ROTATION_POLISH_EXIT_Z_TOL:-0.060}"
DEPTH_ROTATION_POLISH_PRELOAD_STEP="${RCA_LAUNCHABLE_DEPTH_ROTATION_POLISH_PRELOAD_STEP:-0.001}"
DEPTH_ROTATION_POLISH_ROT_STEP="${RCA_LAUNCHABLE_DEPTH_ROTATION_POLISH_ROT_STEP:-}"
DEPTH_ROTATION_POLISH_POS_GAIN="${RCA_LAUNCHABLE_DEPTH_ROTATION_POLISH_POS_GAIN:-1.0}"
DEPTH_ROTATION_POLISH_POS_CLAMP="${RCA_LAUNCHABLE_DEPTH_ROTATION_POLISH_POS_CLAMP:-0.004}"
DEPTH_ROTATION_POLISH_ROT_GAIN="${RCA_LAUNCHABLE_DEPTH_ROTATION_POLISH_ROT_GAIN:-3.0}"
DEPTH_ROTATION_POLISH_ROT_CLAMP="${RCA_LAUNCHABLE_DEPTH_ROTATION_POLISH_ROT_CLAMP:-0.16}"
PROBE_LABEL="${RCA_LAUNCHABLE_JOINTPOS_PROBE_LABEL:-jointpos-nullspace-probe}"
FAIL_CLOSED_EXIT_ZERO="${RCA_LAUNCHABLE_FAIL_CLOSED_EXIT_ZERO:-0}"
export RCA_FORCE_APP_LAUNCHER="${RCA_FORCE_APP_LAUNCHER:-1}"
export RCA_ARTIFACT_ROOT="${RCA_ARTIFACT_ROOT:-${ARTIFACT_ROOT}}"

RUN_ID="$(date -u +"%Y-%m-%dT%H-%M-%SZ")"
SCRIPTED_DIR="${ARTIFACT_ROOT}/evaluations/scripted/${RUN_ID}_${PROBE_LABEL}"
SCRIPTED_SUMMARY_JSON="${SCRIPTED_DIR}/seed_${SEED}.json"
SCRIPTED_TRACE_JSON="${SCRIPTED_DIR}/seed_${SEED}_trace.json"
HANDOFF_JSON="${SCRIPTED_DIR}/handoff_selection.json"
PROBE_SUMMARY_JSON="${SCRIPTED_DIR}/probe_summary.json"
TRACKING_ANALYSIS_JSON="${SCRIPTED_DIR}/tracking_analysis.json"
COMMAND_PATH="${SCRIPTED_DIR}/command.txt"

if [[ ! -x "${ISAAC_PYTHON}" ]]; then
  echo "[launchable-jointpos-nullspace-probe] missing Isaac Python: ${ISAAC_PYTHON}" >&2
  exit 2
fi

if [[ ! -d "${REPO_DIR}/source/robot_contact_assembly_tasks" ]]; then
  echo "[launchable-jointpos-nullspace-probe] missing project repo at ${REPO_DIR}" >&2
  exit 2
fi

mkdir -p "${SCRIPTED_DIR}" "${ARTIFACT_ROOT}/hydra"

DEFAULT_SCRIPTED_ARGS=(
  --deterministic-reset
  --socket-pos 0.22,0.04,0.19
  --scripted-control-mode joint-ik
  --abs-control-mode "${ABS_CONTROL_MODE}"
  --abs-pos-step 0.010
  --abs-rot-step 0.10
  --joint-ik-step "${JOINT_IK_STEP}"
  --joint-step-limit-mode "${JOINT_STEP_LIMIT_MODE}"
  --joint-limit-margin "${JOINT_LIMIT_MARGIN}"
  --joint-limit-nullspace-gain "${JOINT_LIMIT_NULLSPACE_GAIN}"
  --joint-limit-nullspace-activation-margin "${JOINT_LIMIT_NULLSPACE_ACTIVATION_MARGIN}"
  --joint-limit-nullspace-step "${JOINT_LIMIT_NULLSPACE_STEP}"
  --joint-limit-nullspace-damping "${JOINT_LIMIT_NULLSPACE_DAMPING}"
  --joint-limit-guard-gain "${JOINT_LIMIT_GUARD_GAIN}"
  --joint-limit-guard-activation-margin "${JOINT_LIMIT_GUARD_ACTIVATION_MARGIN}"
  --joint-limit-guard-step "${JOINT_LIMIT_GUARD_STEP}"
  --orientation-target-mode axis-align-current
  --staged-approach
  --rotate-before-descend
  --rotate-descent-mode "${ROTATE_DESCENT_MODE}"
  --rotate-control-mode stateful-waypoint
  --hold-orientation-during-descend
  --insert-after-alignment
  --insert-descent-mode vertical
  --insert-vertical-step 0.020
  --insert-pos-step 0.004
  --insert-rot-step 0.02
  --insert-abort-grace-steps 8
  --insert-abort-xy-tol 0.080
  --insert-abort-rot-tol 0.50
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

if [[ -n "${INSERT_JOINT_LIMIT_MARGIN}" ]]; then
  DEFAULT_SCRIPTED_ARGS+=(--insert-joint-limit-margin "${INSERT_JOINT_LIMIT_MARGIN}")
fi

if [[ "${HOLD_ORIENTATION_DURING_INSERT}" =~ ^(1|true|TRUE|yes|YES|y|Y)$ ]]; then
  DEFAULT_SCRIPTED_ARGS+=(--hold-orientation-during-insert)
fi

if [[ "${INSERT_ROTATION_GATED_DESCENT}" =~ ^(1|true|TRUE|yes|YES|y|Y)$ ]]; then
  DEFAULT_SCRIPTED_ARGS+=(--insert-rotation-gated-descent)
  if [[ -n "${INSERT_DESCENT_ROT_TOL}" ]]; then
    DEFAULT_SCRIPTED_ARGS+=(--insert-descent-rot-tol "${INSERT_DESCENT_ROT_TOL}")
  fi
  DEFAULT_SCRIPTED_ARGS+=(
    --insert-rotation-gate-descent-scale "${INSERT_ROTATION_GATE_DESCENT_SCALE}"
    --insert-rotation-gate-min-descent-step "${INSERT_ROTATION_GATE_MIN_DESCENT_STEP}"
  )
  if [[ -n "${INSERT_ROTATION_GATE_NEAR_DEPTH_Z_TOL}" ]]; then
    DEFAULT_SCRIPTED_ARGS+=(--insert-rotation-gate-near-depth-z-tol "${INSERT_ROTATION_GATE_NEAR_DEPTH_Z_TOL}")
  fi
  if [[ -n "${INSERT_ROTATION_GATE_NEAR_DEPTH_ROT_TOL}" ]]; then
    DEFAULT_SCRIPTED_ARGS+=(--insert-rotation-gate-near-depth-rot-tol "${INSERT_ROTATION_GATE_NEAR_DEPTH_ROT_TOL}")
  fi
  if [[ -n "${INSERT_ROTATION_GATE_NEAR_DEPTH_DESCENT_SCALE}" ]]; then
    DEFAULT_SCRIPTED_ARGS+=(
      --insert-rotation-gate-near-depth-descent-scale "${INSERT_ROTATION_GATE_NEAR_DEPTH_DESCENT_SCALE}"
    )
  fi
  if [[ -n "${INSERT_ROTATION_GATE_NEAR_DEPTH_MIN_DESCENT_STEP}" ]]; then
    DEFAULT_SCRIPTED_ARGS+=(
      --insert-rotation-gate-near-depth-min-descent-step "${INSERT_ROTATION_GATE_NEAR_DEPTH_MIN_DESCENT_STEP}"
    )
  fi
elif [[ -n "${INSERT_DESCENT_ROT_TOL}" ]]; then
  echo "[launchable-jointpos-nullspace-probe] ignoring insert_descent_rot_tol because insert_rotation_gated_descent=0" >&2
fi

if [[ "${DEPTH_ROTATION_POLISH}" =~ ^(1|true|TRUE|yes|YES|y|Y)$ ]]; then
  DEFAULT_SCRIPTED_ARGS+=(--depth-rotation-polish)
  if [[ -n "${DEPTH_ROTATION_POLISH_XY_TOL}" ]]; then
    DEFAULT_SCRIPTED_ARGS+=(--depth-rotation-polish-xy-tol "${DEPTH_ROTATION_POLISH_XY_TOL}")
  fi
  if [[ -n "${DEPTH_ROTATION_POLISH_Z_TOL}" ]]; then
    DEFAULT_SCRIPTED_ARGS+=(--depth-rotation-polish-z-tol "${DEPTH_ROTATION_POLISH_Z_TOL}")
  fi
  if [[ -n "${DEPTH_ROTATION_POLISH_CONTACT_MIN_FORCE}" ]]; then
    DEFAULT_SCRIPTED_ARGS+=(--depth-rotation-polish-contact-min-force "${DEPTH_ROTATION_POLISH_CONTACT_MIN_FORCE}")
  fi
  if [[ -n "${DEPTH_ROTATION_POLISH_EXIT_CONTACT_MIN_FORCE}" ]]; then
    DEFAULT_SCRIPTED_ARGS+=(
      --depth-rotation-polish-exit-contact-min-force "${DEPTH_ROTATION_POLISH_EXIT_CONTACT_MIN_FORCE}"
    )
  fi
  DEFAULT_SCRIPTED_ARGS+=(
    --depth-rotation-polish-orientation-mode "${DEPTH_ROTATION_POLISH_ORIENTATION_MODE}"
    --depth-rotation-polish-exit-xy-tol "${DEPTH_ROTATION_POLISH_EXIT_XY_TOL}"
    --depth-rotation-polish-exit-z-tol "${DEPTH_ROTATION_POLISH_EXIT_Z_TOL}"
    --depth-rotation-polish-preload-step "${DEPTH_ROTATION_POLISH_PRELOAD_STEP}"
    --depth-rotation-polish-pos-gain "${DEPTH_ROTATION_POLISH_POS_GAIN}"
    --depth-rotation-polish-pos-clamp "${DEPTH_ROTATION_POLISH_POS_CLAMP}"
    --depth-rotation-polish-rot-gain "${DEPTH_ROTATION_POLISH_ROT_GAIN}"
    --depth-rotation-polish-rot-clamp "${DEPTH_ROTATION_POLISH_ROT_CLAMP}"
  )
  if [[ -n "${DEPTH_ROTATION_POLISH_ROT_STEP}" ]]; then
    DEFAULT_SCRIPTED_ARGS+=(--depth-rotation-polish-rot-step "${DEPTH_ROTATION_POLISH_ROT_STEP}")
  fi
fi

if [[ "${REACHABLE_APPROACH}" =~ ^(1|true|TRUE|yes|YES|y|Y)$ ]]; then
  DEFAULT_SCRIPTED_ARGS+=(
    --reachable-approach
    --reachable-approach-start-radius "${REACHABLE_APPROACH_START_RADIUS}"
    --reachable-approach-min-radius "${REACHABLE_APPROACH_MIN_RADIUS}"
    --reachable-approach-shrink-step "${REACHABLE_APPROACH_SHRINK_STEP}"
    --reachable-approach-shrink-xy-tol "${REACHABLE_APPROACH_SHRINK_XY_TOL}"
    --reachable-approach-joint-margin-min "${REACHABLE_APPROACH_JOINT_MARGIN_MIN}"
  )
fi

if [[ "${ROTATE_XY_RETENTION}" =~ ^(1|true|TRUE|yes|YES|y|Y)$ ]]; then
  DEFAULT_SCRIPTED_ARGS+=(--rotate-xy-retention --rotate-xy-retention-tol "${ROTATE_XY_RETENTION_TOL}")
fi

if [[ "${DESCEND_XY_RETENTION}" =~ ^(1|true|TRUE|yes|YES|y|Y)$ ]]; then
  DEFAULT_SCRIPTED_ARGS+=(--descend-xy-retention --descend-xy-retention-tol "${DESCEND_XY_RETENTION_TOL}")
fi

if [[ -n "${RCA_LAUNCHABLE_SCRIPTED_AGENT_ARGS:-}" ]]; then
  # shellcheck disable=SC2206
  SCRIPTED_ARGS=(${RCA_LAUNCHABLE_SCRIPTED_AGENT_ARGS})
else
  SCRIPTED_ARGS=("${DEFAULT_SCRIPTED_ARGS[@]}")
fi

echo "[launchable-jointpos-nullspace-probe] repo=${REPO_DIR}"
echo "[launchable-jointpos-nullspace-probe] task=${TASK_NAME} scripted_steps=${SCRIPTED_STEPS} seed=${SEED}"
echo "[launchable-jointpos-nullspace-probe] force_app_launcher=${RCA_FORCE_APP_LAUNCHER}"
echo "[launchable-jointpos-nullspace-probe] abs_control_mode=${ABS_CONTROL_MODE}"
echo "[launchable-jointpos-nullspace-probe] joint_ik_step=${JOINT_IK_STEP}"
echo "[launchable-jointpos-nullspace-probe] joint_step_limit_mode=${JOINT_STEP_LIMIT_MODE}"
echo "[launchable-jointpos-nullspace-probe] joint_limit_margin=${JOINT_LIMIT_MARGIN}"
echo "[launchable-jointpos-nullspace-probe] insert_joint_limit_margin=${INSERT_JOINT_LIMIT_MARGIN:-<unset>}"
echo "[launchable-jointpos-nullspace-probe] joint_limit_nullspace_gain=${JOINT_LIMIT_NULLSPACE_GAIN}"
echo "[launchable-jointpos-nullspace-probe] joint_limit_nullspace_activation_margin=${JOINT_LIMIT_NULLSPACE_ACTIVATION_MARGIN}"
echo "[launchable-jointpos-nullspace-probe] joint_limit_nullspace_step=${JOINT_LIMIT_NULLSPACE_STEP}"
echo "[launchable-jointpos-nullspace-probe] joint_limit_nullspace_damping=${JOINT_LIMIT_NULLSPACE_DAMPING}"
echo "[launchable-jointpos-nullspace-probe] joint_limit_guard_gain=${JOINT_LIMIT_GUARD_GAIN}"
echo "[launchable-jointpos-nullspace-probe] joint_limit_guard_activation_margin=${JOINT_LIMIT_GUARD_ACTIVATION_MARGIN}"
echo "[launchable-jointpos-nullspace-probe] joint_limit_guard_step=${JOINT_LIMIT_GUARD_STEP}"
echo "[launchable-jointpos-nullspace-probe] reachable_approach=${REACHABLE_APPROACH}"
echo "[launchable-jointpos-nullspace-probe] reachable_approach_start_radius=${REACHABLE_APPROACH_START_RADIUS}"
echo "[launchable-jointpos-nullspace-probe] reachable_approach_min_radius=${REACHABLE_APPROACH_MIN_RADIUS}"
echo "[launchable-jointpos-nullspace-probe] reachable_approach_shrink_step=${REACHABLE_APPROACH_SHRINK_STEP}"
echo "[launchable-jointpos-nullspace-probe] reachable_approach_shrink_xy_tol=${REACHABLE_APPROACH_SHRINK_XY_TOL}"
echo "[launchable-jointpos-nullspace-probe] reachable_approach_joint_margin_min=${REACHABLE_APPROACH_JOINT_MARGIN_MIN}"
echo "[launchable-jointpos-nullspace-probe] rotate_descent_mode=${ROTATE_DESCENT_MODE}"
echo "[launchable-jointpos-nullspace-probe] rotate_xy_retention=${ROTATE_XY_RETENTION} tol=${ROTATE_XY_RETENTION_TOL}"
echo "[launchable-jointpos-nullspace-probe] descend_xy_retention=${DESCEND_XY_RETENTION} tol=${DESCEND_XY_RETENTION_TOL}"
echo "[launchable-jointpos-nullspace-probe] hold_orientation_during_insert=${HOLD_ORIENTATION_DURING_INSERT}"
echo "[launchable-jointpos-nullspace-probe] insert_rotation_gated_descent=${INSERT_ROTATION_GATED_DESCENT} tol=${INSERT_DESCENT_ROT_TOL:-<default>}"
echo "[launchable-jointpos-nullspace-probe] insert_rotation_gate_descent_scale=${INSERT_ROTATION_GATE_DESCENT_SCALE}"
echo "[launchable-jointpos-nullspace-probe] insert_rotation_gate_min_descent_step=${INSERT_ROTATION_GATE_MIN_DESCENT_STEP}"
echo "[launchable-jointpos-nullspace-probe] insert_rotation_gate_near_depth_z_tol=${INSERT_ROTATION_GATE_NEAR_DEPTH_Z_TOL:-<unset>}"
echo "[launchable-jointpos-nullspace-probe] insert_rotation_gate_near_depth_rot_tol=${INSERT_ROTATION_GATE_NEAR_DEPTH_ROT_TOL:-<unset>}"
echo "[launchable-jointpos-nullspace-probe] insert_rotation_gate_near_depth_descent_scale=${INSERT_ROTATION_GATE_NEAR_DEPTH_DESCENT_SCALE:-<unset>}"
echo "[launchable-jointpos-nullspace-probe] insert_rotation_gate_near_depth_min_descent_step=${INSERT_ROTATION_GATE_NEAR_DEPTH_MIN_DESCENT_STEP:-<unset>}"
echo "[launchable-jointpos-nullspace-probe] depth_rotation_polish=${DEPTH_ROTATION_POLISH}"
echo "[launchable-jointpos-nullspace-probe] depth_rotation_polish_xy_tol=${DEPTH_ROTATION_POLISH_XY_TOL:-<default>}"
echo "[launchable-jointpos-nullspace-probe] depth_rotation_polish_z_tol=${DEPTH_ROTATION_POLISH_Z_TOL:-<default>}"
echo "[launchable-jointpos-nullspace-probe] depth_rotation_polish_contact_min_force=${DEPTH_ROTATION_POLISH_CONTACT_MIN_FORCE:-<default>}"
echo "[launchable-jointpos-nullspace-probe] depth_rotation_polish_exit_contact_min_force=${DEPTH_ROTATION_POLISH_EXIT_CONTACT_MIN_FORCE:-<unset>}"
echo "[launchable-jointpos-nullspace-probe] depth_rotation_polish_orientation_mode=${DEPTH_ROTATION_POLISH_ORIENTATION_MODE}"
echo "[launchable-jointpos-nullspace-probe] depth_rotation_polish_exit_xy_tol=${DEPTH_ROTATION_POLISH_EXIT_XY_TOL}"
echo "[launchable-jointpos-nullspace-probe] depth_rotation_polish_exit_z_tol=${DEPTH_ROTATION_POLISH_EXIT_Z_TOL}"
echo "[launchable-jointpos-nullspace-probe] depth_rotation_polish_preload_step=${DEPTH_ROTATION_POLISH_PRELOAD_STEP}"
echo "[launchable-jointpos-nullspace-probe] depth_rotation_polish_rot_step=${DEPTH_ROTATION_POLISH_ROT_STEP:-<unset>}"
echo "[launchable-jointpos-nullspace-probe] handoff_max_strict_miss=${HANDOFF_MAX_STRICT_MISS}"
echo "[launchable-jointpos-nullspace-probe] fail_closed_exit_zero=${FAIL_CLOSED_EXIT_ZERO}"
echo "[launchable-jointpos-nullspace-probe] scripted_trace=${SCRIPTED_TRACE_JSON}"

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
  echo "[launchable-jointpos-nullspace-probe] scripted probe failed status=${scripted_status}; inspect ${SCRIPTED_DIR}/scripted.log" >&2
  exit "${scripted_status}"
fi

if [[ ! -s "${SCRIPTED_TRACE_JSON}" ]]; then
  echo "[launchable-jointpos-nullspace-probe] missing scripted trace: ${SCRIPTED_TRACE_JSON}" >&2
  exit 1
fi

"${ISAAC_PYTHON}" scripts/select_preload_handoff_step.py \
  --trace-json "${SCRIPTED_TRACE_JSON}" \
  --json > "${HANDOFF_JSON}"
echo "[launchable-jointpos-nullspace-probe] handoff_selection=${HANDOFF_JSON}"
cat "${HANDOFF_JSON}"
echo

"${ISAAC_PYTHON}" scripts/summarize_absik_handoff_probe.py \
  --trace-json "${SCRIPTED_TRACE_JSON}" \
  --summary-json "${SCRIPTED_SUMMARY_JSON}" \
  --handoff-json "${HANDOFF_JSON}" \
  --max-strict-miss "${HANDOFF_MAX_STRICT_MISS}" \
  | tee "${PROBE_SUMMARY_JSON}"
echo "[launchable-jointpos-nullspace-probe] probe_summary=${PROBE_SUMMARY_JSON}"

"${ISAAC_PYTHON}" scripts/analyze_absik_probe_trace.py \
  --trace-json "${SCRIPTED_TRACE_JSON}" \
  --summary-json "${SCRIPTED_SUMMARY_JSON}" \
  --handoff-json "${HANDOFF_JSON}" \
  | tee "${TRACKING_ANALYSIS_JSON}"
echo "[launchable-jointpos-nullspace-probe] tracking_analysis=${TRACKING_ANALYSIS_JSON}"

"${ISAAC_PYTHON}" - "${HANDOFF_JSON}" "${HANDOFF_MAX_STRICT_MISS}" "${FAIL_CLOSED_EXIT_ZERO}" <<'PY'
import json
import sys

handoff = json.load(open(sys.argv[1], encoding="utf-8"))
max_miss = float(sys.argv[2])
exit_zero = sys.argv[3].strip().lower() in {"1", "true", "yes", "y"}
miss = float(handoff["strict_miss_score"])
if miss > max_miss:
    message = (
        f"[launchable-jointpos-nullspace-probe] selected handoff strict_miss_score={miss:.6f} "
        f"exceeds RCA_LAUNCHABLE_HANDOFF_MAX_STRICT_MISS={max_miss:.6f}"
    )
    if exit_zero:
        print(message)
        print("[launchable-jointpos-nullspace-probe] fail_closed_exit_zero enabled; preserving artifacts and exiting 0")
        raise SystemExit(0)
    raise SystemExit(message)
print("[launchable-jointpos-nullspace-probe] handoff strict-miss guard passed")
PY

echo "[launchable-jointpos-nullspace-probe] scripted_summary=${SCRIPTED_SUMMARY_JSON}"
echo "[launchable-jointpos-nullspace-probe] scripted_trace=${SCRIPTED_TRACE_JSON}"
echo "[launchable-jointpos-nullspace-probe] probe_summary=${PROBE_SUMMARY_JSON}"
echo "[launchable-jointpos-nullspace-probe] tracking_analysis=${TRACKING_ANALYSIS_JSON}"
echo "[launchable-jointpos-nullspace-probe] command=${COMMAND_PATH}"
