#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

ENV_NAME="${1:-isaac-l40s}"
REMOTE_ROOT="${2:-/home/ubuntu/projects/robot-contact-assembly}"
REMOTE_COMPOSE_ROOT="${3:-/home/ubuntu/isaac-compose}"
EPOCHS="${4:-${RCA_FINAL_CONTACT_BC_EPOCHS:-120}}"
TIMEOUT_SECONDS="${5:-${RCA_FINAL_CONTACT_BC_TIMEOUT_SECONDS:-900}}"
EXTRA_TRAIN_ARGS="${6:-${RCA_FINAL_CONTACT_BC_EXTRA_TRAIN_ARGS:---batch-size 256 --hidden-dim 128 --layers 3}}"

LOCAL_DATASET="${RCA_FINAL_CONTACT_BC_LOCAL_DATASET:-${REPO_ROOT}/artifacts/datasets/phase2_contact_bc_final_contact_candidates/phase2_contact_bc_final_contact_candidates_dataset.jsonl}"
REMOTE_DATASET="${RCA_FINAL_CONTACT_BC_REMOTE_DATASET:-/workspace/artifacts/datasets/phase2_contact_bc_final_contact_candidates/phase2_contact_bc_final_contact_candidates_dataset.jsonl}"
REMOTE_OUTPUT="${RCA_FINAL_CONTACT_BC_REMOTE_OUTPUT:-/workspace/artifacts/policies/phase2_contact_bc_final_contact_candidates/bc_mlp.pt}"

if [[ ! -s "${LOCAL_DATASET}" ]]; then
  echo "[final-contact-bc-train] missing dataset: ${LOCAL_DATASET}" >&2
  echo "[final-contact-bc-train] generate it with:" >&2
  echo "  python3 scripts/extract_final_contact_candidate_dataset.py" >&2
  exit 2
fi

echo "[final-contact-bc-train] env=${ENV_NAME}"
echo "[final-contact-bc-train] local_dataset=${LOCAL_DATASET}"
echo "[final-contact-bc-train] remote_output=${REMOTE_OUTPUT}"
echo "[final-contact-bc-train] epochs=${EPOCHS} timeout_seconds=${TIMEOUT_SECONDS}"
echo "[final-contact-bc-train] extra_train_args=${EXTRA_TRAIN_ARGS}"

exec "${SCRIPT_DIR}/run_remote_train_contact_bc_policy.sh" \
  "${ENV_NAME}" \
  "${REMOTE_ROOT}" \
  "${REMOTE_COMPOSE_ROOT}" \
  "${LOCAL_DATASET}" \
  "${REMOTE_DATASET}" \
  "${REMOTE_OUTPUT}" \
  "${EPOCHS}" \
  "${TIMEOUT_SECONDS}" \
  "${EXTRA_TRAIN_ARGS}"
