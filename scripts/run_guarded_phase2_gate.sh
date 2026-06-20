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
DIRECT_SSH_AFTER_CREATE_READY="${RCA_GATE_DIRECT_SSH_AFTER_CREATE_READY:-0}"
DIRECT_SSH_PROBE_ATTEMPTS="${RCA_GATE_DIRECT_SSH_PROBE_ATTEMPTS:-6}"
DIRECT_SSH_PROBE_INTERVAL_SECONDS="${RCA_GATE_DIRECT_SSH_PROBE_INTERVAL_SECONDS:-10}"
SSH_CONNECT_TIMEOUT="${RCA_GATE_SSH_CONNECT_TIMEOUT:-20}"
SSH_COMMAND_TIMEOUT="${RCA_GATE_SSH_COMMAND_TIMEOUT:-60}"
ALLOW_DIRTY="${RCA_ALLOW_DIRTY:-0}"
ALLOW_PAID_BREV_CREATE="${RCA_ALLOW_PAID_BREV_CREATE:-0}"
WATCHDOG_MAX_MINUTES="${RCA_GATE_WATCHDOG_MAX_MINUTES:-120}"
WATCHDOG_POLL_SECONDS="${RCA_GATE_WATCHDOG_POLL_SECONDS:-120}"
WATCHDOG_WAIT_MAX_MINUTES="${RCA_GATE_WATCHDOG_WAIT_MAX_MINUTES:-$(( (CREATE_TIMEOUT + 599) / 60 + 10 ))}"
WATCHDOG_START_GRACE_SECONDS="${RCA_GATE_WATCHDOG_START_GRACE_SECONDS:-2}"
WATCHDOG_DASHBOARD_URL="${RCA_GATE_WATCHDOG_DASHBOARD_URL:-https://brev.nvidia.com/org/org-3BaYGdtoRGmgc77Z7NHHhPSD254/environments}"

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
BC_LOCAL_DATASET="${RCA_BC_LOCAL_DATASET:-${REPO_ROOT}/artifacts/datasets/phase2_contact_bc/phase2_contact_bc_dataset.jsonl}"
BC_REMOTE_DATASET="${RCA_BC_REMOTE_DATASET:-/workspace/artifacts/datasets/phase2_contact_bc/phase2_contact_bc_dataset.jsonl}"
BC_CHECKPOINT="${RCA_BC_CHECKPOINT:-/workspace/artifacts/policies/phase2_contact_bc/bc_mlp.pt}"
BC_EPOCHS="${RCA_BC_EPOCHS:-250}"
BC_TRAIN_EXTRA_ARGS="${RCA_BC_TRAIN_EXTRA_ARGS:-}"
BC_EVAL_EXTRA_ARGS="${RCA_BC_EVAL_EXTRA_ARGS:-}"
BASELINE_CONTROLLER="${RCA_BASELINE_CONTROLLER:-current-joint}"
BASELINE_EVAL_EXTRA_ARGS="${RCA_BASELINE_EVAL_EXTRA_ARGS:-}"

RUN_ID="$(date -u +"%Y-%m-%dT%H-%M-%SZ")"
LOCAL_RUN_DIR="${REPO_ROOT}/artifacts/gpu_gate/${RUN_ID}_${INSTANCE_NAME}"
mkdir -p "${LOCAL_RUN_DIR}"
exec > >(tee -a "${LOCAL_RUN_DIR}/gate.log") 2>&1

REMOTE_USER=""
REMOTE_ROOT=""
REMOTE_COMPOSE_ROOT=""
CREATED_INSTANCE=0
FINAL_STATUS=0
WATCHDOG_PID=""

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

require_paid_brev_create_ack() {
  if [[ "${ALLOW_PAID_BREV_CREATE}" == "1" ]]; then
    return 0
  fi

  cat >&2 <<'EOF'
[guarded-gate] refusing to create a paid Brev instance.
[guarded-gate] Set RCA_ALLOW_PAID_BREV_CREATE=1 and RCA_BREV_CREDITS_VERIFIED=1 only after confirming credits/budget and a manual deletion path in the Brev UI.
EOF
  return 2
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

start_billing_watchdog() {
  local watchdog_dir launcher_log
  watchdog_dir="${LOCAL_RUN_DIR}/billing_watchdog"
  launcher_log="${watchdog_dir}/watchdog_launcher.log"
  mkdir -p "${watchdog_dir}"
  log "starting Brev billing watchdog max_minutes=${WATCHDOG_MAX_MINUTES} poll_seconds=${WATCHDOG_POLL_SECONDS}"
  nohup env \
    RCA_BREV_CLI="${BREV_BIN}" \
    RCA_BREV_WATCHDOG_INSTANCE_NAME="${INSTANCE_NAME}" \
    RCA_BREV_WATCHDOG_MAX_MINUTES="${WATCHDOG_MAX_MINUTES}" \
    RCA_BREV_WATCHDOG_POLL_SECONDS="${WATCHDOG_POLL_SECONDS}" \
    RCA_BREV_WATCHDOG_WAIT_FOR_APPEAR=1 \
    RCA_BREV_WATCHDOG_WAIT_MAX_MINUTES="${WATCHDOG_WAIT_MAX_MINUTES}" \
    RCA_BREV_WATCHDOG_DASHBOARD_URL="${WATCHDOG_DASHBOARD_URL}" \
    RCA_BREV_WATCHDOG_LEDGER_DIR="${watchdog_dir}" \
    "${SCRIPT_DIR}/brev_paid_run_watchdog.sh" >"${launcher_log}" 2>&1 &
  WATCHDOG_PID="$!"
  printf '%s\n' "${WATCHDOG_PID}" > "${watchdog_dir}/watchdog.pid"
  verify_watchdog_alive "${WATCHDOG_PID}" "${launcher_log}"
  disown "${WATCHDOG_PID}" 2>/dev/null || true
}

verify_watchdog_alive() {
  local pid="$1"
  local launcher_log="$2"

  sleep "${WATCHDOG_START_GRACE_SECONDS}"
  if ! kill -0 "${pid}" 2>/dev/null; then
    log "billing watchdog exited before instance creation; refusing paid create"
    cat "${launcher_log}" >&2 2>/dev/null || true
    exit 2
  fi
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

run_brev_refresh() {
  log "refreshing Brev SSH config"
  run_with_timeout "${BREV_MUTATION_TIMEOUT}" "${BREV_BIN}" refresh || true
}

run_ssh() {
  local command="$1"
  run_with_timeout \
    "${SSH_COMMAND_TIMEOUT}" \
    ssh \
    -o BatchMode=yes \
    -o ConnectTimeout="${SSH_CONNECT_TIMEOUT}" \
    -o StrictHostKeyChecking=accept-new \
    "${INSTANCE_NAME}" \
    "${command}"
}

probe_remote_host() {
  local remote_user_output

  log "probing remote host"
  run_ssh 'whoami && hostname && nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader && df -h /' || return 1
  remote_user_output="$(run_ssh 'whoami')" || return 1
  REMOTE_USER="$(strip_cr "${remote_user_output}" | awk 'NF { value = $0 } END { print value }')"
  if [[ -z "${REMOTE_USER}" ]]; then
    log "remote whoami probe returned an empty user"
    return 1
  fi
  REMOTE_ROOT="$(strip_cr "${RCA_REMOTE_ROOT:-/home/${REMOTE_USER}/projects/robot-contact-assembly}")"
  REMOTE_COMPOSE_ROOT="$(strip_cr "${RCA_REMOTE_COMPOSE_ROOT:-/home/${REMOTE_USER}/isaac-compose}")"
  log "remote_user=${REMOTE_USER}"
  log "remote_root=${REMOTE_ROOT}"
  log "remote_compose_root=${REMOTE_COMPOSE_ROOT}"
}

direct_ssh_probe_after_create_ready() {
  local attempt

  if [[ "${DIRECT_SSH_AFTER_CREATE_READY}" != "1" ]]; then
    return 1
  fi

  log "Brev list readiness did not become READY; trying direct SSH probe because RCA_GATE_DIRECT_SSH_AFTER_CREATE_READY=1"
  for (( attempt = 1; attempt <= DIRECT_SSH_PROBE_ATTEMPTS; attempt++ )); do
    log "direct SSH probe attempt ${attempt}/${DIRECT_SSH_PROBE_ATTEMPTS}"
    run_brev_refresh
    if probe_remote_host; then
      log "direct SSH probe succeeded"
      return 0
    fi
    if (( attempt < DIRECT_SSH_PROBE_ATTEMPTS )); then
      sleep "${DIRECT_SSH_PROBE_INTERVAL_SECONDS}"
    fi
  done

  log "direct SSH probe failed after ${DIRECT_SSH_PROBE_ATTEMPTS} attempts"
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

  if [[ "${CREATED_INSTANCE}" == "1" ]]; then
    delete_target_instance || true
    if wait_for_empty_org; then
      log "confirmed no visible instances after delete"
    else
      log "warning: instance list did not become empty before delete timeout"
      run_brev_ls_all || true
      run_brev_json_all || true
    fi
  else
    log "no Brev instance was created"
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
watchdog_enabled=1
watchdog_max_minutes=${WATCHDOG_MAX_MINUTES}
watchdog_poll_seconds=${WATCHDOG_POLL_SECONDS}
watchdog_pid=${WATCHDOG_PID}
direct_ssh_after_create_ready=${DIRECT_SSH_AFTER_CREATE_READY}
direct_ssh_probe_attempts=${DIRECT_SSH_PROBE_ATTEMPTS}
direct_ssh_probe_interval_seconds=${DIRECT_SSH_PROBE_INTERVAL_SECONDS}
ssh_connect_timeout=${SSH_CONNECT_TIMEOUT}
ssh_command_timeout=${SSH_COMMAND_TIMEOUT}
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

  log "preflight: paid compute guard"
  RCA_PAID_RUN_PURPOSE="${RCA_PAID_RUN_PURPOSE:-post_contact_gate}" \
  RCA_PAID_INSTANCE_NAME="${INSTANCE_NAME}" \
  RCA_PAID_MAX_MINUTES="${WATCHDOG_MAX_MINUTES}" \
  RCA_BREV_CREDITS_VERIFIED="${RCA_BREV_CREDITS_VERIFIED:-0}" \
  RCA_BREV_CLI="${BREV_BIN}" \
    "${SCRIPT_DIR}/paid_compute_preflight.sh"

  log "preflight: current Brev instances"
  run_brev_ls_all || true
  if ! refuse_if_instance_would_conflict; then
    echo "[guarded-gate] refusing to create a new instance because the org is not empty" >&2
    run_brev_json_all || true
    return 2
  fi
  require_paid_brev_create_ack

  log "preflight: recording live price tables"
  run_brev_search --min-total-vram 24 --min-disk "${MIN_DISK}" --stoppable --sort price | head -40 | tee "${LOCAL_RUN_DIR}/brev_search_24gb.txt"
  run_brev_search --min-total-vram 32 --min-disk "${MIN_DISK}" --stoppable --sort price | head -40 | tee "${LOCAL_RUN_DIR}/brev_search_32gb.txt"
  run_brev_search --min-total-vram 40 --min-disk "${MIN_DISK}" --stoppable --sort price | head -40 | tee "${LOCAL_RUN_DIR}/brev_search_40gb.txt"

  choose_instance_type

  log "creating ${INSTANCE_NAME} type=${INSTANCE_TYPE}"
  CREATED_INSTANCE=1
  start_billing_watchdog
  "${BREV_BIN}" create "${INSTANCE_NAME}" --type "${INSTANCE_TYPE}" --min-disk "${MIN_DISK}" --stoppable --timeout "${CREATE_TIMEOUT}"

  log "waiting for instance readiness"
  if wait_for_ready; then
    run_brev_refresh
    probe_remote_host
  elif ! direct_ssh_probe_after_create_ready; then
    return 1
  fi

  if [[ "${GATE_COMMAND}" == "probe_only" ]]; then
    log "probe-only gate completed"
    return 0
  fi

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
    contact_bc_train)
      log "running contact BC training"
      bash "${SCRIPT_DIR}/run_remote_train_contact_bc_policy.sh" \
        "${INSTANCE_NAME}" \
        "${REMOTE_ROOT}" \
        "${REMOTE_COMPOSE_ROOT}" \
        "${BC_LOCAL_DATASET}" \
        "${BC_REMOTE_DATASET}" \
        "${BC_CHECKPOINT}" \
        "${BC_EPOCHS}" \
        "${EVAL_TIMEOUT_SECONDS}" \
        "${BC_TRAIN_EXTRA_ARGS}"
      ;;
    contact_bc_eval)
      log "running contact BC evaluation"
      bash "${SCRIPT_DIR}/run_remote_eval_contact_bc_policy.sh" \
        "${INSTANCE_NAME}" \
        "${REMOTE_ROOT}" \
        "${REMOTE_COMPOSE_ROOT}" \
        "${TASK_NAME}" \
        "${NUM_ENVS}" \
        "${STEPS}" \
        "${SEEDS%%,*}" \
        "${BC_CHECKPOINT}" \
        "${EVAL_TIMEOUT_SECONDS}" \
        "${BC_EVAL_EXTRA_ARGS}"
      ;;
    contact_bc_smoke)
      log "running contact BC train+eval smoke"
      bash "${SCRIPT_DIR}/run_remote_train_contact_bc_policy.sh" \
        "${INSTANCE_NAME}" \
        "${REMOTE_ROOT}" \
        "${REMOTE_COMPOSE_ROOT}" \
        "${BC_LOCAL_DATASET}" \
        "${BC_REMOTE_DATASET}" \
        "${BC_CHECKPOINT}" \
        "${BC_EPOCHS}" \
        "${EVAL_TIMEOUT_SECONDS}" \
        "${BC_TRAIN_EXTRA_ARGS}"
      bash "${SCRIPT_DIR}/run_remote_eval_contact_bc_policy.sh" \
        "${INSTANCE_NAME}" \
        "${REMOTE_ROOT}" \
        "${REMOTE_COMPOSE_ROOT}" \
        "${TASK_NAME}" \
        "${NUM_ENVS}" \
        "${STEPS}" \
        "${SEEDS%%,*}" \
        "${BC_CHECKPOINT}" \
        "${EVAL_TIMEOUT_SECONDS}" \
        "${BC_EVAL_EXTRA_ARGS}"
      ;;
    contact_handoff_baseline)
      log "running contact handoff baseline controller=${BASELINE_CONTROLLER}"
      bash "${SCRIPT_DIR}/run_remote_eval_contact_handoff_baseline.sh" \
        "${INSTANCE_NAME}" \
        "${REMOTE_ROOT}" \
        "${REMOTE_COMPOSE_ROOT}" \
        "${TASK_NAME}" \
        "${NUM_ENVS}" \
        "${STEPS}" \
        "${SEEDS%%,*}" \
        "${BASELINE_CONTROLLER}" \
        "${EVAL_TIMEOUT_SECONDS}" \
        "${BASELINE_EVAL_EXTRA_ARGS}"
      ;;
    *)
      echo "[guarded-gate] unknown RCA_GATE_COMMAND=${GATE_COMMAND}; use probe_only, scripted_eval, scripted_socket_sweep, scripted_reach_sweep, action_calibration, calibration_then_scripted_eval, contact_bc_train, contact_bc_eval, contact_bc_smoke, or contact_handoff_baseline" >&2
      return 2
      ;;
  esac

  log "gate completed"
}

main "$@"
