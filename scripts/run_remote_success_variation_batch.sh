#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

MANIFEST="${1:-${REPO_ROOT}/artifacts/manifests/success_trace_variations_2026-06-25.json}"
ENV_NAME="${2:-${RCA_SUCCESS_VARIATION_ENV_NAME:-isaac-l40s}}"
REMOTE_ROOT="${3:-${RCA_SUCCESS_VARIATION_REMOTE_ROOT:-/home/ubuntu/projects/robot-contact-assembly}}"
COMPOSE_ROOT="${4:-${RCA_SUCCESS_VARIATION_COMPOSE_ROOT:-/home/ubuntu/isaac-compose}}"
STEPS="${RCA_SUCCESS_VARIATION_STEPS:-220}"
TASK_NAME="${RCA_SUCCESS_VARIATION_TASK:-}"
LOCAL_ARTIFACT_ROOT="${RCA_SUCCESS_VARIATION_LOCAL_ARTIFACT_ROOT:-${REPO_ROOT}/artifacts}"
PLAN_JSON="${RCA_SUCCESS_VARIATION_PLAN_JSON:-${REPO_ROOT}/artifacts/analysis/success_trace_variation_batch_plan_2026-06-25.json}"
PLAN_SH="${RCA_SUCCESS_VARIATION_PLAN_SH:-${REPO_ROOT}/artifacts/analysis/success_trace_variation_batch_plan_2026-06-25.sh}"
CLASSIFICATION_JSON="${RCA_SUCCESS_VARIATION_CLASSIFICATION_JSON:-${REPO_ROOT}/artifacts/analysis/success_trace_variation_classification_2026-06-25.json}"
CLASSIFICATION_MD="${RCA_SUCCESS_VARIATION_CLASSIFICATION_MD:-${REPO_ROOT}/artifacts/analysis/success_trace_variation_classification_2026-06-25.md}"

echo "[success-variation-batch] manifest=${MANIFEST}"
echo "[success-variation-batch] env=${ENV_NAME}"
echo "[success-variation-batch] remote_root=${REMOTE_ROOT}"
echo "[success-variation-batch] compose_root=${COMPOSE_ROOT}"
echo "[success-variation-batch] steps=${STEPS}"
if [[ -n "${TASK_NAME}" ]]; then
  echo "[success-variation-batch] task=${TASK_NAME}"
fi
echo "[success-variation-batch] note: this script uses an existing remote environment; it does not create or delete Brev instances"

PLANNER_ARGS=(
  "${MANIFEST}"
  --env-name "${ENV_NAME}"
  --remote-root "${REMOTE_ROOT}"
  --compose-root "${COMPOSE_ROOT}"
  --steps "${STEPS}"
  --output-json "${PLAN_JSON}"
  --output-sh "${PLAN_SH}"
)
if [[ -n "${TASK_NAME}" ]]; then
  PLANNER_ARGS+=(--task "${TASK_NAME}")
fi

python3 "${SCRIPT_DIR}/plan_success_variation_batch.py" "${PLANNER_ARGS[@]}"

echo "[success-variation-batch] executing generated plan ${PLAN_SH}"
set +e
bash "${PLAN_SH}"
plan_status=$?
set -e
echo "[success-variation-batch] generated plan exit_status=${plan_status}"

echo "[success-variation-batch] pulling remote artifacts before local classification"
set +e
RCA_REMOTE_OPERATION_PURPOSE=post_contact_gate \
  "${SCRIPT_DIR}/pull_artifacts.sh" "${ENV_NAME}" "${REMOTE_ROOT}" "${LOCAL_ARTIFACT_ROOT}"
pull_status=$?
set -e
if [[ "${pull_status}" -ne 0 ]]; then
  echo "[success-variation-batch] artifact pull failed status=${pull_status}" >&2
fi

echo "[success-variation-batch] classifying pulled traces"
set +e
python3 "${SCRIPT_DIR}/classify_success_variation_results.py" "${MANIFEST}" \
  --output-json "${CLASSIFICATION_JSON}" \
  --output-md "${CLASSIFICATION_MD}"
classification_status=$?
set -e
if [[ "${classification_status}" -ne 0 ]]; then
  echo "[success-variation-batch] classification failed status=${classification_status}" >&2
fi

echo "[success-variation-batch] wrote ${CLASSIFICATION_JSON}"
echo "[success-variation-batch] wrote ${CLASSIFICATION_MD}"

if [[ "${plan_status}" -ne 0 ]]; then
  echo "[success-variation-batch] FAIL: returning generated plan status=${plan_status}" >&2
  exit "${plan_status}"
fi
if [[ "${pull_status}" -ne 0 ]]; then
  echo "[success-variation-batch] FAIL: returning artifact pull status=${pull_status}" >&2
  exit "${pull_status}"
fi
if [[ "${classification_status}" -ne 0 ]]; then
  echo "[success-variation-batch] FAIL: returning classification status=${classification_status}" >&2
  exit "${classification_status}"
fi

echo "[success-variation-batch] PASS"
