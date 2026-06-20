#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="${RCA_LAUNCHABLE_REPO_DIR:-/workspace/robot-contact-assembly}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
"${SCRIPT_DIR}/launchable_post_contact_gate.sh" "${REPO_DIR}"
ARTIFACT_ROOT="${RCA_LAUNCHABLE_ARTIFACT_ROOT:-${REPO_DIR}/artifacts}"
RUN_ID="$(date -u +"%Y-%m-%dT%H-%M-%SZ")"
MATRIX_ROOT="${ARTIFACT_ROOT}/evaluations/jointpos_nullspace_matrix/${RUN_ID}"

DEFAULT_CASE_SPECS="baseline:0.000:0.250:0.030:0.050;soft:0.035:0.250:0.030:0.050;strong:0.070:0.300:0.040:0.075"
CASE_SPECS="${RCA_LAUNCHABLE_JOINTPOS_NULLSPACE_CASES:-${DEFAULT_CASE_SPECS}}"

mkdir -p "${MATRIX_ROOT}"

echo "[launchable-jointpos-nullspace-matrix] repo=${REPO_DIR}"
echo "[launchable-jointpos-nullspace-matrix] matrix_root=${MATRIX_ROOT}"
echo "[launchable-jointpos-nullspace-matrix] case_specs=${CASE_SPECS}"

IFS=";" read -r -a cases <<< "${CASE_SPECS}"
for case_spec in "${cases[@]}"; do
  [[ -n "${case_spec}" ]] || continue
  IFS=":" read -r case_name gain activation_margin step damping extra <<< "${case_spec}"
  if [[ -z "${case_name}" || -z "${gain}" || -z "${activation_margin}" || -z "${step}" || -z "${damping}" || -n "${extra:-}" ]]; then
    echo "[launchable-jointpos-nullspace-matrix] invalid case spec: ${case_spec}" >&2
    echo "expected name:gain:activation_margin:step:damping" >&2
    exit 2
  fi
  if [[ ! "${case_name}" =~ ^[A-Za-z0-9_.-]+$ ]]; then
    echo "[launchable-jointpos-nullspace-matrix] invalid case name: ${case_name}" >&2
    exit 2
  fi

  case_root="${MATRIX_ROOT}/${case_name}"
  mkdir -p "${case_root}"
  echo "[launchable-jointpos-nullspace-matrix] starting case=${case_name} gain=${gain} activation_margin=${activation_margin} step=${step} damping=${damping}"

  export RCA_LAUNCHABLE_ARTIFACT_ROOT="${case_root}"
  export RCA_LAUNCHABLE_SCRIPTED_STEPS="${RCA_LAUNCHABLE_SCRIPTED_STEPS:-700}"
  export RCA_LAUNCHABLE_TIMEOUT_SECONDS="${RCA_LAUNCHABLE_TIMEOUT_SECONDS:-1200}"
  export RCA_LAUNCHABLE_FAIL_CLOSED_EXIT_ZERO="${RCA_LAUNCHABLE_FAIL_CLOSED_EXIT_ZERO:-1}"
  export RCA_LAUNCHABLE_JOINT_LIMIT_NULLSPACE_GAIN="${gain}"
  export RCA_LAUNCHABLE_JOINT_LIMIT_NULLSPACE_ACTIVATION_MARGIN="${activation_margin}"
  export RCA_LAUNCHABLE_JOINT_LIMIT_NULLSPACE_STEP="${step}"
  export RCA_LAUNCHABLE_JOINT_LIMIT_NULLSPACE_DAMPING="${damping}"

  "${REPO_DIR}/scripts/run_launchable_phase2_jointpos_nullspace_probe.sh" 2>&1 | tee "${case_root}/matrix_case.log"

  probe_summary="$(find "${case_root}" -path '*_jointpos-nullspace-probe/probe_summary.json' -print | sort | tail -n 1)"
  tracking_analysis="$(find "${case_root}" -path '*_jointpos-nullspace-probe/tracking_analysis.json' -print | sort | tail -n 1)"
  {
    echo "case=${case_name}"
    echo "joint_limit_nullspace_gain=${gain}"
    echo "joint_limit_nullspace_activation_margin=${activation_margin}"
    echo "joint_limit_nullspace_step=${step}"
    echo "joint_limit_nullspace_damping=${damping}"
    echo "probe_summary=${probe_summary:-<missing>}"
    echo "tracking_analysis=${tracking_analysis:-<missing>}"
  } | tee "${case_root}/case_index.txt"
done

find "${MATRIX_ROOT}" -name case_index.txt -print | sort | xargs -r cat > "${MATRIX_ROOT}/matrix_index.txt"
echo "[launchable-jointpos-nullspace-matrix] wrote ${MATRIX_ROOT}/matrix_index.txt"
