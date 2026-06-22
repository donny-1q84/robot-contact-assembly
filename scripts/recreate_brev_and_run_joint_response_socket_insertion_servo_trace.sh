#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

ENV_NAME="${1:-rca-joint-response-socket-servo-vm}"
REMOTE_ROOT="${2:-/home/ubuntu/projects/robot-contact-assembly}"
COMPOSE_ROOT="${3:-/home/ubuntu/isaac-compose}"
TASK_NAME="${4:-RCA-PegInHole-Franka-JointPos-Contact-Play-v0}"
STEPS="${5:-1200}"
SEED="${6:-42}"

RCA_FINAL_CONTACT_VALIDATE_PEG_VIDEO_CANDIDATE="${RCA_JOINT_RESPONSE_SOCKET_VALIDATE_PEG_VIDEO_CANDIDATE:-1}" \
RCA_FINAL_CONTACT_TRACE_RUNNER="${SCRIPT_DIR}/run_remote_joint_response_socket_insertion_servo_trace.sh" \
  "${SCRIPT_DIR}/recreate_brev_and_run_final_contact_servo_trace.sh" \
    "${ENV_NAME}" \
    "${REMOTE_ROOT}" \
    "${COMPOSE_ROOT}" \
    "${TASK_NAME}" \
    "${STEPS}" \
    "${SEED}"
