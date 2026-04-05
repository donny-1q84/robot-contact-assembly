#!/usr/bin/env bash

RCA_DEFAULT_ENV_NAME="isaac-l40s"
RCA_DEFAULT_REMOTE_ROOT="/home/ubuntu/projects/robot-contact-assembly"
RCA_DEFAULT_REMOTE_COMPOSE_ROOT="/home/ubuntu/isaac-compose"

rca_init_remote_vars() {
  RCA_ENV_NAME="${1:-${RCA_DEFAULT_ENV_NAME}}"
  RCA_REMOTE_ROOT="${2:-${RCA_DEFAULT_REMOTE_ROOT}}"
  RCA_REMOTE_COMPOSE_ROOT="${3:-${RCA_DEFAULT_REMOTE_COMPOSE_ROOT}}"
  RCA_REMOTE_REPO_DIR="${RCA_REMOTE_ROOT}/repo/robot-contact-assembly"
  RCA_REMOTE_OVERRIDE_FILE="${RCA_REMOTE_REPO_DIR}/docker/isaac-compose.project.yml"
  RCA_COMPOSE_BASE="docker compose -p isim -f ${RCA_REMOTE_COMPOSE_ROOT}/tools/docker/docker-compose.yml -f ${RCA_REMOTE_COMPOSE_ROOT}/tools/docker/docker-compose.override.yml -f ${RCA_REMOTE_OVERRIDE_FILE}"
}

rca_brev_exec() {
  /Users/Shenghan/bin/brev exec "${RCA_ENV_NAME}" "$@"
}

rca_remote_host_exec() {
  local host_cmd="$1"
  local encoded_cmd

  encoded_cmd="$(printf '%s' "${host_cmd}" | base64 | tr -d '\n')"
  rca_brev_exec "bash -lc 'printf %s ${encoded_cmd} | base64 -d | bash'"
}

rca_remote_container_exec() {
  local container_cmd="$1"
  local quoted_container_cmd
  local host_cmd

  quoted_container_cmd="$(printf '%q' "${container_cmd}")"
  printf -v host_cmd '%s\n%s\n%s\n' \
    'set -euo pipefail' \
    "cd \"${RCA_REMOTE_COMPOSE_ROOT}\"" \
    "${RCA_COMPOSE_BASE} exec -T isaac-sim bash -lc ${quoted_container_cmd}"
  rca_remote_host_exec "${host_cmd}"
}

rca_remote_repo_exec() {
  local repo_cmd="$1"
  rca_remote_container_exec "cd /workspace/robot-contact-assembly && ${repo_cmd}"
}
