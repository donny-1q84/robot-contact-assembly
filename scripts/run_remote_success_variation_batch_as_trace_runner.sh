#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

ENV_NAME="${1:-${RCA_SUCCESS_VARIATION_ENV_NAME:-isaac-l40s}}"
REMOTE_ROOT="${2:-${RCA_SUCCESS_VARIATION_REMOTE_ROOT:-/home/ubuntu/projects/robot-contact-assembly}}"
COMPOSE_ROOT="${3:-${RCA_SUCCESS_VARIATION_COMPOSE_ROOT:-/home/ubuntu/isaac-compose}}"
TASK_NAME="${4:-RCA-PegInHole-Franka-JointPos-Contact-Play-v0}"
NUM_ENVS="${5:-1}"
STEPS="${6:-${RCA_SUCCESS_VARIATION_STEPS:-220}}"
SEED="${7:-42}"
MANIFEST="${RCA_SUCCESS_VARIATION_MANIFEST:-${REPO_ROOT}/artifacts/manifests/success_trace_variations_2026-06-25.json}"

echo "[success-variation-trace-runner] env=${ENV_NAME}"
echo "[success-variation-trace-runner] manifest=${MANIFEST}"
echo "[success-variation-trace-runner] task=${TASK_NAME}"
echo "[success-variation-trace-runner] steps=${STEPS}"
echo "[success-variation-trace-runner] num_envs_arg=${NUM_ENVS}"
echo "[success-variation-trace-runner] seed_arg=${SEED} (manifest case seeds are authoritative)"

RCA_SUCCESS_VARIATION_TASK="${TASK_NAME}" \
RCA_SUCCESS_VARIATION_STEPS="${STEPS}" \
  "${SCRIPT_DIR}/run_remote_success_variation_batch.sh" \
    "${MANIFEST}" \
    "${ENV_NAME}" \
    "${REMOTE_ROOT}" \
    "${COMPOSE_ROOT}"
