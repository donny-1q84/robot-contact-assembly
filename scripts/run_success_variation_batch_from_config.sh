#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

DEFAULT_CONFIG="${REPO_ROOT}/configs/success_variation_batch_run.local.env"
EXAMPLE_CONFIG="${REPO_ROOT}/configs/success_variation_batch_run.env.example"
CONFIG_PATH="${1:-${DEFAULT_CONFIG}}"
MODE="${2:---run}"

usage() {
  cat >&2 <<EOF
Usage:
  $0 [config-env-file] [--check-only|--run]

Default config path:
  ${DEFAULT_CONFIG}

Template:
  ${EXAMPLE_CONFIG}

The config file may only contain KEY=VALUE assignments, blank lines, and # comments.
Real acknowledgement values should live in the ignored *.local.env file, not in git.
EOF
}

if [[ "${CONFIG_PATH}" == "-h" || "${CONFIG_PATH}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ "${CONFIG_PATH}" == "--check-only" || "${CONFIG_PATH}" == "--run" ]]; then
  MODE="${CONFIG_PATH}"
  CONFIG_PATH="${DEFAULT_CONFIG}"
fi

case "${MODE}" in
  --check-only|--run)
    ;;
  *)
    usage
    exit 2
    ;;
esac

if [[ ! -f "${CONFIG_PATH}" ]]; then
  if [[ "${CONFIG_PATH}" == "${DEFAULT_CONFIG}" && -f "${EXAMPLE_CONFIG}" ]]; then
    echo "[success-variation-config] missing local config: ${DEFAULT_CONFIG}" >&2
    echo "[success-variation-config] running check against fail-closed template: ${EXAMPLE_CONFIG}" >&2
    CONFIG_PATH="${EXAMPLE_CONFIG}"
    MODE="--check-only"
  else
    echo "[success-variation-config] missing config: ${CONFIG_PATH}" >&2
    exit 2
  fi
fi

load_config() {
  local line key value line_no=0

  while IFS= read -r line || [[ -n "${line}" ]]; do
    line_no=$((line_no + 1))
    [[ -z "${line}" || "${line}" =~ ^[[:space:]]*# ]] && continue
    if [[ ! "${line}" =~ ^[A-Za-z_][A-Za-z0-9_]*= ]]; then
      echo "[success-variation-config] invalid config line ${line_no}: ${line}" >&2
      exit 2
    fi
    key="${line%%=*}"
    value="${line#*=}"
    case "${key}" in
      RCA_*|BREV_BIN)
        export "${key}=${value}"
        ;;
      *)
        echo "[success-variation-config] disallowed config key on line ${line_no}: ${key}" >&2
        exit 2
        ;;
    esac
  done < "${CONFIG_PATH}"
}

load_config

MANIFEST="${RCA_SUCCESS_VARIATION_MANIFEST:-${REPO_ROOT}/artifacts/manifests/success_trace_variations_2026-06-25.json}"
if [[ ! "${MANIFEST}" = /* ]]; then
  MANIFEST="${REPO_ROOT}/${MANIFEST}"
fi
ENV_NAME="${RCA_SUCCESS_VARIATION_ENV_NAME:-rca-success-variation-batch-vm}"
REMOTE_ROOT="${RCA_SUCCESS_VARIATION_REMOTE_ROOT:-/home/ubuntu/projects/robot-contact-assembly}"
COMPOSE_ROOT="${RCA_SUCCESS_VARIATION_COMPOSE_ROOT:-/home/ubuntu/isaac-compose}"
TASK_NAME="${RCA_SUCCESS_VARIATION_TASK:-RCA-PegInHole-Franka-JointPos-Contact-Play-v0}"
STEPS="${RCA_SUCCESS_VARIATION_STEPS:-220}"
SEED="${RCA_SUCCESS_VARIATION_SEED:-42}"

echo "[success-variation-config] config=${CONFIG_PATH}"
echo "[success-variation-config] mode=${MODE}"
echo "[success-variation-config] manifest=${MANIFEST}"
echo "[success-variation-config] env=${ENV_NAME}"
echo "[success-variation-config] steps=${STEPS}"
echo "[success-variation-config] ttl=${RCA_SUCCESS_VARIATION_WATCHDOG_MAX_MINUTES:-${RCA_FINAL_CONTACT_WATCHDOG_MAX_MINUTES:-${RCA_PAID_MAX_MINUTES:-<unset>}}}"
echo "[success-variation-config] budget_eur=${RCA_PAID_BUDGET_EUR:-<unset>}"
echo "[success-variation-config] estimated_eur_per_hour=${RCA_PAID_ESTIMATED_EUR_PER_HOUR:-<unset>}"

"${SCRIPT_DIR}/check_success_variation_batch_readiness.py" "${MANIFEST}"

if [[ "${MODE}" == "--check-only" ]]; then
  echo "[success-variation-config] check-only complete"
  exit 0
fi

"${SCRIPT_DIR}/recreate_brev_and_run_success_variation_batch.sh" \
  "${MANIFEST}" \
  "${ENV_NAME}" \
  "${REMOTE_ROOT}" \
  "${COMPOSE_ROOT}" \
  "${TASK_NAME}" \
  "${STEPS}" \
  "${SEED}"
