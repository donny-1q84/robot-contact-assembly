#!/usr/bin/env bash
set -euo pipefail

if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
  echo "Do not source this script; execute it as a command." >&2
  return 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

export RCA_BREV_WATCHDOG_SCOPE="${RCA_BREV_WATCHDOG_SCOPE:-org}"
export RCA_BREV_WATCHDOG_DELETE_SCOPE_ACK="${RCA_BREV_WATCHDOG_DELETE_SCOPE_ACK:-delete-all-visible-brev-instances}"
export RCA_BREV_WATCHDOG_MAX_MINUTES="${RCA_BREV_WATCHDOG_MAX_MINUTES:-60}"
export RCA_BREV_WATCHDOG_POLL_SECONDS="${RCA_BREV_WATCHDOG_POLL_SECONDS:-120}"
export RCA_BREV_WATCHDOG_WAIT_FOR_APPEAR="${RCA_BREV_WATCHDOG_WAIT_FOR_APPEAR:-1}"
export RCA_BREV_WATCHDOG_WAIT_MAX_MINUTES="${RCA_BREV_WATCHDOG_WAIT_MAX_MINUTES:-30}"
export RCA_BREV_WATCHDOG_DASHBOARD_URL="${RCA_BREV_WATCHDOG_DASHBOARD_URL:-https://brev.nvidia.com/org/org-3BaYGdtoRGmgc77Z7NHHhPSD254/environments}"

RCA_PAID_RUN_PURPOSE="${RCA_PAID_RUN_PURPOSE:-contact_physics_smoke}" \
RCA_PAID_MAX_MINUTES="${RCA_BREV_WATCHDOG_MAX_MINUTES}" \
  "${SCRIPT_DIR}/paid_compute_preflight.sh"

cat <<EOF
[brev-ui-watchdog] starting org-scope Brev watchdog
[brev-ui-watchdog] max_minutes=${RCA_BREV_WATCHDOG_MAX_MINUTES}
[brev-ui-watchdog] budget_eur=${RCA_PAID_BUDGET_EUR:-<not-recorded>}
[brev-ui-watchdog] estimated_eur_per_hour=${RCA_PAID_ESTIMATED_EUR_PER_HOUR:-${RCA_BREV_UI_PRICE_EUR_PER_HOUR:-<not-recorded>}}
[brev-ui-watchdog] dashboard=${RCA_BREV_WATCHDOG_DASHBOARD_URL}
[brev-ui-watchdog] this will stop/delete all visible Brev instances in the org when TTL expires
EOF

exec "${SCRIPT_DIR}/brev_paid_run_watchdog.sh"
