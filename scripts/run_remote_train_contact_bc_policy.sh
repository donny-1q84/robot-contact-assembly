#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
source "${SCRIPT_DIR}/remote_common.sh"

rca_init_remote_vars "${1:-}" "${2:-}" "${3:-}"

LOCAL_DATASET="${4:-${REPO_ROOT}/artifacts/datasets/phase2_contact_bc/phase2_contact_bc_dataset.jsonl}"
REMOTE_DATASET="${5:-/workspace/artifacts/datasets/phase2_contact_bc/phase2_contact_bc_dataset.jsonl}"
REMOTE_OUTPUT="${6:-/workspace/artifacts/policies/phase2_contact_bc/bc_mlp.pt}"
EPOCHS="${7:-250}"
TIMEOUT_SECONDS="${8:-900}"
EXTRA_TRAIN_ARGS="${9:-}"

if [[ ! -s "${LOCAL_DATASET}" ]]; then
  echo "[train-bc] local dataset missing or empty: ${LOCAL_DATASET}" >&2
  echo "[train-bc] generate it with: python3 scripts/extract_contact_demo_dataset.py" >&2
  exit 2
fi

"${SCRIPT_DIR}/sync_to_brev.sh" "${RCA_ENV_NAME}" "${RCA_REMOTE_ROOT}"

REMOTE_DATASET_HOST_PATH="${RCA_REMOTE_ROOT}/artifacts/datasets/phase2_contact_bc/$(basename "${REMOTE_DATASET}")"
REMOTE_DATASET_HOST_DIR="$(dirname "${REMOTE_DATASET_HOST_PATH}")"
REMOTE_OUTPUT_DIR="$(dirname "${REMOTE_OUTPUT}")"
REMOTE_LOG_PATH="${REMOTE_OUTPUT_DIR}/train.log"
REMOTE_COMMAND_PATH="${REMOTE_OUTPUT_DIR}/train_command.txt"

echo "[train-bc] env=${RCA_ENV_NAME}"
echo "[train-bc] local_dataset=${LOCAL_DATASET}"
echo "[train-bc] remote_dataset=${REMOTE_DATASET}"
echo "[train-bc] remote_output=${REMOTE_OUTPUT}"
echo "[train-bc] epochs=${EPOCHS} timeout_seconds=${TIMEOUT_SECONDS}"

ssh "${RCA_ENV_NAME}" "mkdir -p '${REMOTE_DATASET_HOST_DIR}'"
rsync -az "${LOCAL_DATASET}" "${RCA_ENV_NAME}:${REMOTE_DATASET_HOST_PATH}"

rca_remote_container_exec "mkdir -p '${REMOTE_OUTPUT_DIR}'"
rca_remote_container_exec "cat > '${REMOTE_COMMAND_PATH}' <<'EOF'
/isaac-sim/python.sh scripts/train_contact_bc_policy.py --dataset '${REMOTE_DATASET}' --output '${REMOTE_OUTPUT}' --epochs '${EPOCHS}' ${EXTRA_TRAIN_ARGS}
EOF"

set +e
rca_remote_repo_exec "set -o pipefail && timeout ${TIMEOUT_SECONDS} /isaac-sim/python.sh scripts/train_contact_bc_policy.py --dataset '${REMOTE_DATASET}' --output '${REMOTE_OUTPUT}' --epochs '${EPOCHS}' ${EXTRA_TRAIN_ARGS} 2>&1 | tee '${REMOTE_LOG_PATH}'"
status=$?
set -e
if [[ ${status} -ne 0 ]]; then
  echo "[train-bc] training failed with status=${status}" >&2
  echo "[train-bc] inspect ${REMOTE_LOG_PATH}" >&2
  exit "${status}"
fi

echo "[train-bc] checkpoint: ${REMOTE_OUTPUT}"
echo "[train-bc] log:        ${REMOTE_LOG_PATH}"
echo "[train-bc] command:    ${REMOTE_COMMAND_PATH}"
