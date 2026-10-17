#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Do not let a direct wrapper call evade the highest-entry r34 safety hold.
# Check before installing traps: a refused start must not delete an existing run.
RCA_PAID_INSTANCE_NAME="${1:-rca-final-contact-servo-vm}" python3 "${SCRIPT_DIR}/check_paid_supervision.py"

ENV_NAME="${1:-rca-final-contact-servo-vm}"
REMOTE_ROOT="${2:-/home/ubuntu/projects/robot-contact-assembly}"
COMPOSE_ROOT="${3:-/home/ubuntu/isaac-compose}"
TASK_NAME="${4:-RCA-PegInHole-Franka-JointPos-Contact-Play-v0}"
STEPS="${5:-1200}"
SEED="${6:-42}"

source "${SCRIPT_DIR}/brev_cli_path.sh"
INSTANCE_TYPE="${RCA_FINAL_CONTACT_INSTANCE_TYPE:-g6e.xlarge}"
MIN_DISK="${RCA_FINAL_CONTACT_MIN_DISK:-500}"
CREATE_TIMEOUT="${RCA_FINAL_CONTACT_CREATE_TIMEOUT:-900}"
WATCHDOG_MAX_MINUTES="${RCA_FINAL_CONTACT_WATCHDOG_MAX_MINUTES:-45}"
WATCHDOG_POLL_SECONDS="${RCA_FINAL_CONTACT_WATCHDOG_POLL_SECONDS:-60}"
WATCHDOG_WAIT_MAX_MINUTES="${RCA_FINAL_CONTACT_WATCHDOG_WAIT_MAX_MINUTES:-$(( (CREATE_TIMEOUT + 599) / 60 + 10 ))}"
WATCHDOG_START_GRACE_SECONDS="${RCA_FINAL_CONTACT_WATCHDOG_START_GRACE_SECONDS:-2}"
WATCHDOG_DASHBOARD_URL="${RCA_FINAL_CONTACT_DASHBOARD_URL:-https://brev.nvidia.com/org/org-3BaYGdtoRGmgc77Z7NHHhPSD254/environments}"
DELETE_ATTEMPTS="${RCA_FINAL_CONTACT_DELETE_ATTEMPTS:-45}"
DELETE_RETRY_INTERVAL_SECONDS="${RCA_FINAL_CONTACT_DELETE_RETRY_INTERVAL_SECONDS:-10}"
BREV_QUERY_TIMEOUT_SECONDS="${RCA_FINAL_CONTACT_BREV_QUERY_TIMEOUT_SECONDS:-45}"
BREV_MUTATION_TIMEOUT_SECONDS="${RCA_FINAL_CONTACT_BREV_MUTATION_TIMEOUT_SECONDS:-180}"
PULLBACK_TIMEOUT_SECONDS="${RCA_FINAL_CONTACT_PULLBACK_TIMEOUT_SECONDS:-180}"
TRACE_TIMEOUT_SECONDS="${RCA_FINAL_CONTACT_TRACE_TIMEOUT_SECONDS:-900}"
TRACE_TIMEOUT_KILL_SECONDS="${RCA_FINAL_CONTACT_TRACE_TIMEOUT_KILL_SECONDS:-45}"
TRACE_RUNNER="${RCA_FINAL_CONTACT_TRACE_RUNNER:-${SCRIPT_DIR}/run_remote_final_contact_servo_trace.sh}"
OPERATION_PURPOSE="${RCA_PAID_RUN_PURPOSE:-post_contact_gate}"
if [[ "${OPERATION_PURPOSE}" == "contact_physics_smoke" ]]; then
  if [[ "${TRACE_RUNNER}" != "${SCRIPT_DIR}/run_remote_contact_revalidation.sh" || ! -s "${RCA_CONTACT_SMOKE_BUNDLE_PATH:-}" ]]; then
    echo "[final-contact-servo] BLOCKED: contact purpose requires its dedicated runner, frozen source, and prepared bundle" >&2
    exit 2
  fi
fi
VALIDATE_PEG_VIDEO_CANDIDATE="${RCA_FINAL_CONTACT_VALIDATE_PEG_VIDEO_CANDIDATE:-${RCA_VALIDATE_PEG_VIDEO_CANDIDATE:-1}}"
RUN_ID="$(date -u +"%Y-%m-%dT%H-%M-%SZ")"
WATCHDOG_DIR="${RCA_FINAL_CONTACT_WATCHDOG_LEDGER_DIR:-${REPO_ROOT}/artifacts/brev_paid_runs/${RUN_ID}_${ENV_NAME}}"
CREATED_INSTANCE=0
REMOTE_INITIALIZED=0
WATCHDOG_PID=""
PREPARATION_DEADLINE=0
PREPARATION_SECONDS=900
if [[ "${OPERATION_PURPOSE}" == "contact_physics_smoke" && "${RCA_CONTACT_SMOKE_SUITE:-wall}" == "seated" ]]; then
  SEATED_BUDGET="$(python3 "${SCRIPT_DIR}/seated_time_budget.py" --shell)"
  eval "${SEATED_BUDGET}"
  PREPARATION_SECONDS="${RCA_SEATED_PREPARATION_SECONDS}"
  if [[ "${TRACE_TIMEOUT_SECONDS}" != "${RCA_SEATED_WORKLOAD_SECONDS}" || "${TRACE_TIMEOUT_KILL_SECONDS}" != "60" || "${WATCHDOG_MAX_MINUTES}" != "45" ]]; then
    echo "[final-contact-servo] BLOCKED: seated timing must match the reviewed 45min allocation" >&2
    exit 2
  fi
fi

selected_instance_spec() {
  python3 - "${INSTANCE_TYPE}" "${MIN_DISK}" <<'PY'
import json
import sys

instance_type, disk_text = sys.argv[1:]
disk_gb = int(disk_text)
if not instance_type.strip() or "," in instance_type or disk_gb <= 0:
    raise SystemExit("exactly one instance type and a positive disk size are required")
# CLI v0.6.335 only propagates disk size from input specs, not --type + --min-disk.
print(json.dumps([{"type": instance_type, "target_disk_gb": disk_gb}]))
PY
}

run_with_timeout() {
  local timeout_seconds="$1"
  shift

  local output_file
  mkdir -p "${WATCHDOG_DIR}"
  output_file="${WATCHDOG_DIR}/.timeout_$$_${RANDOM}.out"
  # Bound the whole helper process group, not just a waiting shell parent.
  python3 - "${timeout_seconds}" "${output_file}" "$@" <<'PY'
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

limit, output = float(sys.argv[1]), Path(sys.argv[2])
if not math.isfinite(limit) or limit <= 0:
    raise SystemExit(2)
process, status = None, 1
phase = os.environ.get("RCA_PREPARATION_PHASE")
if phase:
    import json
    from dataclasses import asdict
    sys.dont_write_bytecode = True
    sys.path.insert(0, os.environ["RCA_PREPARATION_SCRIPT_DIR"])
    from paid_run_os_clock import sample_os_clock

    def record_phase(event, exit_code=None):
        # Observations only: no deadline reset, target authority or admission.
        record = {"schema": "preparation-observation-v1", "phase": phase,
                  "event": event, "clock": asdict(sample_os_clock()),
                  "lifecycle_pid": os.getppid(), "timeout_seconds": limit,
                  "exit_code": exit_code, "diagnostic_only": True}
        fd = os.open(output.parent / "preparation_phases.jsonl",
                     os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "w") as stream:
            stream.write(json.dumps(record, sort_keys=True, allow_nan=False) + "\n")
            stream.flush()
            os.fsync(stream.fileno())

    record_phase("start")
def interrupted(signum, frame):
    raise SystemExit(128 + signum)
signal.signal(signal.SIGTERM, interrupted)
try:
    with output.open("xb") as log:
        process = subprocess.Popen(sys.argv[3:], stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        status = process.wait(timeout=limit)
except subprocess.TimeoutExpired:
    status = 124
except KeyboardInterrupt:
    status = 130
except SystemExit as exc:
    status = exc.code or 1
finally:
    if process is not None:
        try:
            os.killpg(process.pid, signal.SIGTERM)
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                process.poll()
                try:
                    os.killpg(process.pid, 0)
                except PermissionError:
                    # Transitional macOS EPERM is not cleanup confirmation.
                    pass
                time.sleep(.05)
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=5)
    if phase:
        record_phase("end", status if status >= 0 else 128-status)
    if output.exists():
        sys.stdout.buffer.write(output.read_bytes())
        output.unlink()
raise SystemExit(status if status >= 0 else 128-status)
PY
}

run_preparation() {
  local phase="$1"
  shift
  case "${phase}" in
    create|ready|bootstrap|sync|install|xvfb) ;;
    *) echo "[final-contact-servo] invalid preparation phase" >&2; return 2 ;;
  esac
  if [[ "${OPERATION_PURPOSE}" == "contact_physics_smoke" && "${RCA_CONTACT_SMOKE_SUITE:-wall}" == "seated" ]]; then
    local remaining=$((PREPARATION_DEADLINE - SECONDS))
    if (( remaining <= 0 )); then
      echo "[final-contact-servo] seated preparation exhausted its shared ${PREPARATION_SECONDS}s allocation" >&2
      return 124
    fi
    RCA_PREPARATION_PHASE="${phase}" RCA_PREPARATION_SCRIPT_DIR="${SCRIPT_DIR}" \
      run_with_timeout "${remaining}" "$@"
  else
    "$@"
  fi
}

verify_watchdog_alive() {
  local pid="$1"
  local launcher_log="$2"

  sleep "${WATCHDOG_START_GRACE_SECONDS}"
  if ! kill -0 "${pid}" 2>/dev/null; then
    echo "[final-contact-servo] billing watchdog exited before instance creation; refusing paid create" >&2
    cat "${launcher_log}" >&2 2>/dev/null || true
    exit 2
  fi
}

start_billing_watchdog() {
  mkdir -p "${WATCHDOG_DIR}"
  echo "[final-contact-servo] starting billing watchdog max_minutes=${WATCHDOG_MAX_MINUTES} ledger=${WATCHDOG_DIR}"
  nohup env \
    RCA_BREV_CLI="${BREV_BIN}" \
    RCA_BREV_WATCHDOG_INSTANCE_NAME="${ENV_NAME}" \
    RCA_BREV_WATCHDOG_MAX_MINUTES="${WATCHDOG_MAX_MINUTES}" \
    RCA_BREV_WATCHDOG_POLL_SECONDS="${WATCHDOG_POLL_SECONDS}" \
    RCA_BREV_WATCHDOG_WAIT_FOR_APPEAR=1 \
    RCA_BREV_WATCHDOG_WAIT_MAX_MINUTES="${WATCHDOG_WAIT_MAX_MINUTES}" \
    RCA_BREV_WATCHDOG_DASHBOARD_URL="${WATCHDOG_DASHBOARD_URL}" \
    RCA_BREV_WATCHDOG_LEDGER_DIR="${WATCHDOG_DIR}" \
    RCA_PAID_BUDGET_EUR="${RCA_PAID_BUDGET_EUR:-}" \
    RCA_PAID_ESTIMATED_EUR_PER_HOUR="${RCA_PAID_ESTIMATED_EUR_PER_HOUR:-}" \
    "${SCRIPT_DIR}/brev_paid_run_watchdog.sh" >"${WATCHDOG_DIR}/watchdog_launcher.log" 2>&1 &
  WATCHDOG_PID="$!"
  printf '%s\n' "${WATCHDOG_PID}" > "${WATCHDOG_DIR}/watchdog.pid"
  verify_watchdog_alive "${WATCHDOG_PID}" "${WATCHDOG_DIR}/watchdog_launcher.log"
  disown "${WATCHDOG_PID}" 2>/dev/null || true
}

matching_instance_tokens() {
  local raw
  raw="$(run_with_timeout "${BREV_QUERY_TIMEOUT_SECONDS}" "${BREV_BIN}" ls instances --json --all 2>/dev/null)" || return 1
  RCA_FINAL_CONTACT_TARGET="${ENV_NAME}" RCA_FINAL_CONTACT_INSTANCES_JSON="${raw}" python3 - <<'PY'
import json
import os

target = os.environ["RCA_FINAL_CONTACT_TARGET"]
raw = os.environ.get("RCA_FINAL_CONTACT_INSTANCES_JSON", "").strip()
try:
    data = json.loads(raw)
except json.JSONDecodeError:
    raise SystemExit(20)

if not isinstance(data, dict) or "workspaces" not in data:
    raise SystemExit(20)
instances = data["workspaces"]
if instances is None:
    instances = []
if not isinstance(instances, list) or any(not isinstance(item, dict) for item in instances):
    raise SystemExit(20)

tokens: list[str] = []
for item in instances or []:
    if not isinstance(item, dict):
        continue
    name = str(item.get("name") or item.get("workspaceName") or item.get("workspace_name") or "")
    ident = str(item.get("id") or item.get("workspaceId") or item.get("workspace_id") or "")
    if target not in {name, ident}:
        continue
    for token in (name, ident):
        if token and token not in tokens:
            tokens.append(token)

for token in tokens:
    print(token)
PY
}

delete_instance() {
  # The hosted owner is the only mutation authority. No name-based delete, retry
  # loop or second local watchdog may race its persisted exact-ID intention.
  python3 "${SCRIPT_DIR}/paid_run_hosted.py" finish
}

confirm_org_empty() {
  local attempt raw count parse_status

  echo "[final-contact-servo] confirming Brev org is empty"
  for attempt in $(seq 1 "${DELETE_ATTEMPTS}"); do
    if ! raw="$(run_with_timeout "${BREV_QUERY_TIMEOUT_SECONDS}" "${BREV_BIN}" ls instances --json --all 2>/dev/null)"; then
      echo "[final-contact-servo] org query failed; cleanup not confirmed attempt=${attempt}" >&2
      sleep "${DELETE_RETRY_INTERVAL_SECONDS}"
      continue
    fi
    set +e
    count="$(
      RCA_FINAL_CONTACT_INSTANCES_JSON="${raw}" python3 - <<'PY'
import json
import os
import sys

raw = os.environ.get("RCA_FINAL_CONTACT_INSTANCES_JSON", "").strip()
try:
    data = json.loads(raw)
except json.JSONDecodeError:
    print("invalid")
    sys.exit(20)

if not isinstance(data, dict) or "workspaces" not in data:
    sys.exit(20)
instances = data["workspaces"]
if instances is None:
    instances = []
if not isinstance(instances, list) or any(not isinstance(item, dict) for item in instances):
    sys.exit(20)

print(len(instances))
PY
    )"
    parse_status=$?
    set -e
    if [[ "${parse_status}" -eq 0 && "${count}" == "0" ]]; then
      echo "[final-contact-servo] org cleanup confirmed: ${raw}"
      return 0
    fi
    echo "[final-contact-servo] org still not empty or unparsable attempt=${attempt}: ${raw}" >&2
    sleep "${DELETE_RETRY_INTERVAL_SECONDS}"
  done

  echo "[final-contact-servo] manual cleanup required: Brev org is not confirmed empty" >&2
  run_with_timeout "${BREV_QUERY_TIMEOUT_SECONDS}" "${BREV_BIN}" ls instances --json --all || true
  return 1
}

pull_remote_artifacts() {
  if [[ "${REMOTE_INITIALIZED}" != "1" ]]; then
    echo "[final-contact-servo] remote initialization never completed; no task artifacts to pull"
    return 0
  fi
  echo "[final-contact-servo] pulling remote artifacts before cleanup"
  run_with_timeout "${PULLBACK_TIMEOUT_SECONDS}" env RCA_REMOTE_OPERATION_PURPOSE="${OPERATION_PURPOSE}" \
    "${SCRIPT_DIR}/pull_artifacts.sh" "${ENV_NAME}" "${REMOTE_ROOT}" "${REPO_ROOT}/artifacts"
}

start_container_xvfb() {
  echo "[final-contact-servo] starting Xvfb inside task container"
  run_preparation xvfb "${BREV_BIN}" exec "${ENV_NAME}" \
    "sudo docker exec -u root isaac-runner bash -lc 'set -euo pipefail; apt-get update >/dev/null; DEBIAN_FRONTEND=noninteractive apt-get install -y xvfb xauth x11-xserver-utils x11-utils >/dev/null; pkill -TERM -x Xvfb 2>/dev/null || true; nohup Xvfb :99 -screen 0 1280x720x24 -ac -extension GLX >/tmp/rca-xvfb.log 2>&1 & sleep 2; DISPLAY=:99 xdpyinfo | sed -n 1,5p'"
}

cleanup() {
  local status=$?
  local cleanup_status=0
  local pullback_status=0
  set +e
  echo "[final-contact-servo] cleanup status=${status}"
  if [[ "${CREATED_INSTANCE}" == "1" ]]; then
    pull_remote_artifacts || pullback_status=$?
    mkdir -p "${WATCHDOG_DIR}"
    printf 'pullback_exit=%s\n' "${pullback_status}" > "${WATCHDOG_DIR}/artifact_pullback.status"
    if [[ "${pullback_status}" -ne 0 ]]; then
      echo "[final-contact-servo] ARTIFACT_PULLBACK_FAILED; preserving partial local data and stopping billing, NOT reporting a complete archive" >&2
    fi
    delete_instance || cleanup_status=1
    confirm_org_empty || cleanup_status=1
  else
    echo "[final-contact-servo] no Brev instance was created"
    confirm_org_empty || cleanup_status=1
  fi
  if [[ ( "${cleanup_status}" -ne 0 || "${pullback_status}" -ne 0 ) && "${status}" -eq 0 ]]; then
    status=1
  fi
  exit "${status}"
}

trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

if [[ "${RCA_ALLOW_PAID_BREV_CREATE:-0}" != "1" ]]; then
  cat >&2 <<'EOF'
[final-contact-servo] refusing to create a paid Brev instance.
[final-contact-servo] Set RCA_ALLOW_PAID_BREV_CREATE=1 and RCA_BREV_CREDITS_VERIFIED=1 only after confirming credits, budget, and deletion path.
EOF
  exit 2
fi

RCA_PAID_RUN_PURPOSE="${RCA_PAID_RUN_PURPOSE:-post_contact_gate}" \
RCA_PAID_INSTANCE_NAME="${ENV_NAME}" \
RCA_PAID_MAX_MINUTES="${WATCHDOG_MAX_MINUTES}" \
RCA_BREV_CREDITS_VERIFIED="${RCA_BREV_CREDITS_VERIFIED:-0}" \
RCA_BREV_CLI="${BREV_BIN}" \
  "${SCRIPT_DIR}/paid_compute_preflight.sh"

echo "[final-contact-servo] creating Brev instance ${ENV_NAME} type=${INSTANCE_TYPE}"
python3 "${SCRIPT_DIR}/check_isaac_runtime_lock.py"
CREATE_SPEC="$(selected_instance_spec)"
CREATED_INSTANCE=1
# No local deletion watchdog: independent GitHub owner was acknowledged before
# this wrapper. Its original origin includes all delay before this create.
HOSTED_PREPARATION_REMAINING="$(python3 - <<'PY'
import math, os, time
remaining = float(os.environ['RCA_HOSTED_ORIGIN_UTC']) + 1080 - time.time()
if not 0 < remaining <= 1080:
    raise SystemExit('hosted preparation deadline closed or uncertain')
print(math.floor(remaining))
PY
)"
PREPARATION_DEADLINE=$((SECONDS + HOSTED_PREPARATION_REMAINING))
# Keep CLI spec input inside the bounded child, not the supervisor's Python stdin.
run_preparation create env CREATE_SPEC="${CREATE_SPEC}" bash -c 'exec "$@" <<<"${CREATE_SPEC}"' _ \
  "${BREV_BIN}" create "${ENV_NAME}" \
  --count 1 --parallel 1 \
  --stoppable \
  --timeout "${CREATE_TIMEOUT}"

run_preparation ready python3 "${SCRIPT_DIR}/wait_brev_instance_ready.py" "${ENV_NAME}" \
  --instance-type "${INSTANCE_TYPE}" --brev-cli "${BREV_BIN}" \
  --timeout-seconds "${CREATE_TIMEOUT}" --refresh-ssh

# Test the independent runner's real SSH/read path on this bound instance before
# spending the remaining preparation window installing/running the simulator.
run_with_timeout 30 "${BREV_BIN}" exec "${ENV_NAME}" \
  "mkdir -p '${REMOTE_ROOT}/artifacts'; printf '%s\\n' '${ENV_NAME}' > '${REMOTE_ROOT}/artifacts/cleanup-canary.txt'"
python3 "${SCRIPT_DIR}/paid_run_hosted.py" probe

echo "[final-contact-servo] bootstrapping remote workspace"
run_preparation bootstrap env RCA_REMOTE_OPERATION_PURPOSE="${OPERATION_PURPOSE}" \
  "${SCRIPT_DIR}/bootstrap_brev_workspace.sh" "${ENV_NAME}" "${REMOTE_ROOT}"
REMOTE_INITIALIZED=1

echo "[final-contact-servo] syncing repository"
run_preparation sync env RCA_REMOTE_OPERATION_PURPOSE="${OPERATION_PURPOSE}" \
  "${SCRIPT_DIR}/sync_to_brev.sh" "${ENV_NAME}" "${REMOTE_ROOT}"

echo "[final-contact-servo] installing Isaac Lab runtime"
run_preparation install env RCA_REMOTE_OPERATION_PURPOSE="${OPERATION_PURPOSE}" \
RCA_ISAACLAB_RUNTIME_PROFILE="${RCA_ISAACLAB_RUNTIME_PROFILE:-trace-only}" \
RCA_SKIP_STREAM_STACK="${RCA_SKIP_STREAM_STACK:-1}" \
  "${SCRIPT_DIR}/install_remote_isaaclab_runtime.sh" "${ENV_NAME}" "${REMOTE_ROOT}" "${COMPOSE_ROOT}"

start_container_xvfb
python3 "${SCRIPT_DIR}/paid_run_hosted.py" admit --phases "${WATCHDOG_DIR}/preparation_phases.jsonl"

echo "[final-contact-servo] running trace-only final-contact servo validation"
set +e
run_with_timeout "${TRACE_TIMEOUT_SECONDS}" env RCA_REMOTE_OPERATION_PURPOSE="${OPERATION_PURPOSE}" \
RCA_REMOTE_DOCKER_EXEC_ENV="-u root -e DISPLAY=:99" \
RCA_TRACE_ONLY_TIMEOUT_SECONDS="${TRACE_TIMEOUT_SECONDS}" \
RCA_TRACE_ONLY_TIMEOUT_KILL_SECONDS="${TRACE_TIMEOUT_KILL_SECONDS}" \
RCA_VALIDATE_PEG_VIDEO_CANDIDATE="${VALIDATE_PEG_VIDEO_CANDIDATE}" \
  "${TRACE_RUNNER}" \
    "${ENV_NAME}" \
    "${REMOTE_ROOT}" \
    "${COMPOSE_ROOT}" \
    "${TASK_NAME}" \
    1 \
    "${STEPS}" \
    "${SEED}"
run_status=$?
set -e

if [[ "${run_status}" -ne 0 ]]; then
  echo "[final-contact-servo] trace validation failed status=${run_status}" >&2
  exit "${run_status}"
fi

if [[ "${VALIDATE_PEG_VIDEO_CANDIDATE}" == "1" ]]; then
  echo "[final-contact-servo] PASS: trace validated as peg-in-hole video candidate"
else
  echo "[final-contact-servo] PASS: trace runner completed; peg video candidate validation was disabled"
fi
