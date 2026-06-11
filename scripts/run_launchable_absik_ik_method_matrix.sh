#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="${RCA_LAUNCHABLE_REPO_DIR:-/workspace/robot-contact-assembly}"
ARTIFACT_ROOT="${RCA_LAUNCHABLE_ARTIFACT_ROOT:-${REPO_DIR}/artifacts}"
RUN_ID="$(date -u +"%Y-%m-%dT%H-%M-%SZ")"
MATRIX_ROOT="${ARTIFACT_ROOT}/evaluations/absik_ik_method_matrix/${RUN_ID}"
CASE_SPECS="${RCA_LAUNCHABLE_ABS_IK_METHOD_CASES:-dls:dls;pinv:pinv;svd:svd;trans:trans}"

mkdir -p "${MATRIX_ROOT}"

echo "[launchable-ik-method-matrix] repo=${REPO_DIR}"
echo "[launchable-ik-method-matrix] matrix_root=${MATRIX_ROOT}"
echo "[launchable-ik-method-matrix] case_specs=${CASE_SPECS}"

IFS=";" read -r -a cases <<< "${CASE_SPECS}"
for case_spec in "${cases[@]}"; do
  [[ -n "${case_spec}" ]] || continue
  case_name="${case_spec%%:*}"
  ik_method=""
  if [[ "${case_spec}" == *":"* ]]; then
    ik_method="${case_spec#*:}"
  fi
  if [[ -z "${case_name}" || -z "${ik_method}" ]]; then
    echo "[launchable-ik-method-matrix] invalid case spec: ${case_spec}" >&2
    exit 2
  fi

  case_root="${MATRIX_ROOT}/${case_name}"
  mkdir -p "${case_root}"
  echo "[launchable-ik-method-matrix] starting case=${case_name} ik_method=${ik_method}"

  export RCA_LAUNCHABLE_ARTIFACT_ROOT="${case_root}"
  export RCA_LAUNCHABLE_ABS_CONTROL_MODE="${RCA_LAUNCHABLE_ABS_CONTROL_MODE:-target}"
  export RCA_LAUNCHABLE_MDP_ABS_IK_METHOD="${ik_method}"
  export RCA_LAUNCHABLE_SCRIPTED_STEPS="${RCA_LAUNCHABLE_SCRIPTED_STEPS:-350}"
  export RCA_LAUNCHABLE_TIMEOUT_SECONDS="${RCA_LAUNCHABLE_TIMEOUT_SECONDS:-900}"
  export RCA_LAUNCHABLE_FAIL_CLOSED_EXIT_ZERO="${RCA_LAUNCHABLE_FAIL_CLOSED_EXIT_ZERO:-1}"
  unset RCA_LAUNCHABLE_TARGET_ACTION_POS_OFFSET

  "${REPO_DIR}/scripts/run_launchable_phase2_absik_handoff_probe.sh" 2>&1 | tee "${case_root}/matrix_case.log"

  probe_summary="$(find "${case_root}" -path '*_absik-handoff-probe/probe_summary.json' -print | sort | tail -n 1)"
  tracking_analysis="$(find "${case_root}" -path '*_absik-handoff-probe/tracking_analysis.json' -print | sort | tail -n 1)"
  {
    echo "case=${case_name}"
    echo "ik_method=${ik_method}"
    echo "probe_summary=${probe_summary:-<missing>}"
    echo "tracking_analysis=${tracking_analysis:-<missing>}"
  } | tee "${case_root}/case_index.txt"
done

find "${MATRIX_ROOT}" -name case_index.txt -print | sort | xargs -r cat > "${MATRIX_ROOT}/matrix_index.txt"
echo "[launchable-ik-method-matrix] wrote ${MATRIX_ROOT}/matrix_index.txt"
