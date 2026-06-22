#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

RCA_FINAL_CONTACT_TRACE_RUNNER="${SCRIPT_DIR}/run_remote_action_semantics_probe_suite.sh" \
RCA_FINAL_CONTACT_INSTANCE_TYPE="${RCA_ACTION_SEMANTICS_INSTANCE_TYPE:-g6e.xlarge}" \
RCA_FINAL_CONTACT_WATCHDOG_MAX_MINUTES="${RCA_ACTION_SEMANTICS_WATCHDOG_MAX_MINUTES:-35}" \
RCA_FINAL_CONTACT_TRACE_TIMEOUT_SECONDS="${RCA_ACTION_SEMANTICS_TRACE_TIMEOUT_SECONDS:-600}" \
RCA_FINAL_CONTACT_TRACE_TIMEOUT_KILL_SECONDS="${RCA_ACTION_SEMANTICS_TRACE_TIMEOUT_KILL_SECONDS:-30}" \
RCA_FINAL_CONTACT_CREATE_TIMEOUT="${RCA_ACTION_SEMANTICS_CREATE_TIMEOUT:-900}" \
RCA_FINAL_CONTACT_WATCHDOG_LEDGER_DIR="${RCA_ACTION_SEMANTICS_WATCHDOG_LEDGER_DIR:-}" \
  "${SCRIPT_DIR}/recreate_brev_and_run_final_contact_servo_trace.sh" \
    "${1:-rca-action-semantics-suite-vm}" \
    "${2:-/home/ubuntu/projects/robot-contact-assembly}" \
    "${3:-/home/ubuntu/isaac-compose}" \
    "${4:-RCA-PegInHole-Franka-JointPos-Contact-Play-v0}" \
    "${5:-8}" \
    "${6:-42}"
