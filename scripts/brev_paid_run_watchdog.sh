#!/usr/bin/env bash
set -euo pipefail

if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
  echo "Do not source this script; execute it as a command." >&2
  return 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

BREV_BIN="${RCA_BREV_CLI:-${BREV_BIN:-/Users/Shenghan/bin/brev}}"
INSTANCE_NAME="${RCA_BREV_WATCHDOG_INSTANCE_NAME:-${RCA_BREV_INSTANCE_NAME:-}}"
INSTANCE_ID="${RCA_BREV_WATCHDOG_INSTANCE_ID:-${RCA_BREV_INSTANCE_ID:-}}"
SCOPE="${RCA_BREV_WATCHDOG_SCOPE:-target}"
MAX_MINUTES="${RCA_BREV_WATCHDOG_MAX_MINUTES:-${RCA_BREV_MAX_MINUTES:-}}"
BUDGET_EUR="${RCA_PAID_BUDGET_EUR:-}"
ESTIMATED_EUR_PER_HOUR="${RCA_PAID_ESTIMATED_EUR_PER_HOUR:-${RCA_BREV_UI_PRICE_EUR_PER_HOUR:-}}"
WAIT_FOR_APPEAR="${RCA_BREV_WATCHDOG_WAIT_FOR_APPEAR:-1}"
WAIT_MAX_MINUTES="${RCA_BREV_WATCHDOG_WAIT_MAX_MINUTES:-30}"
POLL_SECONDS="${RCA_BREV_WATCHDOG_POLL_SECONDS:-120}"
QUERY_TIMEOUT_SECONDS="${RCA_BREV_WATCHDOG_QUERY_TIMEOUT_SECONDS:-45}"
QUERY_FAILURE_LIMIT="${RCA_BREV_WATCHDOG_QUERY_FAILURE_LIMIT:-3}"
MUTATION_TIMEOUT_SECONDS="${RCA_BREV_WATCHDOG_MUTATION_TIMEOUT_SECONDS:-180}"
DELETE_TIMEOUT_SECONDS="${RCA_BREV_WATCHDOG_DELETE_TIMEOUT_SECONDS:-900}"
DELETE_RETRY_INTERVAL_SECONDS="${RCA_BREV_WATCHDOG_DELETE_RETRY_INTERVAL_SECONDS:-60}"
DELETE_ON_TIMEOUT="${RCA_BREV_WATCHDOG_DELETE_ON_TIMEOUT:-1}"
STOP_BEFORE_DELETE="${RCA_BREV_WATCHDOG_STOP_BEFORE_DELETE:-1}"
NOTIFY="${RCA_BREV_WATCHDOG_NOTIFY:-1}"
PLAY_SOUND="${RCA_BREV_WATCHDOG_SOUND:-1}"
DRY_RUN="${RCA_BREV_WATCHDOG_DRY_RUN:-0}"
ONCE="${RCA_BREV_WATCHDOG_ONCE:-0}"
DASHBOARD_URL="${RCA_BREV_WATCHDOG_DASHBOARD_URL:-https://brev.nvidia.com/org/org-3BaYGdtoRGmgc77Z7NHHhPSD254/environments}"
LEDGER_ROOT="${RCA_BREV_WATCHDOG_LEDGER_ROOT:-${REPO_ROOT}/artifacts/brev_paid_runs}"
RUN_ID="${RCA_BREV_WATCHDOG_RUN_ID:-$(date -u +"%Y-%m-%dT%H-%M-%SZ")}"
DELETE_SCOPE_ACK="${RCA_BREV_WATCHDOG_DELETE_SCOPE_ACK:-}"

safe_name() {
  printf '%s' "$1" | tr -c 'A-Za-z0-9_.@=-' '_'
}

if [[ -z "${MAX_MINUTES}" || ! "${MAX_MINUTES}" =~ ^[0-9]+$ || "${MAX_MINUTES}" -lt 1 ]]; then
  echo "[brev-watchdog] RCA_BREV_WATCHDOG_MAX_MINUTES must be a positive integer" >&2
  exit 2
fi

if [[ -z "${POLL_SECONDS}" || ! "${POLL_SECONDS}" =~ ^[0-9]+$ || "${POLL_SECONDS}" -lt 5 ]]; then
  echo "[brev-watchdog] RCA_BREV_WATCHDOG_POLL_SECONDS must be an integer >= 5" >&2
  exit 2
fi

if [[ -z "${QUERY_FAILURE_LIMIT}" || ! "${QUERY_FAILURE_LIMIT}" =~ ^[0-9]+$ || "${QUERY_FAILURE_LIMIT}" -lt 1 ]]; then
  echo "[brev-watchdog] RCA_BREV_WATCHDOG_QUERY_FAILURE_LIMIT must be an integer >= 1" >&2
  exit 2
fi

case "${SCOPE}" in
  target)
    if [[ -z "${INSTANCE_NAME}" && -z "${INSTANCE_ID}" ]]; then
      echo "[brev-watchdog] target scope requires RCA_BREV_WATCHDOG_INSTANCE_NAME or RCA_BREV_WATCHDOG_INSTANCE_ID" >&2
      exit 2
    fi
    ;;
  org)
    if [[ "${DELETE_ON_TIMEOUT}" == "1" && "${DELETE_SCOPE_ACK}" != "delete-all-visible-brev-instances" ]]; then
      cat >&2 <<'EOF'
[brev-watchdog] org scope can delete every visible Brev instance.
[brev-watchdog] Set RCA_BREV_WATCHDOG_DELETE_SCOPE_ACK=delete-all-visible-brev-instances to allow this.
EOF
      exit 2
    fi
    ;;
  *)
    echo "[brev-watchdog] unknown scope=${SCOPE}; use target or org" >&2
    exit 2
    ;;
esac

LEDGER_LABEL="${INSTANCE_NAME:-${INSTANCE_ID:-org}}"
LEDGER_DIR="${RCA_BREV_WATCHDOG_LEDGER_DIR:-${LEDGER_ROOT}/${RUN_ID}_$(safe_name "${LEDGER_LABEL}")}"
mkdir -p "${LEDGER_DIR}"
exec > >(tee -a "${LEDGER_DIR}/watchdog.log") 2>&1

log() {
  echo "[brev-watchdog] $(date -u +"%Y-%m-%dT%H:%M:%SZ") $*" >&2
}

record_event() {
  local event="$1"
  local detail="${2:-}"
  printf '%s\t%s\t%s\n' "$(date -u +"%Y-%m-%dT%H:%M:%SZ")" "${event}" "${detail}" >> "${LEDGER_DIR}/events.tsv"
}

notify_user() {
  local title="$1"
  local body="$2"

  if [[ "${NOTIFY}" != "1" ]]; then
    return 0
  fi
  if command -v osascript >/dev/null 2>&1; then
    RCA_NOTIFY_TITLE="${title}" RCA_NOTIFY_BODY="${body}" osascript >/dev/null 2>&1 <<'OSA' || true
display notification (system attribute "RCA_NOTIFY_BODY") with title (system attribute "RCA_NOTIFY_TITLE")
OSA
  fi
  if [[ "${PLAY_SOUND}" == "1" && -f /System/Library/Sounds/Basso.aiff ]]; then
    afplay /System/Library/Sounds/Basso.aiff >/dev/null 2>&1 || true
  fi
}

manual_delete_required() {
  local reason="$1"
  local body

  body="Manual Brev cleanup required: ${reason}. Open ${DASHBOARD_URL} and delete/stop ${LEDGER_LABEL}."
  log "MANUAL DELETE REQUIRED: ${reason}"
  cat > "${LEDGER_DIR}/manual_delete_required.txt" <<EOF
Manual Brev cleanup is required.

Reason: ${reason}
Scope: ${SCOPE}
Instance name: ${INSTANCE_NAME:-<unknown>}
Instance id: ${INSTANCE_ID:-<unknown>}
Dashboard: ${DASHBOARD_URL}
Recorded at: $(date -u +"%Y-%m-%dT%H:%M:%SZ")
EOF
  record_event "manual_delete_required" "${reason}"
  notify_user "Brev billing risk" "${body}"
}

run_with_timeout() {
  local timeout_seconds="$1"
  shift

  local output_file status_file pid deadline status
  output_file="${LEDGER_DIR}/.timeout_$$_${RANDOM}.out"
  status_file="${LEDGER_DIR}/.timeout_$$_${RANDOM}.status"

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

estimated_max_cost_eur() {
  if [[ -z "${BUDGET_EUR}" || -z "${ESTIMATED_EUR_PER_HOUR}" ]]; then
    printf '<not-recorded>\n'
    return 0
  fi
  if [[ ! "${ESTIMATED_EUR_PER_HOUR}" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
    printf '<invalid-hourly-estimate>\n'
    return 0
  fi
  ESTIMATED_EUR_PER_HOUR="${ESTIMATED_EUR_PER_HOUR}" \
  MAX_MINUTES="${MAX_MINUTES}" \
  python3 - <<'PY'
import os

hourly = float(os.environ["ESTIMATED_EUR_PER_HOUR"])
minutes = int(os.environ["MAX_MINUTES"])
print(f"{hourly * minutes / 60.0:.4f}")
PY
}

query_instances_json() {
  if [[ -n "${RCA_BREV_WATCHDOG_SAMPLE_JSON:-}" ]]; then
    printf '%s\n' "${RCA_BREV_WATCHDOG_SAMPLE_JSON}"
    return 0
  fi
  run_with_timeout "${QUERY_TIMEOUT_SECONDS}" "${BREV_BIN}" ls instances --json --all
}

write_start_metadata() {
  local estimated_max_cost
  estimated_max_cost="$(estimated_max_cost_eur)"
  cat > "${LEDGER_DIR}/watchdog_start.env" <<EOF
run_id=${RUN_ID}
scope=${SCOPE}
instance_name=${INSTANCE_NAME}
instance_id=${INSTANCE_ID}
budget_eur=${BUDGET_EUR:-<not-recorded>}
estimated_eur_per_hour=${ESTIMATED_EUR_PER_HOUR:-<not-recorded>}
estimated_max_cost_eur=${estimated_max_cost}
max_minutes=${MAX_MINUTES}
wait_for_appear=${WAIT_FOR_APPEAR}
wait_max_minutes=${WAIT_MAX_MINUTES}
poll_seconds=${POLL_SECONDS}
query_failure_limit=${QUERY_FAILURE_LIMIT}
delete_on_timeout=${DELETE_ON_TIMEOUT}
stop_before_delete=${STOP_BEFORE_DELETE}
dashboard_url=${DASHBOARD_URL}
ledger_dir=${LEDGER_DIR}
started_at_utc=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
EOF
}

filter_instances() {
  local raw="$1"
  WATCHDOG_JSON="${raw}" \
  WATCHDOG_SCOPE="${SCOPE}" \
  WATCHDOG_INSTANCE_NAME="${INSTANCE_NAME}" \
  WATCHDOG_INSTANCE_ID="${INSTANCE_ID}" \
  python3 - <<'PY'
import json
import os
import sys

raw = os.environ.get("WATCHDOG_JSON", "").strip()
scope = os.environ["WATCHDOG_SCOPE"]
target_name = os.environ.get("WATCHDOG_INSTANCE_NAME", "")
target_id = os.environ.get("WATCHDOG_INSTANCE_ID", "")

try:
    data = json.loads(raw) if raw else None
except json.JSONDecodeError:
    sys.exit(20)

if isinstance(data, dict):
    instances = data.get("workspaces") or data.get("instances") or []
elif isinstance(data, list):
    instances = data
else:
    instances = []

def value(item, *keys):
    for key in keys:
        found = item
        ok = True
        for part in key.split("."):
            if isinstance(found, dict) and part in found:
                found = found[part]
            else:
                ok = False
                break
        if ok and found not in (None, ""):
            return str(found)
    return ""

for item in instances:
    if not isinstance(item, dict):
        continue
    name = value(item, "name", "workspaceName", "workspace_name")
    ident = value(item, "id", "workspaceId", "workspace_id")
    status = value(item, "status", "machineStatus", "machine_status", "state")
    build = value(item, "buildStatus", "build_status", "lifecycleStatus", "lifecycle_status")
    ready = value(item, "readyStatus", "ready_status", "readiness", "ready")

    matched = scope == "org"
    if scope == "target":
        matched = (target_name and name == target_name) or (target_id and ident == target_id)
    if matched:
        print("\t".join([ident, name, status, build, ready]))
PY
}

target_tokens_from_lines() {
  local lines="$1"
  TARGET_LINES="${lines}" python3 - <<'PY'
import os

seen = set()
for line in os.environ.get("TARGET_LINES", "").splitlines():
    parts = line.split("\t")
    ident = parts[0].strip() if len(parts) > 0 else ""
    name = parts[1].strip() if len(parts) > 1 else ""
    token = name or ident
    if token and token not in seen:
        seen.add(token)
        print(token)
PY
}

stop_targets() {
  local lines="$1"
  local tokens=()
  local token

  if [[ "${STOP_BEFORE_DELETE}" != "1" ]]; then
    return 0
  fi
  if [[ "${SCOPE}" == "org" ]]; then
    log "stopping all visible Brev instances"
    if [[ "${DRY_RUN}" == "1" ]]; then
      log "dry-run: ${BREV_BIN} stop --all"
      return 0
    fi
    run_with_timeout "${MUTATION_TIMEOUT_SECONDS}" "${BREV_BIN}" stop --all
    return $?
  fi

  while IFS= read -r token; do
    [[ -n "${token}" ]] && tokens+=("${token}")
  done < <(target_tokens_from_lines "${lines}")
  if (( ${#tokens[@]} == 0 )); then
    return 0
  fi
  log "stopping target(s): ${tokens[*]}"
  if [[ "${DRY_RUN}" == "1" ]]; then
    log "dry-run: ${BREV_BIN} stop ${tokens[*]}"
    return 0
  fi
  run_with_timeout "${MUTATION_TIMEOUT_SECONDS}" "${BREV_BIN}" stop "${tokens[@]}"
}

delete_targets() {
  local lines="$1"
  local tokens=()
  local token

  if [[ "${DELETE_ON_TIMEOUT}" != "1" ]]; then
    manual_delete_required "watchdog TTL expired but RCA_BREV_WATCHDOG_DELETE_ON_TIMEOUT=0"
    return 1
  fi

  while IFS= read -r token; do
    [[ -n "${token}" ]] && tokens+=("${token}")
  done < <(target_tokens_from_lines "${lines}")
  if (( ${#tokens[@]} == 0 )); then
    log "no target tokens found for delete"
    return 0
  fi

  log "deleting target(s): ${tokens[*]}"
  if [[ "${DRY_RUN}" == "1" ]]; then
    log "dry-run: ${BREV_BIN} delete ${tokens[*]}"
    return 0
  fi
  run_with_timeout "${MUTATION_TIMEOUT_SECONDS}" "${BREV_BIN}" delete "${tokens[@]}"
}

poll_current_targets() {
  local raw status lines parse_status query_failures failure_count_file
  failure_count_file="${LEDGER_DIR}/query_failure_count.txt"

  set +e
  raw="$(query_instances_json)"
  status=$?
  set -e
  printf '%s\n' "${raw}" > "${LEDGER_DIR}/latest_brev_instances.json"
  if (( status != 0 )); then
    query_failures=0
    if [[ -f "${failure_count_file}" ]]; then
      query_failures="$(cat "${failure_count_file}" 2>/dev/null || printf '0')"
      [[ "${query_failures}" =~ ^[0-9]+$ ]] || query_failures=0
    fi
    query_failures=$((query_failures + 1))
    printf '%s\n' "${query_failures}" > "${failure_count_file}"
    printf '%s\n' "${raw}" > "${LEDGER_DIR}/latest_brev_instances_error.txt"
    log "Brev CLI instance query failed (${query_failures}/${QUERY_FAILURE_LIMIT})"
    record_event "query_failed" "count=${query_failures}"
    if (( query_failures < QUERY_FAILURE_LIMIT )); then
      return 85
    fi
    manual_delete_required "Brev CLI instance query failed ${query_failures} consecutive times or login expired"
    return 86
  fi
  printf '0\n' > "${failure_count_file}"

  set +e
  lines="$(filter_instances "${raw}")"
  parse_status=$?
  set -e
  if (( parse_status != 0 )); then
    manual_delete_required "Brev instance JSON could not be parsed"
    return 86
  fi

  printf '%s\n' "${lines}"
}

wait_until_absent_after_delete() {
  local deadline last_retry lines status
  deadline=$((SECONDS + DELETE_TIMEOUT_SECONDS))
  last_retry=0

  while (( SECONDS < deadline )); do
    set +e
    lines="$(poll_current_targets)"
    status=$?
    set -e
    if (( status == 85 )); then
      log "transient Brev query failure while waiting for delete confirmation"
      sleep "${POLL_SECONDS}"
      continue
    fi
    if (( status != 0 )); then
      return "${status}"
    fi
    if [[ -z "${lines}" ]]; then
      log "target no longer visible after delete"
      record_event "cleanup_confirmed" "target absent"
      notify_user "Brev cleanup confirmed" "Brev target ${LEDGER_LABEL} is no longer visible."
      return 0
    fi
    log "target still visible after delete:"
    printf '%s\n' "${lines}"
    if (( SECONDS - last_retry >= DELETE_RETRY_INTERVAL_SECONDS )); then
      record_event "delete_retry" "${LEDGER_LABEL}"
      delete_targets "${lines}" || true
      last_retry="${SECONDS}"
    fi
    sleep "${POLL_SECONDS}"
  done

  manual_delete_required "delete did not clear target within ${DELETE_TIMEOUT_SECONDS}s"
  return 87
}

main() {
  local started_epoch first_seen_epoch wait_deadline deadline lines status age remaining estimated_cost
  started_epoch="$(date +%s)"
  first_seen_epoch=0
  wait_deadline=$((started_epoch + WAIT_MAX_MINUTES * 60))
  estimated_cost="$(estimated_max_cost_eur)"

  write_start_metadata
  record_event "started" "scope=${SCOPE} label=${LEDGER_LABEL}"
  log "watching scope=${SCOPE} label=${LEDGER_LABEL} max_minutes=${MAX_MINUTES} ledger=${LEDGER_DIR}"
  log "cost_boundary budget_eur=${BUDGET_EUR:-<not-recorded>} estimated_eur_per_hour=${ESTIMATED_EUR_PER_HOUR:-<not-recorded>} estimated_max_cost_eur=${estimated_cost}"
  log "dashboard=${DASHBOARD_URL}"

  while true; do
    set +e
    lines="$(poll_current_targets)"
    status=$?
    set -e
    if (( status == 85 )); then
      log "transient Brev query failure; continuing watchdog"
      sleep "${POLL_SECONDS}"
      continue
    fi
    if (( status != 0 )); then
      return "${status}"
    fi

    if [[ -z "${lines}" ]]; then
      if (( first_seen_epoch > 0 )); then
        log "target disappeared; cleanup confirmed"
        record_event "cleanup_confirmed" "target absent"
        return 0
      fi
      if [[ "${ONCE}" == "1" ]]; then
        log "target is not visible"
        return 0
      fi
      if [[ "${WAIT_FOR_APPEAR}" == "1" && "$(date +%s)" -lt "${wait_deadline}" ]]; then
        log "target not visible yet; waiting for creation"
        sleep "${POLL_SECONDS}"
        continue
      fi
      log "target never appeared within wait window; exiting"
      record_event "never_appeared" "${LEDGER_LABEL}"
      return 0
    fi

    if (( first_seen_epoch == 0 )); then
      first_seen_epoch="$(date +%s)"
      deadline=$((first_seen_epoch + MAX_MINUTES * 60))
      printf '%s\n' "${lines}" > "${LEDGER_DIR}/first_seen_targets.tsv"
      record_event "first_seen" "${LEDGER_LABEL}"
      notify_user "Brev watchdog armed" "Brev target ${LEDGER_LABEL} is visible. TTL: ${MAX_MINUTES} minutes."
    else
      deadline=$((first_seen_epoch + MAX_MINUTES * 60))
    fi

    printf '%s\n' "${lines}" > "${LEDGER_DIR}/latest_targets.tsv"
    age=$(( $(date +%s) - first_seen_epoch ))
    remaining=$(( deadline - $(date +%s) ))
    log "target visible age=${age}s remaining=${remaining}s"
    printf '%s\n' "${lines}"

    if [[ "${ONCE}" == "1" ]]; then
      return 0
    fi

    if (( remaining <= 0 )); then
      record_event "ttl_expired" "max_minutes=${MAX_MINUTES}"
      notify_user "Brev TTL expired" "Stopping/deleting Brev target ${LEDGER_LABEL} now."
      stop_targets "${lines}" || true
      if ! delete_targets "${lines}"; then
        manual_delete_required "watchdog could not issue Brev delete"
        return 87
      fi
      wait_until_absent_after_delete
      return $?
    fi

    sleep "${POLL_SECONDS}"
  done
}

main "$@"
