#!/usr/bin/env bash
set -euo pipefail

if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
  echo "Do not source this script; execute it as a command." >&2
  return 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

BREV_BIN="${RCA_BREV_CLI:-${BREV_BIN:-/Users/Shenghan/bin/brev}}"
RUN_ID="${RCA_BREV_INCIDENT_RUN_ID:-$(date -u +"%Y-%m-%dT%H-%M-%SZ")}"
OUT_DIR="${RCA_BREV_INCIDENT_OUTPUT_DIR:-${REPO_ROOT}/artifacts/brev_lifecycle_incidents/${RUN_ID}}"
SUPPORT_DRAFT="${RCA_BREV_SUPPORT_DRAFT:-${REPO_ROOT}/docs/brev_support_followup_2026-06-20.md}"
HOLD_FILE="${RCA_BREV_LIFECYCLE_HOLD_FILE:-${REPO_ROOT}/docs/brev_launchable_lifecycle_hold.md}"

log() {
  echo "[brev-incident] $*" >&2
}

capture() {
  local name="$1"
  shift
  local output_path="${OUT_DIR}/${name}.txt"
  {
    printf '$'
    printf ' %q' "$@"
    printf '\n\n'
    set +e
    "$@"
    local status=$?
    set -e
    printf '\n[exit_status] %s\n' "${status}"
  } >"${output_path}" 2>&1
}

mkdir -p "${OUT_DIR}"

log "writing evidence to ${OUT_DIR}"

capture "brev_ls_instances_json" "${BREV_BIN}" ls instances --json --all
capture "brev_healthcheck" "${BREV_BIN}" healthcheck
capture "brev_paid_safety_status" env RCA_BREV_CLI="${BREV_BIN}" "${SCRIPT_DIR}/brev_paid_safety_status.sh"
capture "source_payload_fingerprint" python3 "${SCRIPT_DIR}/source_payload_fingerprint.py"
capture "project_status_report" python3 "${SCRIPT_DIR}/project_status_report.py" --fail-on-blocked
capture "paid_preflight_hold_block" env \
  RCA_BREV_CLI="${BREV_BIN}" \
  RCA_ALLOW_PAID_BREV_CREATE=1 \
  RCA_BREV_CREDITS_VERIFIED=1 \
  RCA_PAID_BUDGET_EUR=1 \
  RCA_PAID_ESTIMATED_EUR_PER_HOUR=1 \
  RCA_PAID_MAX_MINUTES=5 \
  RCA_PAID_RUN_PURPOSE=contact_physics_smoke \
  "${SCRIPT_DIR}/paid_compute_preflight.sh"

if [[ "${RCA_INCIDENT_SKIP_LOCAL_QUALITY:-0}" != "1" ]]; then
  capture "local_quality_checks" "${SCRIPT_DIR}/run_local_quality_checks.sh"
fi

if [[ -f "${SUPPORT_DRAFT}" ]]; then
  cp "${SUPPORT_DRAFT}" "${OUT_DIR}/support_followup_draft.md"
fi
if [[ -f "${HOLD_FILE}" ]]; then
  cp "${HOLD_FILE}" "${OUT_DIR}/brev_launchable_lifecycle_hold.md"
fi

cat >"${OUT_DIR}/README.md" <<EOF
# Brev Launchable Lifecycle Incident Evidence

Run ID: ${RUN_ID}
Repo: ${REPO_ROOT}

This package is local evidence for the 2026-06-20 Brev/AWS Isaac Launchable
lifecycle failures that happened before shell access and before any project
workload ran.

Key files:

- \`brev_ls_instances_json.txt\`: current visible Brev instance list.
- \`brev_healthcheck.txt\`: Brev backend healthcheck output.
- \`brev_paid_safety_status.txt\`: read-only Brev safety snapshot, including
  active org, visible instance count, watchdog processes, watchdog ledgers, and
  lifecycle hold status.
- \`project_status_report.txt\`: current project gate/hold status.
- \`paid_preflight_hold_block.txt\`: proof that paid creation is blocked by the local lifecycle hold.
- \`support_followup_draft.md\`: local support draft, if present.
- \`brev_launchable_lifecycle_hold.md\`: active local paid-compute hold file, if present.

This script does not create, start, stop, or delete paid resources.
EOF

(
  cd "${OUT_DIR}"
  shasum -a 256 ./* >SHA256SUMS.txt
)

tar_path="${OUT_DIR}.tar.gz"
tar -czf "${tar_path}" -C "$(dirname "${OUT_DIR}")" "$(basename "${OUT_DIR}")"
archive_sha_file="${tar_path}.sha256"
shasum -a 256 "${tar_path}" >"${archive_sha_file}"
archive_sha256="$(awk '{print $1}' "${archive_sha_file}")"

cat <<EOF
[brev-incident] READY
evidence_dir=${OUT_DIR}
archive=${tar_path}
archive_sha256=${archive_sha256}
archive_sha256_file=${archive_sha_file}
EOF
