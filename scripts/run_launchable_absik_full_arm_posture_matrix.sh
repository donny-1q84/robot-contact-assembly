#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="${RCA_LAUNCHABLE_REPO_DIR:-/workspace/robot-contact-assembly}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
"${SCRIPT_DIR}/launchable_post_contact_gate.sh" "${REPO_DIR}"
ARTIFACT_ROOT="${RCA_LAUNCHABLE_ARTIFACT_ROOT:-${REPO_DIR}/artifacts}"
RUN_ID="$(date -u +"%Y-%m-%dT%H-%M-%SZ")"
MATRIX_ROOT="${ARTIFACT_ROOT}/evaluations/absik_full_arm_posture_matrix/${RUN_ID}"

DEFAULT_CASE_SPECS="baseline:;ready_mid:panda_joint1=0.0,panda_joint2=-0.569,panda_joint3=0.0,panda_joint4=-2.810,panda_joint5=0.0,panda_joint6=3.037,panda_joint7=0.741;elbow_open:panda_joint1=0.0,panda_joint2=-0.35,panda_joint3=0.0,panda_joint4=-2.20,panda_joint5=0.0,panda_joint6=2.20,panda_joint7=0.80;yaw_pos:panda_joint1=0.35,panda_joint2=-0.55,panda_joint3=0.35,panda_joint4=-2.30,panda_joint5=0.20,panda_joint6=2.20,panda_joint7=1.00;yaw_neg:panda_joint1=-0.35,panda_joint2=-0.55,panda_joint3=-0.35,panda_joint4=-2.30,panda_joint5=-0.20,panda_joint6=2.20,panda_joint7=1.00"
CASE_SPECS="${RCA_LAUNCHABLE_ABS_IK_POSTURE_CASES:-${DEFAULT_CASE_SPECS}}"

mkdir -p "${MATRIX_ROOT}"

echo "[launchable-full-arm-posture-matrix] repo=${REPO_DIR}"
echo "[launchable-full-arm-posture-matrix] matrix_root=${MATRIX_ROOT}"
echo "[launchable-full-arm-posture-matrix] case_specs=${CASE_SPECS}"

IFS=";" read -r -a cases <<< "${CASE_SPECS}"
for case_spec in "${cases[@]}"; do
  [[ -n "${case_spec}" ]] || continue
  case_name="${case_spec%%:*}"
  initial_joint_pos=""
  if [[ "${case_spec}" == *":"* ]]; then
    initial_joint_pos="${case_spec#*:}"
  fi
  if [[ -z "${case_name}" ]]; then
    echo "[launchable-full-arm-posture-matrix] invalid case spec: ${case_spec}" >&2
    exit 2
  fi
  if [[ ! "${case_name}" =~ ^[A-Za-z0-9_.-]+$ ]]; then
    echo "[launchable-full-arm-posture-matrix] invalid case name: ${case_name}" >&2
    exit 2
  fi

  case_root="${MATRIX_ROOT}/${case_name}"
  mkdir -p "${case_root}"
  echo "[launchable-full-arm-posture-matrix] starting case=${case_name} initial_joint_pos=${initial_joint_pos:-<default>}"

  export RCA_LAUNCHABLE_ARTIFACT_ROOT="${case_root}"
  export RCA_LAUNCHABLE_ABS_CONTROL_MODE="${RCA_LAUNCHABLE_ABS_CONTROL_MODE:-target}"
  export RCA_LAUNCHABLE_SCRIPTED_STEPS="${RCA_LAUNCHABLE_SCRIPTED_STEPS:-350}"
  export RCA_LAUNCHABLE_TIMEOUT_SECONDS="${RCA_LAUNCHABLE_TIMEOUT_SECONDS:-900}"
  export RCA_LAUNCHABLE_FAIL_CLOSED_EXIT_ZERO="${RCA_LAUNCHABLE_FAIL_CLOSED_EXIT_ZERO:-1}"
  unset RCA_LAUNCHABLE_MDP_ABS_IK_METHOD
  unset RCA_LAUNCHABLE_TARGET_ACTION_POS_OFFSET

  if [[ -n "${initial_joint_pos}" ]]; then
    export RCA_LAUNCHABLE_INITIAL_JOINT_POS="${initial_joint_pos}"
  else
    unset RCA_LAUNCHABLE_INITIAL_JOINT_POS
  fi

  "${REPO_DIR}/scripts/run_launchable_phase2_absik_handoff_probe.sh" 2>&1 | tee "${case_root}/matrix_case.log"

  probe_summary="$(find "${case_root}" -path '*_absik-handoff-probe/probe_summary.json' -print | sort | tail -n 1)"
  tracking_analysis="$(find "${case_root}" -path '*_absik-handoff-probe/tracking_analysis.json' -print | sort | tail -n 1)"
  {
    echo "case=${case_name}"
    echo "initial_joint_pos=${initial_joint_pos:-<default>}"
    echo "probe_summary=${probe_summary:-<missing>}"
    echo "tracking_analysis=${tracking_analysis:-<missing>}"
  } | tee "${case_root}/case_index.txt"
done

find "${MATRIX_ROOT}" -name case_index.txt -print | sort | xargs -r cat > "${MATRIX_ROOT}/matrix_index.txt"
echo "[launchable-full-arm-posture-matrix] wrote ${MATRIX_ROOT}/matrix_index.txt"
