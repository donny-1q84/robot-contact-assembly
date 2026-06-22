#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

RCA_FINAL_CONTACT_TRACE_RUNNER="${SCRIPT_DIR}/run_remote_joint_response_semantics_probe_suite.sh" \
RCA_FINAL_CONTACT_INSTANCE_TYPE="${RCA_JOINT_RESPONSE_INSTANCE_TYPE:-g6e.xlarge}" \
RCA_FINAL_CONTACT_WATCHDOG_MAX_MINUTES="${RCA_JOINT_RESPONSE_WATCHDOG_MAX_MINUTES:-45}" \
RCA_FINAL_CONTACT_TRACE_TIMEOUT_SECONDS="${RCA_JOINT_RESPONSE_TRACE_TIMEOUT_SECONDS:-900}" \
RCA_FINAL_CONTACT_TRACE_TIMEOUT_KILL_SECONDS="${RCA_JOINT_RESPONSE_TRACE_TIMEOUT_KILL_SECONDS:-30}" \
RCA_FINAL_CONTACT_CREATE_TIMEOUT="${RCA_JOINT_RESPONSE_CREATE_TIMEOUT:-900}" \
RCA_FINAL_CONTACT_WATCHDOG_LEDGER_DIR="${RCA_JOINT_RESPONSE_WATCHDOG_LEDGER_DIR:-}" \
  "${SCRIPT_DIR}/recreate_brev_and_run_final_contact_servo_trace.sh" \
    "${1:-rca-joint-response-semantics-vm}" \
    "${2:-/home/ubuntu/projects/robot-contact-assembly}" \
    "${3:-/home/ubuntu/isaac-compose}" \
    "${4:-RCA-PegInHole-Franka-JointPos-Contact-Play-v0}" \
    "${5:-8}" \
    "${6:-42}"
