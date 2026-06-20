#!/usr/bin/env bash
set -euo pipefail

if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
  echo "Do not source this script; execute it as a command." >&2
  return 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

BREV_BIN="${RCA_BREV_CLI:-${BREV_BIN:-/Users/Shenghan/bin/brev}}"
QUERY_TIMEOUT_SECONDS="${RCA_BREV_SAFETY_QUERY_TIMEOUT_SECONDS:-45}"
LEDGER_ROOT="${RCA_BREV_WATCHDOG_LEDGER_ROOT:-${REPO_ROOT}/artifacts/brev_paid_runs}"
LIFECYCLE_HOLD_FILE="${RCA_BREV_LIFECYCLE_HOLD_FILE:-${REPO_ROOT}/docs/brev_launchable_lifecycle_hold.md}"
FAIL_ON_STALE_ALERTS="${RCA_BREV_SAFETY_FAIL_ON_STALE_ALERTS:-0}"
FAILURES=0
VISIBLE_INSTANCE_COUNT="unknown"
INSTANCE_LIST_PROVEN="0"

log() {
  echo "[brev-safety] $*"
}

warn() {
  echo "[brev-safety] WARNING: $*" >&2
  FAILURES=$((FAILURES + 1))
}

run_with_timeout() {
  local timeout_seconds="$1"
  shift

  local output_file status_file pid deadline status
  output_file="$(mktemp)"
  status_file="$(mktemp)"
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

count_instances() {
  BREV_INSTANCES_JSON="$1" python3 - <<'PY'
import json
import os
import sys

raw = os.environ.get("BREV_INSTANCES_JSON", "").strip()
try:
    data = json.loads(raw) if raw else None
except json.JSONDecodeError:
    print("invalid")
    sys.exit(20)

if isinstance(data, dict):
    instances = data.get("workspaces") or data.get("instances") or []
elif isinstance(data, list):
    instances = data
else:
    instances = []

if instances is None:
    instances = []

print(len(instances))
PY
}

print_watchdog_processes() {
  local processes=""

  if command -v pgrep >/dev/null 2>&1; then
    processes="$(pgrep -fl "[b]rev_paid_run_watchdog.sh" 2>/dev/null || true)"
  fi

  if [[ -z "${processes}" ]] && command -v ps >/dev/null 2>&1; then
    processes="$(ps ax -o pid= -o command= | grep "[b]rev_paid_run_watchdog.sh" || true)"
  fi

  if [[ -n "${processes}" ]]; then
    log "watchdog_processes=running"
    printf '%s\n' "${processes}"
  else
    log "watchdog_processes=none"
  fi
}

print_manual_delete_alerts() {
  local alert_file
  local found=0

  if [[ ! -d "${LEDGER_ROOT}" ]]; then
    log "watchdog_ledgers=none"
    return 0
  fi

  while IFS= read -r alert_file; do
    [[ -z "${alert_file}" ]] && continue
    if (( found == 0 )); then
      log "manual_delete_alerts=present"
    fi
    found=$((found + 1))
    printf '%s\n' "${alert_file}"
  done < <(find "${LEDGER_ROOT}" -maxdepth 3 -name manual_delete_required.txt -type f -print | sort | tail -10)

  if (( found == 0 )); then
    log "manual_delete_alerts=none"
  elif [[ "${INSTANCE_LIST_PROVEN}" == "1" && "${VISIBLE_INSTANCE_COUNT}" == "0" && "${FAIL_ON_STALE_ALERTS}" != "1" ]]; then
    log "manual_delete_alerts=stale_resolved current_visible_instances=0"
  else
    warn "watchdog ledger contains manual_delete_required.txt; inspect artifacts/brev_paid_runs before any paid work"
  fi
}

log "repo=${REPO_ROOT}"
log "brev_cli=${BREV_BIN}"

if [[ -f "${LIFECYCLE_HOLD_FILE}" ]]; then
  log "lifecycle_hold=active file=${LIFECYCLE_HOLD_FILE}"
else
  warn "lifecycle_hold=missing; paid preflight will not block lifecycle retries by hold file"
fi

if [[ ! -x "${BREV_BIN}" ]]; then
  warn "Brev CLI is not executable: ${BREV_BIN}"
  print_watchdog_processes
  print_manual_delete_alerts
  exit 2
fi

set +e
health_output="$(run_with_timeout "${QUERY_TIMEOUT_SECONDS}" "${BREV_BIN}" healthcheck)"
health_status=$?
set -e
if (( health_status == 0 )); then
  log "healthcheck=pass"
  printf '%s\n' "${health_output}"
else
  warn "healthcheck=fail status=${health_status}"
  printf '%s\n' "${health_output}" >&2
fi

set +e
org_output="$(run_with_timeout "${QUERY_TIMEOUT_SECONDS}" "${BREV_BIN}" org ls)"
org_status=$?
set -e
if (( org_status == 0 )); then
  log "org_list=pass"
  printf '%s\n' "${org_output}"
else
  warn "org_list=fail status=${org_status}; Brev login may be expired"
  printf '%s\n' "${org_output}" >&2
fi

set +e
instances_json="$(run_with_timeout "${QUERY_TIMEOUT_SECONDS}" "${BREV_BIN}" ls instances --json --all)"
instances_status=$?
set -e
if (( instances_status != 0 )); then
  warn "instance_list=fail status=${instances_status}; cannot prove the org is empty"
  printf '%s\n' "${instances_json}" >&2
else
  log "instance_list=pass"
  printf '%s\n' "${instances_json}"
  set +e
  instance_count="$(count_instances "${instances_json}")"
  parse_status=$?
  set -e
  if (( parse_status != 0 )) || [[ ! "${instance_count}" =~ ^[0-9]+$ ]]; then
    warn "visible_instances=unknown; instance JSON could not be parsed"
  elif (( instance_count > 0 )); then
    VISIBLE_INSTANCE_COUNT="${instance_count}"
    INSTANCE_LIST_PROVEN="1"
    warn "visible_instances=${instance_count}; paid resources may still be running"
  else
    VISIBLE_INSTANCE_COUNT="0"
    INSTANCE_LIST_PROVEN="1"
    log "visible_instances=0"
  fi
fi

print_watchdog_processes
print_manual_delete_alerts

if (( FAILURES > 0 )); then
  log "status=ATTENTION_REQUIRED"
  exit 2
fi

log "status=SAFE_NO_VISIBLE_PAID_INSTANCE"
