#!/usr/bin/env bash
set -euo pipefail

if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
  echo "Do not source this script; execute it as a command." >&2
  return 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

BREV_BIN="${RCA_BREV_CLI:-${BREV_BIN:-/Users/Shenghan/bin/brev}}"
PURPOSE="${RCA_PAID_RUN_PURPOSE:-post_contact_gate}"
INSTANCE_NAME="${RCA_PAID_INSTANCE_NAME:-}"
MAX_MINUTES="${RCA_PAID_MAX_MINUTES:-${RCA_BREV_WATCHDOG_MAX_MINUTES:-${RCA_BREV_MAX_MINUTES:-}}}"
BUDGET_EUR="${RCA_PAID_BUDGET_EUR:-}"
ESTIMATED_EUR_PER_HOUR="${RCA_PAID_ESTIMATED_EUR_PER_HOUR:-${RCA_BREV_UI_PRICE_EUR_PER_HOUR:-}}"
CREDITS_VERIFIED="${RCA_BREV_CREDITS_VERIFIED:-0}"
QUERY_TIMEOUT_SECONDS="${RCA_PAID_PREFLIGHT_QUERY_TIMEOUT_SECONDS:-45}"
ALLOW_CREATE="${RCA_ALLOW_PAID_BREV_CREATE:-0}"
LIFECYCLE_HOLD_FILE="${RCA_BREV_LIFECYCLE_HOLD_FILE:-${REPO_ROOT}/docs/brev_launchable_lifecycle_hold.md}"
ACK_LIFECYCLE_RISK="${RCA_ACK_BREV_LIFECYCLE_RISK:-0}"

log() {
  echo "[paid-preflight] $*" >&2
}

fail() {
  echo "[paid-preflight] BLOCKED: $*" >&2
  exit 2
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

if [[ "${ALLOW_CREATE}" != "1" ]]; then
  fail "set RCA_ALLOW_PAID_BREV_CREATE=1 only after deciding this paid run is allowed"
fi

if [[ -z "${BUDGET_EUR}" || ! "${BUDGET_EUR}" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
  fail "set RCA_PAID_BUDGET_EUR to the explicit budget for this paid run"
fi

if [[ -z "${MAX_MINUTES}" || ! "${MAX_MINUTES}" =~ ^[0-9]+$ || "${MAX_MINUTES}" -lt 1 ]]; then
  fail "set RCA_PAID_MAX_MINUTES or RCA_BREV_WATCHDOG_MAX_MINUTES to a positive integer"
fi

if [[ -z "${ESTIMATED_EUR_PER_HOUR}" || ! "${ESTIMATED_EUR_PER_HOUR}" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
  fail "set RCA_PAID_ESTIMATED_EUR_PER_HOUR to a conservative EUR/hour estimate from the UI/provider price"
fi

if [[ "${CREDITS_VERIFIED}" != "1" ]]; then
  fail "set RCA_BREV_CREDITS_VERIFIED=1 only after confirming the Brev UI/org credit balance can cover the explicit budget"
fi

set +e
budget_check="$(
  BUDGET_EUR="${BUDGET_EUR}" \
  MAX_MINUTES="${MAX_MINUTES}" \
  ESTIMATED_EUR_PER_HOUR="${ESTIMATED_EUR_PER_HOUR}" \
  python3 - <<'PY'
import os
import sys

budget = float(os.environ["BUDGET_EUR"])
minutes = int(os.environ["MAX_MINUTES"])
hourly = float(os.environ["ESTIMATED_EUR_PER_HOUR"])
estimated_total = hourly * minutes / 60.0
print(f"{estimated_total:.4f}")
if estimated_total - budget > 1e-9:
    sys.exit(3)
PY
)"
budget_status=$?
set -e
if (( budget_status != 0 )); then
  fail "estimated max cost ${budget_check} EUR exceeds budget ${BUDGET_EUR} EUR; lower TTL, choose a cheaper GPU, or raise the explicit budget"
fi

case "${PURPOSE}" in
  contact_physics_smoke)
    log "purpose=contact_physics_smoke; Phase 2 gate may still be blocked"
    ;;
  post_contact_gate)
    log "checking Phase 2 contact gate before post-contact paid work"
    python3 "${SCRIPT_DIR}/check_phase2_contact_gate.py"
    ;;
  *)
    fail "unknown RCA_PAID_RUN_PURPOSE=${PURPOSE}; use contact_physics_smoke or post_contact_gate"
    ;;
esac

if [[ ! -x "${BREV_BIN}" ]]; then
  fail "Brev CLI is not executable: ${BREV_BIN}"
fi

log "checking Brev CLI auth and active instance list"
set +e
brev_json="$(run_with_timeout "${QUERY_TIMEOUT_SECONDS}" "${BREV_BIN}" ls instances --json --all)"
brev_status=$?
set -e
if (( brev_status != 0 )); then
  printf '%s\n' "${brev_json}" >&2
  fail "Brev CLI query failed or login expired; refresh NVIDIA/Brev login before any paid action"
fi

set +e
instance_count="$(
  BREV_INSTANCES_JSON="${brev_json}" python3 - <<'PY'
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
)"
parse_status=$?
set -e
if (( parse_status != 0 )) || [[ ! "${instance_count}" =~ ^[0-9]+$ ]]; then
  printf '%s\n' "${brev_json}" >&2
  fail "Brev instance JSON could not be parsed"
fi

if (( instance_count > 0 )); then
  printf '%s\n' "${brev_json}" >&2
  fail "Brev org is not empty (${instance_count} visible instance(s)); delete/confirm cleanup before creating another"
fi

if [[ -f "${LIFECYCLE_HOLD_FILE}" && "${ACK_LIFECYCLE_RISK}" != "1" ]]; then
  echo "[paid-preflight] lifecycle hold file: ${LIFECYCLE_HOLD_FILE}" >&2
  sed -n '1,80p' "${LIFECYCLE_HOLD_FILE}" >&2 || true
  fail "Brev/Launchable lifecycle hold is active; wait for service recovery or set RCA_ACK_BREV_LIFECYCLE_RISK=1 after explicitly accepting the retry risk"
fi

cat <<EOF
[paid-preflight] PASS
[paid-preflight] repo=${REPO_ROOT}
[paid-preflight] purpose=${PURPOSE}
[paid-preflight] instance_name=${INSTANCE_NAME:-<not-set>}
[paid-preflight] budget_eur=${BUDGET_EUR}
[paid-preflight] estimated_eur_per_hour=${ESTIMATED_EUR_PER_HOUR}
[paid-preflight] estimated_max_cost_eur=${budget_check}
[paid-preflight] credits_verified=${CREDITS_VERIFIED}
[paid-preflight] max_minutes=${MAX_MINUTES}
[paid-preflight] visible_instances=${instance_count}
EOF
