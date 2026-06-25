#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

MANIFEST="${1:-${REPO_ROOT}/artifacts/manifests/success_trace_variations_2026-06-25.json}"
if [[ ! "${MANIFEST}" = /* ]]; then
  MANIFEST="${REPO_ROOT}/${MANIFEST}"
fi

RESULTS_ROOT="${RCA_SUCCESS_VARIATION_RESULTS_ROOT:-}"
MIN_STRICT_SUCCESSES="${RCA_SUCCESS_VARIATION_MIN_STRICT_SUCCESSES:-5}"
NEGATIVE_CONTROL_ID="${RCA_SUCCESS_VARIATION_NEGATIVE_CONTROL_ID:-socket_x_pos_25mm_negative_control}"
REVIEW_JSON="${RCA_SUCCESS_VARIATION_REVIEW_JSON:-${REPO_ROOT}/artifacts/analysis/success_trace_variation_batch_review_2026-06-25.json}"
REVIEW_MD="${RCA_SUCCESS_VARIATION_REVIEW_MD:-${REPO_ROOT}/artifacts/analysis/success_trace_variation_batch_review_2026-06-25.md}"
RESULT_GATE_JSON="${RCA_SUCCESS_VARIATION_RESULT_GATE_JSON:-${REPO_ROOT}/artifacts/analysis/success_trace_variation_result_gate_2026-06-25.json}"
DATASET_JSON="${RCA_SUCCESS_VARIATION_DATASET_JSON:-${REPO_ROOT}/artifacts/datasets/v0_scripted_skill_success_variations/manifest.json}"
DATASET_MD="${RCA_SUCCESS_VARIATION_DATASET_MD:-${REPO_ROOT}/artifacts/datasets/v0_scripted_skill_success_variations/README.md}"
SKIP_BREV_SAFETY="${RCA_SUCCESS_VARIATION_FINALIZE_SKIP_BREV_SAFETY:-0}"

echo "[success-variation-finalize] manifest=${MANIFEST}"
echo "[success-variation-finalize] min_strict_successes=${MIN_STRICT_SUCCESSES}"
echo "[success-variation-finalize] negative_control_id=${NEGATIVE_CONTROL_ID}"
echo "[success-variation-finalize] review_json=${REVIEW_JSON}"
echo "[success-variation-finalize] result_gate_json=${RESULT_GATE_JSON}"
echo "[success-variation-finalize] dataset_json=${DATASET_JSON}"
echo "[success-variation-finalize] note: finalize is offline except optional read-only Brev safety review; it does not create or delete Brev instances"

COMMON_ARGS=(
  "${MANIFEST}"
  --min-strict-successes "${MIN_STRICT_SUCCESSES}"
  --negative-control-id "${NEGATIVE_CONTROL_ID}"
)
if [[ -n "${RESULTS_ROOT}" ]]; then
  COMMON_ARGS+=(--results-root "${RESULTS_ROOT}")
fi

REVIEW_ARGS=(
  "${COMMON_ARGS[@]}"
  --output-json "${REVIEW_JSON}"
  --output-md "${REVIEW_MD}"
  --fail-on-blocked
)
if [[ "${SKIP_BREV_SAFETY}" == "1" ]]; then
  REVIEW_ARGS+=(--skip-brev-safety)
fi

set +e
python3 "${SCRIPT_DIR}/review_success_variation_batch.py" "${REVIEW_ARGS[@]}"
review_status=$?
set -e

if [[ "${review_status}" -ne 0 ]]; then
  echo "[success-variation-finalize] BLOCKED: review did not reach ready_for_dataset_policy_preparation" >&2
  echo "[success-variation-finalize] wrote review record: ${REVIEW_JSON}" >&2
  exit "${review_status}"
fi

python3 "${SCRIPT_DIR}/check_success_variation_batch_results.py" "${COMMON_ARGS[@]}" \
  --output-json "${RESULT_GATE_JSON}"

python3 "${SCRIPT_DIR}/prepare_success_variation_dataset.py" "${COMMON_ARGS[@]}" \
  --output-json "${DATASET_JSON}" \
  --output-md "${DATASET_MD}"

echo "[success-variation-finalize] PASS: dataset prepared for policy/API review"
