#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

RCA_FINAL_CONTACT_TRACE_RUNNER="${SCRIPT_DIR}/run_remote_socket_insertion_servo_trace.sh" \
  "${SCRIPT_DIR}/recreate_brev_and_run_final_contact_servo_trace.sh" "$@"
