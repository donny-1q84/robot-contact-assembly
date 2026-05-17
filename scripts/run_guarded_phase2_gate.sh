#!/usr/bin/env bash
set -euo pipefail

if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
  echo "Do not source this script; execute it as a command." >&2
  return 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

BREV_BIN="${BREV_BIN:-/Users/Shenghan/bin/brev}"
INSTANCE_NAME="${RCA_GATE_INSTANCE_NAME:-isaac-phase2-gate}"
INSTANCE_TYPE="${RCA_GATE_INSTANCE_TYPE:-}"
GATE_PROFILE="${RCA_GATE_PROFILE:-balanced}"
MIN_DISK="${RCA_GATE_MIN_DISK:-500}"
CREATE_TIMEOUT="${RCA_GATE_CREATE_TIMEOUT:-900}"
READY_TIMEOUT_SECONDS="${RCA_GATE_READY_TIMEOUT_SECONDS:-900}"
BUILD_STUCK_SECONDS="${RCA_GATE_BUILD_STUCK_SECONDS:-420}"
DELETE_TIMEOUT_SECONDS="${RCA_GATE_DELETE_TIMEOUT_SECONDS:-600}"
DELETE_RETRY_INTERVAL_SECONDS="${RCA_GATE_DELETE_RETRY_INTERVAL_SECONDS:-30}"
BREV_QUERY_TIMEOUT="${RCA_GATE_BREV_QUERY_TIMEOUT:-45}"
BREV_MUTATION_TIMEOUT="${RCA_GATE_BREV_MUTATION_TIMEOUT:-180}"
DELETE_ON_EXIT="${RCA_GATE_DELETE_ON_EXIT:-1}"
KEEP_ON_FAILURE="${RCA_GATE_KEEP_ON_FAILURE:-0}"
ALLOW_DIRTY="${RCA_ALLOW_DIRTY:-0}"

TASK_NAME="${RCA_GATE_TASK:-RCA-PegInHole-Franka-IK-Rel-Contact-Play-v0}"
NUM_ENVS="${RCA_GATE_NUM_ENVS:-1}"
STEPS="${RCA_GATE_STEPS:-240}"
SEEDS="${RCA_GATE_SEEDS:-42}"
EVAL_TIMEOUT_SECONDS="${RCA_GATE_EVAL_TIMEOUT_SECONDS:-600}"
EXTRA_AGENT_ARGS="${RCA_GATE_EXTRA_AGENT_ARGS:-}"
CALIBRATION_EXTRA_AGENT_ARGS="${RCA_GATE_CALIBRATION_EXTRA_AGENT_ARGS:-${EXTRA_AGENT_ARGS}}"
SCRIPTED_EXTRA_AGENT_ARGS="${RCA_GATE_SCRIPTED_EXTRA_AGENT_ARGS:-${EXTRA_AGENT_ARGS}}"
USE_CALIBRATED_SCRIPTED="${RCA_GATE_USE_CALIBRATED_SCRIPTED:-0}"
GATE_COMMAND="${RCA_GATE_COMMAND:-scripted_eval}"
CALIBRATION_STEPS="${RCA_GATE_CALIBRATION_STEPS:-${STEPS}}"
SCRIPTED_STEPS="${RCA_GATE_SCRIPTED_STEPS:-${STEPS}}"

RUN_ID="$(date -u +"%Y-%m-%dT%H-%M-%SZ")"
LOCAL_RUN_DIR="${REPO_ROOT}/artifacts/gpu_gate/${RUN_ID}_${INSTANCE_NAME}"
mkdir -p "${LOCAL_RUN_DIR}"
exec > >(tee -a "${LOCAL_RUN_DIR}/gate.log") 2>&1

REMOTE_USER=""
REMOTE_ROOT=""
REMOTE_COMPOSE_ROOT=""
CREATED_INSTANCE=0
FINAL_STATUS=0

log() {
  echo "[guarded-gate] $*"
}

strip_cr() {
  printf '%s' "$1" | tr -d '\r'
}

run_with_timeout() {
  local timeout_seconds="$1"
  shift

  local output_file status_file pid deadline status
  output_file="${LOCAL_RUN_DIR}/.timeout_$$_${RANDOM}.out"
  status_file="${LOCAL_RUN_DIR}/.timeout_$$_${RANDOM}.status"

  (
    set +e
    "$@" >"${output_file}" 2>&1
    printf '%s' "$?" >"${status_file}"
  ) &
  pid=$!
  deadline=$((SECONDS + timeout_seconds))

  while kill -0 "${pid}" 2>/dev/null; do
    if (( SECONDS >= deadline )); then
      kill "${pid}" 2>/dev/null || true
      sleep 1
      kill -9 "${pid}" 2>/dev/null || true
      wait "${pid}" 2>/dev/null || true
      cat "${output_file}" 2>/dev/null || true
      rm -f "${output_file}" "${status_file}"
      return 124
    fi
    sleep 1
  done

  wait "${pid}" 2>/dev/null || true
  cat "${output_file}" 2>/dev/null || true
  if [[ -f "${status_file}" ]]; then
    status="$(cat "${status_file}")"
  else
    status=1
  fi
  rm -f "${output_file}" "${status_file}"
  return "${status}"
}

run_brev_ls_all() {
  run_with_timeout "${BREV_QUERY_TIMEOUT}" "${BREV_BIN}" ls instances --all
}

run_brev_json_all() {
  run_with_timeout "${BREV_QUERY_TIMEOUT}" "${BREV_BIN}" ls instances --json --all
}

run_brev_search() {
  run_with_timeout "${BREV_QUERY_TIMEOUT}" "${BREV_BIN}" search "$@"
}

org_is_empty() {
  local json json_status json_parse_status json_state all all_status all_state
  set +e
  json="$(run_brev_json_all 2>/dev/null)"
  json_status=$?
  all="$(run_brev_ls_all 2>/dev/null)"
  all_status=$?
  set -e

  json_state="invalid"
  set +e
  BREV_INSTANCES_JSON="${json}" python3 - <<'PY'
import json
import os
import sys

raw = os.environ.get("BREV_INSTANCES_JSON", "").strip()
try:
    data = json.loads(raw) if raw else None
except json.JSONDecodeError:
    sys.exit(20)

if data in (None, []):
    sys.exit(0)
if isinstance(data, dict) and not data.get("workspaces"):
    sys.exit(0)
sys.exit(10)
PY
  json_parse_status=$?
  set -e
  case "${json_parse_status}" in
    0) json_state="empty" ;;
    10) json_state="nonempty" ;;
    *) json_state="invalid" ;;
  esac

  all_state="invalid"
  if [[ "${all_status}" -eq 0 ]]; then
    if [[ "${all}" == *"No instances in org"* ]]; then
      all_state="empty"
    else
      all_state="nonempty"
    fi
  fi

  if [[ "${json_state}" == "nonempty" || "${all_state}" == "nonempty" ]]; then
    log "Brev instance query is not empty; treating org as not empty"
    return 1
  fi

  if [[ "${json_state}" == "empty" || "${all_state}" == "empty" ]]; then
    return 0
  fi

  if [[ "${json_status}" -ne 0 ]]; then
    log "Brev JSON instance query failed and plain query did not prove emptiness; treating org as not empty"
  else
    log "Brev instance query did not prove emptiness; treating org as not empty"
  fi
  if [[ "${all_status}" -ne 0 ]]; then
    log "Brev plain instance query also failed"
  fi
  return 1
}

org_has_target_instance() {
  local output
  output="$(run_brev_ls_all || true)"
  printf '%s\n' "${output}" | awk -v name="${INSTANCE_NAME}" '$1 == name { found = 1 } END { exit found ? 0 : 1 }'
}

refuse_if_instance_would_conflict() {
  if org_is_empty; then
    return 0
  fi
  if org_has_target_instance; then
    log "target instance ${INSTANCE_NAME} already exists; refusing to create another"
    return 1
  fi
  log "org has a non-target instance; refusing to create a new instance"
  return 1
}

target_instance_ids() {
  local json
  set +e
  json="$(run_brev_json_all 2>/dev/null)"
  set -e
  TARGET_INSTANCE_NAME="${INSTANCE_NAME}" TARGET_INSTANCES_JSON="${json}" python3 - <<'PY'
import json
import os

name = os.environ["TARGET_INSTANCE_NAME"]
raw = os.environ.get("TARGET_INSTANCES_JSON", "").strip()
try:
    data = json.loads(raw) if raw else None
except json.JSONDecodeError:
    data = None

if isinstance(data, dict):
    instances = data.get("workspaces") or []
else:
    instances = data

if not instances:
    raise SystemExit(0)

for instance in instances:
    if instance.get("name") == name and instance.get("id"):
        print(instance["id"])
PY
}

delete_target_instance() {
  local ids id
  log "deleting instance ${INSTANCE_NAME}"
  run_with_timeout "${BREV_MUTATION_TIMEOUT}" "${BREV_BIN}" delete "${INSTANCE_NAME}" || true
  ids="$(target_instance_ids || true)"
  while IFS= read -r id; do
    [[ -z "${id}" ]] && continue
    log "deleting instance id=${id}"
    run_with_timeout "${BREV_MUTATION_TIMEOUT}" "${BREV_BIN}" delete "${id}" || true
  done <<< "${ids}"
}

wait_for_ready() {
  local deadline output building_since
  deadline=$((SECONDS + READY_TIMEOUT_SECONDS))
  building_since=0
  while (( SECONDS < deadline )); do
    output="$(run_brev_ls_all || true)"
    printf '%s\n' "${output}"
    if printf '%s\n' "${output}" | awk -v name="${INSTANCE_NAME}" '$1 == name && $2 == "RUNNING" && $3 == "COMPLETED" && $4 == "READY" { found = 1 } END { exit found ? 0 : 1 }'; then
      return 0
    fi
    if printf '%s\n' "${output}" | awk -v name="${INSTANCE_NAME}" '$1 == name && $2 == "RUNNING" && $3 == "BUILDING" { found = 1 } END { exit found ? 0 : 1 }'; then
      if (( building_since == 0 )); then
        building_since="${SECONDS}"
      elif (( SECONDS - building_since >= BUILD_STUCK_SECONDS )); then
        log "instance ${INSTANCE_NAME} stuck in RUNNING/BUILDING for $((SECONDS - building_since))s; aborting before ready timeout"
        return 1
      fi
    else
      building_since=0
    fi
    sleep 10
  done
  log "instance ${INSTANCE_NAME} did not become READY within ${READY_TIMEOUT_SECONDS}s"
  return 1
}

wait_for_empty_org() {
  local deadline last_delete_retry output
  deadline=$((SECONDS + DELETE_TIMEOUT_SECONDS))
  last_delete_retry=0
  while (( SECONDS < deadline )); do
    if org_is_empty; then
      run_brev_ls_all || true
      return 0
    fi
    output="$(run_brev_ls_all || true)"
    printf '%s\n' "${output}"
    if printf '%s\n' "${output}" | awk -v name="${INSTANCE_NAME}" '$1 == name { found = 1 } END { exit found ? 0 : 1 }'; then
      if (( SECONDS - last_delete_retry >= DELETE_RETRY_INTERVAL_SECONDS )); then
        log "target instance ${INSTANCE_NAME} still visible during cleanup; re-issuing delete"
        delete_target_instance || true
        last_delete_retry="${SECONDS}"
      fi
    fi
    sleep 10
  done
  if org_is_empty; then
    run_brev_ls_all || true
    return 0
  fi
  return 1
}

cleanup() {
  local status=$?
  FINAL_STATUS="${status}"
  set +e

  log "cleanup status=${status}"
  if [[ -n "${REMOTE_ROOT}" ]]; then
    log "pulling artifacts before shutdown"
    bash "${SCRIPT_DIR}/pull_artifacts.sh" "${INSTANCE_NAME}" "${REMOTE_ROOT}" "${REPO_ROOT}/artifacts" || true
  fi

  if [[ "${CREATED_INSTANCE}" == "1" && "${DELETE_ON_EXIT}" == "1" && ( "${KEEP_ON_FAILURE}" != "1" || "${status}" == "0" ) ]]; then
    delete_target_instance || true
    if wait_for_empty_org; then
      log "confirmed no visible instances after delete"
    else
      log "warning: instance list did not become empty before delete timeout"
      run_brev_ls_all || true
      run_brev_json_all || true
    fi
  else
    log "skipping delete: CREATED_INSTANCE=${CREATED_INSTANCE} DELETE_ON_EXIT=${DELETE_ON_EXIT} KEEP_ON_FAILURE=${KEEP_ON_FAILURE} status=${status}"
    run_brev_ls_all || true
  fi

  cat > "${LOCAL_RUN_DIR}/gate_metadata.env" <<EOF
run_id=${RUN_ID}
instance_name=${INSTANCE_NAME}
instance_type=${INSTANCE_TYPE}
gate_profile=${GATE_PROFILE}
gate_command=${GATE_COMMAND}
use_calibrated_scripted=${USE_CALIBRATED_SCRIPTED}
task_name=${TASK_NAME}
num_envs=${NUM_ENVS}
steps=${STEPS}
build_stuck_seconds=${BUILD_STUCK_SECONDS}
calibration_steps=${CALIBRATION_STEPS}
scripted_steps=${SCRIPTED_STEPS}
seeds=${SEEDS}
eval_timeout_seconds=${EVAL_TIMEOUT_SECONDS}
remote_user=${REMOTE_USER}
remote_root=${REMOTE_ROOT}
remote_compose_root=${REMOTE_COMPOSE_ROOT}
final_status=${FINAL_STATUS}
EOF
  log "local run dir: ${LOCAL_RUN_DIR}"
  exit "${status}"
}

trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

choose_instance_type() {
  if [[ -n "${INSTANCE_TYPE}" ]]; then
    log "using explicit RCA_GATE_INSTANCE_TYPE=${INSTANCE_TYPE}"
    return 0
  fi

  local search_output selected
  case "${GATE_PROFILE}" in
    balanced)
      log "selecting cheapest visible single L40S candidate"
      search_output="$(run_brev_search --gpu-name L40S --min-total-vram 40 --min-disk "${MIN_DISK}" --stoppable --sort price)"
      printf '%s\n' "${search_output}" | tee "${LOCAL_RUN_DIR}/brev_search_l40s.txt"
      selected="$(printf '%s\n' "${search_output}" | awk '$4 == "L40S" && $5 == 1 { print $1; exit }')"
      ;;
    cheap)
      log "selecting cheapest visible single L4 candidate"
      search_output="$(run_brev_search --gpu-name L4 --min-total-vram 24 --min-disk "${MIN_DISK}" --stoppable --sort price)"
      printf '%s\n' "${search_output}" | tee "${LOCAL_RUN_DIR}/brev_search_l4.txt"
      selected="$(printf '%s\n' "${search_output}" | awk '$4 == "L4" && $5 == 1 { print $1; exit }')"
      ;;
    *)
      echo "[guarded-gate] unknown RCA_GATE_PROFILE=${GATE_PROFILE}; use balanced or cheap" >&2
      return 2
      ;;
  esac

  if [[ -z "${selected}" ]]; then
    echo "[guarded-gate] could not select an instance type for profile=${GATE_PROFILE}" >&2
    return 2
  fi
  INSTANCE_TYPE="${selected}"
  log "selected instance_type=${INSTANCE_TYPE}"
}

main() {
  log "repo=${REPO_ROOT}"
  log "run_id=${RUN_ID}"
  log "preflight: checking git state"
  git -C "${REPO_ROOT}" status --short --branch
  if [[ "${ALLOW_DIRTY}" != "1" && -n "$(git -C "${REPO_ROOT}" status --porcelain)" ]]; then
    echo "[guarded-gate] repo has uncommitted changes; commit first or set RCA_ALLOW_DIRTY=1" >&2
    return 2
  fi

  log "preflight: current Brev instances"
  run_brev_ls_all || true
  if ! refuse_if_instance_would_conflict; then
    echo "[guarded-gate] refusing to create a new instance because the org is not empty" >&2
    run_brev_json_all || true
    return 2
  fi

  log "preflight: recording live price tables"
  run_brev_search --min-total-vram 24 --min-disk "${MIN_DISK}" --stoppable --sort price | head -40 | tee "${LOCAL_RUN_DIR}/brev_search_24gb.txt"
  run_brev_search --min-total-vram 32 --min-disk "${MIN_DISK}" --stoppable --sort price | head -40 | tee "${LOCAL_RUN_DIR}/brev_search_32gb.txt"
  run_brev_search --min-total-vram 40 --min-disk "${MIN_DISK}" --stoppable --sort price | head -40 | tee "${LOCAL_RUN_DIR}/brev_search_40gb.txt"

  choose_instance_type

  log "creating ${INSTANCE_NAME} type=${INSTANCE_TYPE}"
  CREATED_INSTANCE=1
  "${BREV_BIN}" create "${INSTANCE_NAME}" --type "${INSTANCE_TYPE}" --min-disk "${MIN_DISK}" --stoppable --timeout "${CREATE_TIMEOUT}"

  log "waiting for instance readiness"
  wait_for_ready

  log "refreshing Brev SSH config"
  run_with_timeout "${BREV_MUTATION_TIMEOUT}" "${BREV_BIN}" refresh || true

  log "probing remote host"
  ssh "${INSTANCE_NAME}" 'whoami && hostname && nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader && df -h /'
  REMOTE_USER="$(ssh "${INSTANCE_NAME}" 'whoami' | tr -d '\r')"
  REMOTE_ROOT="$(strip_cr "${RCA_REMOTE_ROOT:-/home/${REMOTE_USER}/projects/robot-contact-assembly}")"
  REMOTE_COMPOSE_ROOT="$(strip_cr "${RCA_REMOTE_COMPOSE_ROOT:-/home/${REMOTE_USER}/isaac-compose}")"
  log "remote_user=${REMOTE_USER}"
  log "remote_root=${REMOTE_ROOT}"
  log "remote_compose_root=${REMOTE_COMPOSE_ROOT}"

  log "bootstrapping workspace"
  bash "${SCRIPT_DIR}/bootstrap_brev_workspace.sh" "${INSTANCE_NAME}" "${REMOTE_ROOT}"

  log "syncing repository"
  bash "${SCRIPT_DIR}/sync_to_brev.sh" "${INSTANCE_NAME}" "${REMOTE_ROOT}"

  log "installing headless Isaac Lab runtime"
  RCA_SKIP_STREAM_STACK=1 bash "${SCRIPT_DIR}/install_remote_isaaclab_runtime.sh" "${INSTANCE_NAME}" "${REMOTE_ROOT}" "${REMOTE_COMPOSE_ROOT}"

  log "checking runtime"
  bash "${SCRIPT_DIR}/check_remote_runtime.sh" "${INSTANCE_NAME}" "${REMOTE_ROOT}" "${REMOTE_COMPOSE_ROOT}"

  case "${GATE_COMMAND}" in
    scripted_eval)
      log "running scripted contact gate"
      bash "${SCRIPT_DIR}/run_remote_scripted_eval.sh" \
        "${INSTANCE_NAME}" \
        "${REMOTE_ROOT}" \
        "${REMOTE_COMPOSE_ROOT}" \
        "${TASK_NAME}" \
        "${NUM_ENVS}" \
        "${STEPS}" \
        "${SEEDS}" \
        "${EVAL_TIMEOUT_SECONDS}" \
        "${EXTRA_AGENT_ARGS}"
      ;;
    action_calibration)
      log "running relative IK action calibration gate"
      bash "${SCRIPT_DIR}/run_remote_action_calibration.sh" \
        "${INSTANCE_NAME}" \
        "${REMOTE_ROOT}" \
        "${REMOTE_COMPOSE_ROOT}" \
        "${TASK_NAME}" \
        "${CALIBRATION_STEPS}" \
        "${SEEDS%%,*}" \
        "${EVAL_TIMEOUT_SECONDS}" \
        "${CALIBRATION_EXTRA_AGENT_ARGS}"
      ;;
    calibration_then_scripted_eval)
      log "running relative IK action calibration gate"
      bash "${SCRIPT_DIR}/run_remote_action_calibration.sh" \
        "${INSTANCE_NAME}" \
        "${REMOTE_ROOT}" \
        "${REMOTE_COMPOSE_ROOT}" \
        "${TASK_NAME}" \
        "${CALIBRATION_STEPS}" \
        "${SEEDS%%,*}" \
        "${EVAL_TIMEOUT_SECONDS}" \
        "${CALIBRATION_EXTRA_AGENT_ARGS}"
      log "running scripted contact gate after calibration"
      combined_scripted_args="${SCRIPTED_EXTRA_AGENT_ARGS}"
      if [[ "${USE_CALIBRATED_SCRIPTED}" == "1" ]]; then
        latest_calibration_json="/workspace/artifacts/calibration/relative_ik_action/latest_seed_${SEEDS%%,*}.json"
        combined_scripted_args="${combined_scripted_args} --position-control-mode calibrated-onehot --position-response-json ${latest_calibration_json}"
      fi
      bash "${SCRIPT_DIR}/run_remote_scripted_eval.sh" \
        "${INSTANCE_NAME}" \
        "${REMOTE_ROOT}" \
        "${REMOTE_COMPOSE_ROOT}" \
        "${TASK_NAME}" \
        "${NUM_ENVS}" \
        "${SCRIPTED_STEPS}" \
        "${SEEDS}" \
        "${EVAL_TIMEOUT_SECONDS}" \
        "${combined_scripted_args}"
      ;;
    scripted_reach_sweep)
      log "running scripted reachability sweep"
      bash "${SCRIPT_DIR}/run_remote_scripted_reach_sweep.sh" \
        "${INSTANCE_NAME}" \
        "${REMOTE_ROOT}" \
        "${REMOTE_COMPOSE_ROOT}" \
        "${TASK_NAME}" \
        "${NUM_ENVS}" \
        "${SEEDS%%,*}" \
        "${EVAL_TIMEOUT_SECONDS}"
      ;;
    scripted_socket_sweep)
      log "running scripted socket-pose sweep"
      bash "${SCRIPT_DIR}/run_remote_scripted_socket_sweep.sh" \
        "${INSTANCE_NAME}" \
        "${REMOTE_ROOT}" \
        "${REMOTE_COMPOSE_ROOT}" \
        "${TASK_NAME}" \
        "${NUM_ENVS}" \
        "${STEPS}" \
        "${SEEDS}" \
        "${EVAL_TIMEOUT_SECONDS}" \
        "${RCA_SOCKET_SWEEP_POSITIONS:-}" \
        "${EXTRA_AGENT_ARGS}"
      ;;
    *)
      echo "[guarded-gate] unknown RCA_GATE_COMMAND=${GATE_COMMAND}; use scripted_eval, scripted_socket_sweep, scripted_reach_sweep, action_calibration, or calibration_then_scripted_eval" >&2
      return 2
      ;;
  esac

  log "gate completed"
}

main "$@"
