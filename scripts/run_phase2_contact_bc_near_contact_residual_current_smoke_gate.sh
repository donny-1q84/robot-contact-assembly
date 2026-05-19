#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

export RCA_GATE_INSTANCE_NAME="${RCA_GATE_INSTANCE_NAME:-isaac-phase2-contact-bc-near-contact-residual-l4}"
export RCA_BC_LOCAL_DATASET="${RCA_BC_LOCAL_DATASET:-${REPO_ROOT}/artifacts/datasets/phase2_contact_bc_near_contact_residual_current/phase2_contact_bc_near_contact_residual_current_dataset.jsonl}"
export RCA_BC_REMOTE_DATASET="${RCA_BC_REMOTE_DATASET:-/workspace/artifacts/datasets/phase2_contact_bc_near_contact_residual_current/phase2_contact_bc_near_contact_residual_current_dataset.jsonl}"
export RCA_BC_CHECKPOINT="${RCA_BC_CHECKPOINT:-/workspace/artifacts/policies/phase2_contact_bc_near_contact_residual_current/bc_mlp.pt}"

if [[ ! -s "${RCA_BC_LOCAL_DATASET}" ]]; then
  echo "[near-contact-residual-gate] missing dataset: ${RCA_BC_LOCAL_DATASET}" >&2
  echo "[near-contact-residual-gate] generate it with:" >&2
  echo "  python3 scripts/extract_contact_demo_dataset.py --since 2026-05-17T00-00-00Z --task-contains JointPos --max-lateral 0.015 --max-axial 0.060 --max-rot 0.35 --min-contact 0.2 --action-mode residual-current --output artifacts/datasets/phase2_contact_bc_near_contact_residual_current/phase2_contact_bc_near_contact_residual_current_dataset.jsonl" >&2
  exit 2
fi

exec "${SCRIPT_DIR}/run_phase2_contact_bc_best_window_smoke_gate.sh"
