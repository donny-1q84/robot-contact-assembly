#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="${RCA_LAUNCHABLE_REPO_DIR:-/workspace/robot-contact-assembly}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
"${SCRIPT_DIR}/launchable_post_contact_gate.sh" "${REPO_DIR}"
ARTIFACT_ROOT="${RCA_LAUNCHABLE_ARTIFACT_ROOT:-${REPO_DIR}/artifacts}"
ISAAC_PYTHON="${RCA_ISAAC_PYTHON:-/isaac-sim/python.sh}"
TASK_NAME="${RCA_LAUNCHABLE_TASK:-RCA-PegInHole-Franka-JointPos-Contact-Play-v0}"
SCRIPTED_STEPS="${RCA_LAUNCHABLE_SCRIPTED_STEPS:-1900}"
EVAL_STEPS="${RCA_LAUNCHABLE_STEPS:-400}"
SEED="${RCA_LAUNCHABLE_SEED:-42}"
TIMEOUT_SECONDS="${RCA_LAUNCHABLE_TIMEOUT_SECONDS:-1800}"
HANDOFF_MAX_STRICT_MISS="${RCA_LAUNCHABLE_HANDOFF_MAX_STRICT_MISS:-1.0}"
HANDOFF_REPLAY_MAX_LATERAL_DRIFT="${RCA_LAUNCHABLE_HANDOFF_REPLAY_MAX_LATERAL_DRIFT:-0.02}"
HANDOFF_REPLAY_MAX_AXIAL_DRIFT="${RCA_LAUNCHABLE_HANDOFF_REPLAY_MAX_AXIAL_DRIFT:-0.02}"
HANDOFF_REPLAY_MAX_ROT_DRIFT="${RCA_LAUNCHABLE_HANDOFF_REPLAY_MAX_ROT_DRIFT:-0.25}"
export RCA_FORCE_APP_LAUNCHER="${RCA_FORCE_APP_LAUNCHER:-1}"
export RCA_ARTIFACT_ROOT="${RCA_ARTIFACT_ROOT:-${ARTIFACT_ROOT}}"

RUN_ID="$(date -u +"%Y-%m-%dT%H-%M-%SZ")"
SCRIPTED_DIR="${ARTIFACT_ROOT}/evaluations/scripted/${RUN_ID}_fresh-preload"
EVAL_DIR="${ARTIFACT_ROOT}/evaluations/contact_handoff_baseline/${RUN_ID}_fresh-preload-direction"
SCRIPTED_SUMMARY_JSON="${SCRIPTED_DIR}/seed_${SEED}.json"
SCRIPTED_TRACE_JSON="${SCRIPTED_DIR}/seed_${SEED}_trace.json"
HANDOFF_JSON="${EVAL_DIR}/handoff_selection.json"
SUMMARY_JSON="${EVAL_DIR}/summary.json"
TRACE_JSON="${EVAL_DIR}/trace.json"
LOG_PATH="${EVAL_DIR}/eval.log"
COMMAND_PATH="${EVAL_DIR}/eval_command.txt"

if [[ ! -x "${ISAAC_PYTHON}" ]]; then
  echo "[launchable-fresh-preload] missing Isaac Python: ${ISAAC_PYTHON}" >&2
  exit 2
fi

if [[ ! -d "${REPO_DIR}/source/robot_contact_assembly_tasks" ]]; then
  echo "[launchable-fresh-preload] missing project repo at ${REPO_DIR}" >&2
  exit 2
fi

mkdir -p "${SCRIPTED_DIR}" "${EVAL_DIR}" "${ARTIFACT_ROOT}/hydra"

DEFAULT_SCRIPTED_ARGS=(
  --deterministic-reset
  --socket-pos 0.22,0.04,0.22
  --scripted-control-mode joint-ik
  --joint-ik-step 0.035
  --joint-limit-margin 0.005
  --abs-control-mode waypoint
  --abs-pos-step 0.010
  --abs-rot-step 0.10
  --orientation-target-mode axis-align-current
  --rotate-control-mode stateful-waypoint
  --rotate-xy-retention
  --rotate-xy-retention-tol 0.012
  --descend-xy-retention
  --descend-xy-retention-tol 0.012
  --hold-orientation-during-descend
  --insert-after-alignment
  --insert-descent-mode joint-cache
  --insert-vertical-step 0.020
  --joint-cache-step 0.020
  --joint-cache-step-scale 0.55
  --joint-cache-total-limit 0.60
  --joint-cache-live-polish
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
  --insert-abort-grace-steps 4
  --insert-abort-xy-tol 0.022
  --insert-abort-rot-tol 0.45
  --branch-jump-xy-tol 0.08
  --staged-approach
  --rotate-before-descend
  --success-xy-tol 0.005
  --success-z-tol 0.045
  --success-rot-tol 0.18
  --success-min-contact-force 0.5
  --debug-action-steps 4
)

if [[ -n "${RCA_LAUNCHABLE_SCRIPTED_AGENT_ARGS:-}" ]]; then
  # shellcheck disable=SC2206
  SCRIPTED_ARGS=(${RCA_LAUNCHABLE_SCRIPTED_AGENT_ARGS})
else
  SCRIPTED_ARGS=("${DEFAULT_SCRIPTED_ARGS[@]}")
fi

echo "[launchable-fresh-preload] repo=${REPO_DIR}"
echo "[launchable-fresh-preload] task=${TASK_NAME} scripted_steps=${SCRIPTED_STEPS} eval_steps=${EVAL_STEPS} seed=${SEED}"
echo "[launchable-fresh-preload] force_app_launcher=${RCA_FORCE_APP_LAUNCHER}"
echo "[launchable-fresh-preload] handoff_max_strict_miss=${HANDOFF_MAX_STRICT_MISS}"
echo "[launchable-fresh-preload] scripted_trace=${SCRIPTED_TRACE_JSON}"
echo "[launchable-fresh-preload] eval_dir=${EVAL_DIR}"

"${ISAAC_PYTHON}" -m pip install --editable "${REPO_DIR}/source/robot_contact_assembly_tasks"

cd "${REPO_DIR}"

cat > "${COMMAND_PATH}" <<EOF
${ISAAC_PYTHON} scripts/scripted_agent.py --task ${TASK_NAME} --headless --num_envs 1 --steps ${SCRIPTED_STEPS} --seed ${SEED} --summary-json ${SCRIPTED_SUMMARY_JSON} --trace-json ${SCRIPTED_TRACE_JSON} ${SCRIPTED_ARGS[*]}
${ISAAC_PYTHON} scripts/evaluate_contact_bc_policy.py --task ${TASK_NAME} --headless --num_envs 1 --steps ${EVAL_STEPS} --seed ${SEED} --controller preload-direction --preload-trace-json ${SCRIPTED_TRACE_JSON} --preload-trace-end-step <selected> --summary-json ${SUMMARY_JSON} --trace-json ${TRACE_JSON} --deterministic-reset --socket-pos 0.22,0.04,0.22 --success-xy-tol 0.005 --success-z-tol 0.045 --success-rot-tol 0.18 --success-min-contact-force 0.5 --near-contact-xy-tol 0.015 --near-contact-z-tol 0.060 --near-contact-rot-tol 0.35 --near-contact-min-force 0.2 --max-action-delta 0.02 --preload-direction-hold-gain 0.35 --preload-direction-scale 1.0
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
  2>&1 | tee "${EVAL_DIR}/scripted.log"
scripted_status=${PIPESTATUS[0]}
set -e

if [[ ${scripted_status} -ne 0 ]]; then
  echo "[launchable-fresh-preload] scripted preload failed status=${scripted_status}; inspect ${EVAL_DIR}/scripted.log" >&2
  exit "${scripted_status}"
fi

if [[ ! -s "${SCRIPTED_TRACE_JSON}" ]]; then
  echo "[launchable-fresh-preload] missing scripted trace: ${SCRIPTED_TRACE_JSON}" >&2
  exit 1
fi

"${ISAAC_PYTHON}" scripts/select_preload_handoff_step.py \
  --trace-json "${SCRIPTED_TRACE_JSON}" \
  --json > "${HANDOFF_JSON}"
HANDOFF_STEP="$("${ISAAC_PYTHON}" scripts/select_preload_handoff_step.py --trace-json "${SCRIPTED_TRACE_JSON}")"
echo "[launchable-fresh-preload] selected_handoff_step=${HANDOFF_STEP}"
cat "${HANDOFF_JSON}"
echo

"${ISAAC_PYTHON}" - "${HANDOFF_JSON}" "${HANDOFF_MAX_STRICT_MISS}" <<'PY'
import json
import sys

handoff = json.load(open(sys.argv[1], encoding="utf-8"))
max_miss = float(sys.argv[2])
miss = float(handoff["strict_miss_score"])
if miss > max_miss:
    raise SystemExit(
        f"[launchable-fresh-preload] selected handoff strict_miss_score={miss:.6f} "
        f"exceeds RCA_LAUNCHABLE_HANDOFF_MAX_STRICT_MISS={max_miss:.6f}; "
        "skipping post-handoff eval"
    )
PY

set +e
timeout "${TIMEOUT_SECONDS}" "${ISAAC_PYTHON}" scripts/evaluate_contact_bc_policy.py \
  --task "${TASK_NAME}" \
  --headless \
  --num_envs 1 \
  --steps "${EVAL_STEPS}" \
  --seed "${SEED}" \
  --controller preload-direction \
  --preload-trace-json "${SCRIPTED_TRACE_JSON}" \
  --preload-trace-end-step "${HANDOFF_STEP}" \
  --summary-json "${SUMMARY_JSON}" \
  --trace-json "${TRACE_JSON}" \
  --deterministic-reset \
  --socket-pos 0.22,0.04,0.22 \
  --success-xy-tol 0.005 \
  --success-z-tol 0.045 \
  --success-rot-tol 0.18 \
  --success-min-contact-force 0.5 \
  --near-contact-xy-tol 0.015 \
  --near-contact-z-tol 0.060 \
  --near-contact-rot-tol 0.35 \
  --near-contact-min-force 0.2 \
  --max-action-delta 0.02 \
  --preload-direction-hold-gain 0.35 \
  --preload-direction-scale 1.0 \
  2>&1 | tee "${LOG_PATH}"
eval_status=${PIPESTATUS[0]}
set -e

if [[ ${eval_status} -ne 0 ]]; then
  echo "[launchable-fresh-preload] eval failed status=${eval_status}; inspect ${LOG_PATH}" >&2
  exit "${eval_status}"
fi

if grep -q "\\[ERROR\\]:\\|Traceback (most recent call last)" "${LOG_PATH}"; then
  echo "[launchable-fresh-preload] eval log contains an error; inspect ${LOG_PATH}" >&2
  exit 1
fi

if [[ ! -s "${SUMMARY_JSON}" ]]; then
  echo "[launchable-fresh-preload] missing summary after eval; inspect ${LOG_PATH}" >&2
  exit 1
fi

"${ISAAC_PYTHON}" - \
  "${SUMMARY_JSON}" \
  "${HANDOFF_REPLAY_MAX_LATERAL_DRIFT}" \
  "${HANDOFF_REPLAY_MAX_AXIAL_DRIFT}" \
  "${HANDOFF_REPLAY_MAX_ROT_DRIFT}" <<'PY'
import json
import sys

summary = json.load(open(sys.argv[1], encoding="utf-8"))
limits = {
    "lateral": float(sys.argv[2]),
    "axial": float(sys.argv[3]),
    "rot": float(sys.argv[4]),
}
pairs = {
    "lateral": ("handoff_source_lateral", "handoff_lateral"),
    "axial": ("handoff_source_axial", "handoff_axial"),
    "rot": ("handoff_source_rot", "handoff_rot"),
}
errors = []
for name, (source_key, replay_key) in pairs.items():
    source = summary.get(source_key)
    replay = summary.get(replay_key)
    if source is None or replay is None:
        errors.append(f"{name}: missing source/replay metrics")
        continue
    drift = abs(float(source) - float(replay))
    if drift > limits[name]:
        errors.append(f"{name}: drift={drift:.6f} > limit={limits[name]:.6f} ({source_key}={source}, {replay_key}={replay})")
if errors:
    raise SystemExit("[launchable-fresh-preload] handoff replay drift check failed: " + "; ".join(errors))
print("[launchable-fresh-preload] handoff replay drift check passed")
PY

echo "[launchable-fresh-preload] scripted_summary=${SCRIPTED_SUMMARY_JSON}"
echo "[launchable-fresh-preload] scripted_trace=${SCRIPTED_TRACE_JSON}"
echo "[launchable-fresh-preload] handoff_selection=${HANDOFF_JSON}"
echo "[launchable-fresh-preload] summary=${SUMMARY_JSON}"
echo "[launchable-fresh-preload] trace=${TRACE_JSON}"
echo "[launchable-fresh-preload] command=${COMMAND_PATH}"
