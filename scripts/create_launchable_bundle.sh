#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
RUN_ID="$(date -u +"%Y-%m-%dT%H-%M-%SZ")"
OUT_DIR="${RCA_LAUNCHABLE_BUNDLE_DIR:-${REPO_ROOT}/artifacts/launchable}"
OUT_PATH="${1:-${OUT_DIR}/robot-contact-assembly-launchable-${RUN_ID}.tar.gz}"
PRELOAD_TRACE="${RCA_LAUNCHABLE_PRELOAD_TRACE_LOCAL:-${REPO_ROOT}/artifacts/preload_traces/2026-05-17T23-32-18Z_seed_42_trace.json}"
TMP_DIR="$(mktemp -d)"
SOURCE_MANIFEST="${TMP_DIR}/robot-contact-assembly/.rca_launchable_source_manifest.txt"

cleanup() {
  rm -rf "${TMP_DIR}"
}
trap cleanup EXIT

mkdir -p "${OUT_DIR}" "${TMP_DIR}/robot-contact-assembly" "${TMP_DIR}/artifacts/preload_traces"

rsync -a --delete \
  --exclude '.claude/' \
  --exclude '.git/' \
  --exclude '.env' \
  --exclude '.env.*' \
  --exclude 'artifacts/' \
  --exclude 'logs/' \
  --exclude 'videos/' \
  --exclude 'checkpoints/' \
  --exclude 'tmp/' \
  --exclude '*.egg-info/' \
  --exclude '__pycache__/' \
  --exclude '*.pyc' \
  --exclude '*.pem' \
  --exclude '*.key' \
  --exclude '*credential*' \
  --exclude '*secret*' \
  --exclude '*private*' \
  --exclude '.DS_Store' \
  "${REPO_ROOT}/" "${TMP_DIR}/robot-contact-assembly/"

git_head="$(git -C "${REPO_ROOT}" rev-parse HEAD 2>/dev/null || echo unknown)"
git_branch="$(git -C "${REPO_ROOT}" branch --show-current 2>/dev/null || echo unknown)"
git_status="$(git -C "${REPO_ROOT}" status --short 2>/dev/null || true)"
source_payload_sha256="$(python3 "${SCRIPT_DIR}/source_payload_fingerprint.py" "${TMP_DIR}/robot-contact-assembly")"
source_payload_scope="$(python3 "${SCRIPT_DIR}/source_payload_fingerprint.py" --scope)"
if [[ -n "${git_status}" ]]; then
  git_dirty=1
else
  git_dirty=0
fi

{
  echo "created_utc=${RUN_ID}"
  echo "source_repo=${REPO_ROOT}"
  echo "git_head=${git_head}"
  echo "git_branch=${git_branch:-unknown}"
  echo "git_dirty=${git_dirty}"
  echo "source_payload_scope=${source_payload_scope}"
  echo "source_payload_sha256=${source_payload_sha256}"
  echo "git_status_short_begin"
  if [[ -n "${git_status}" ]]; then
    printf '%s\n' "${git_status}"
  else
    echo "(clean)"
  fi
  echo "git_status_short_end"
} > "${SOURCE_MANIFEST}"

if [[ -s "${PRELOAD_TRACE}" ]]; then
  cp "${PRELOAD_TRACE}" "${TMP_DIR}/artifacts/preload_traces/$(basename "${PRELOAD_TRACE}")"
else
  echo "[launchable-bundle] warning: preload trace missing, bundle will not include it: ${PRELOAD_TRACE}" >&2
fi

COPYFILE_DISABLE=1 tar -C "${TMP_DIR}" --no-xattrs --exclude='._*' -czf "${OUT_PATH}" robot-contact-assembly artifacts

echo "[launchable-bundle] wrote ${OUT_PATH}"
echo "[launchable-bundle] upload/extract inside Launchable with:"
echo "  tar -xzf $(basename "${OUT_PATH}") -C /workspace"
