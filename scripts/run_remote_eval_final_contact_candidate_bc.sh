#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

ENV_NAME="${1:-isaac-l40s}"
REMOTE_ROOT="${2:-/home/ubuntu/projects/robot-contact-assembly}"
REMOTE_COMPOSE_ROOT="${3:-/home/ubuntu/isaac-compose}"
TASK_NAME="${4:-RCA-PegInHole-Franka-JointPos-Contact-Play-v0}"
NUM_ENVS="${5:-1}"
STEPS="${6:-400}"
SEED="${7:-42}"
CHECKPOINT="${8:-${RCA_FINAL_CONTACT_BC_REMOTE_OUTPUT:-/workspace/artifacts/policies/phase2_contact_bc_final_contact_candidates/bc_mlp.pt}}"
TIMEOUT_SECONDS="${9:-${RCA_FINAL_CONTACT_BC_EVAL_TIMEOUT_SECONDS:-900}}"
EXTRA_EVAL_ARGS="${10:-${RCA_FINAL_CONTACT_BC_EXTRA_EVAL_ARGS:-}}"

LOCAL_MANIFEST="${RCA_FINAL_CONTACT_BC_LOCAL_MANIFEST:-${REPO_ROOT}/artifacts/reports/final_contact_reset_candidates_2026-06-09.json}"
REMOTE_MANIFEST="${RCA_FINAL_CONTACT_BC_REMOTE_MANIFEST:-/workspace/artifacts/reports/final_contact_reset_candidates_2026-06-09.json}"
CANDIDATE_CATEGORY="${RCA_FINAL_CONTACT_BC_CANDIDATE_CATEGORY:-strict_near_miss}"
CANDIDATE_INDEX="${RCA_FINAL_CONTACT_BC_CANDIDATE_INDEX:-0}"
CONTROLLER="${RCA_FINAL_CONTACT_BC_CONTROLLER:-bc}"

if [[ ! -s "${LOCAL_MANIFEST}" ]]; then
  echo "[final-contact-bc-eval] missing manifest: ${LOCAL_MANIFEST}" >&2
  echo "[final-contact-bc-eval] generate it with:" >&2
  echo "  python3 scripts/select_final_contact_reset_candidates.py artifacts/evaluations/scripted --archive-glob 'artifacts/launchable_logs/rca-reachable-guard-results-*.tar.gz'" >&2
  exit 2
fi
if [[ "${REMOTE_MANIFEST}" != /workspace/artifacts/* ]]; then
  echo "[final-contact-bc-eval] REMOTE_MANIFEST must live under /workspace/artifacts: ${REMOTE_MANIFEST}" >&2
  exit 2
fi

REMOTE_MANIFEST_RELATIVE_PATH="${REMOTE_MANIFEST#/workspace/artifacts/}"
REMOTE_MANIFEST_HOST_PATH="${REMOTE_ROOT}/artifacts/${REMOTE_MANIFEST_RELATIVE_PATH}"
REMOTE_MANIFEST_HOST_DIR="$(dirname "${REMOTE_MANIFEST_HOST_PATH}")"

echo "[final-contact-bc-eval] env=${ENV_NAME} controller=${CONTROLLER}"
echo "[final-contact-bc-eval] checkpoint=${CHECKPOINT}"
echo "[final-contact-bc-eval] local_manifest=${LOCAL_MANIFEST}"
echo "[final-contact-bc-eval] remote_manifest=${REMOTE_MANIFEST}"
echo "[final-contact-bc-eval] candidate=${CANDIDATE_CATEGORY}[${CANDIDATE_INDEX}]"
echo "[final-contact-bc-eval] steps=${STEPS} timeout_seconds=${TIMEOUT_SECONDS}"

ssh "${ENV_NAME}" "sudo mkdir -p '${REMOTE_MANIFEST_HOST_DIR}'"
rsync -az --rsync-path="sudo rsync" "${LOCAL_MANIFEST}" "${ENV_NAME}:${REMOTE_MANIFEST_HOST_PATH}"
ssh "${ENV_NAME}" "sudo chmod 0644 '${REMOTE_MANIFEST_HOST_PATH}'"

CANDIDATE_ARGS="--controller '${CONTROLLER}' --preload-candidate-json '${REMOTE_MANIFEST}' --preload-candidate-category '${CANDIDATE_CATEGORY}' --preload-candidate-index '${CANDIDATE_INDEX}' ${EXTRA_EVAL_ARGS}"

exec "${SCRIPT_DIR}/run_remote_eval_contact_bc_policy.sh" \
  "${ENV_NAME}" \
  "${REMOTE_ROOT}" \
  "${REMOTE_COMPOSE_ROOT}" \
  "${TASK_NAME}" \
  "${NUM_ENVS}" \
  "${STEPS}" \
  "${SEED}" \
  "${CHECKPOINT}" \
  "${TIMEOUT_SECONDS}" \
  "${CANDIDATE_ARGS}"
