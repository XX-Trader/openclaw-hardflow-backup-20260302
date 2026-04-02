#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

detect_ssh_config() {
  local candidates=(
    "${SSH_CONFIG:-}"
    "/d/ssh_keys/ssh_config"
    "/mnt/d/ssh_keys/ssh_config"
    "D:/ssh_keys/ssh_config"
  )
  local item
  for item in "${candidates[@]}"; do
    if [[ -n "${item}" && -f "${item}" ]]; then
      echo "${item}"
      return 0
    fi
  done
  return 1
}

usage() {
  cat <<'EOF'
Usage:
  bash scripts/openclaw-ops/sync_todo_patrol_to_servers.sh [server1 server2 ...]

Env:
  SSH_CONFIG=/path/to/ssh_config
  TODO_PATROL_DELIVERY_TO=<group_or_user_id>    # optional, auto-infer by default
  TODO_PATROL_EVERY_MS=900000                   # optional
  DRY_RUN=1                                     # optional

Default servers:
  pm-website 大白pm nofx coingod tokyo-claw
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

SSH_CFG="$(detect_ssh_config || true)"
if [[ -z "${SSH_CFG}" ]]; then
  echo "[sync] ssh_config not found. set SSH_CONFIG first." >&2
  exit 1
fi

EVERY_MS="${TODO_PATROL_EVERY_MS:-900000}"
DELIVERY_TO="${TODO_PATROL_DELIVERY_TO:-}"
DRY_RUN="${DRY_RUN:-0}"

if [[ "$#" -gt 0 ]]; then
  SERVERS=("$@")
else
  SERVERS=("pm-website" "大白pm" "nofx" "coingod" "tokyo-claw")
fi

LOCAL_PATROL="${SCRIPT_DIR}/todo_patrol.py"
LOCAL_INSTALLER="${SCRIPT_DIR}/install_todo_patrol_job.py"
if [[ ! -f "${LOCAL_PATROL}" || ! -f "${LOCAL_INSTALLER}" ]]; then
  echo "[sync] missing local files in ${SCRIPT_DIR}" >&2
  exit 1
fi

ok_count=0
fail_count=0

for server in "${SERVERS[@]}"; do
  echo "=========="
  echo "[sync] server=${server}"

  if ! ssh -F "${SSH_CFG}" "${server}" "echo ok" >/dev/null 2>&1; then
    echo "[sync] connect failed: ${server}" >&2
    fail_count=$((fail_count + 1))
    continue
  fi

  remote_home="$(ssh -F "${SSH_CFG}" "${server}" 'printf "%s" "$HOME"')"
  remote_ops_root="${remote_home}/.openclaw/workspace-ops-agent"
  remote_ops_dir="${remote_ops_root}/ops"
  remote_patrol="${remote_ops_dir}/todo_patrol.py"
  remote_installer="${remote_ops_dir}/install_todo_patrol_job.py"

  echo "[sync] remote_home=${remote_home}"
  echo "[sync] remote_ops_dir=${remote_ops_dir}"

  if [[ "${DRY_RUN}" == "1" ]]; then
    echo "[sync] DRY_RUN=1 skip upload/install"
    ok_count=$((ok_count + 1))
    continue
  fi

  ssh -F "${SSH_CFG}" "${server}" "mkdir -p '${remote_ops_dir}' '${remote_home}/.openclaw/cron' '${remote_ops_root}/logs'"
  scp -F "${SSH_CFG}" "${LOCAL_PATROL}" "${server}:${remote_patrol}" >/dev/null
  scp -F "${SSH_CFG}" "${LOCAL_INSTALLER}" "${server}:${remote_installer}" >/dev/null

  install_cmd="python3 '${remote_installer}' --ops-script '${remote_patrol}' --every-ms ${EVERY_MS}"
  if [[ -n "${DELIVERY_TO}" ]]; then
    install_cmd="${install_cmd} --to '${DELIVERY_TO}'"
  fi

  if ! ssh -F "${SSH_CFG}" "${server}" "chmod 755 '${remote_patrol}' '${remote_installer}' && ${install_cmd}"; then
    echo "[sync] install failed: ${server}" >&2
    fail_count=$((fail_count + 1))
    continue
  fi

  echo "[sync] smoke test --dry-run"
  ssh -F "${SSH_CFG}" "${server}" "python3 '${remote_patrol}' --dry-run --task sync-smoke | sed -n '1,24p'" || true

  ok_count=$((ok_count + 1))
done

echo "=========="
echo "[sync] done ok=${ok_count} fail=${fail_count}"
if [[ "${fail_count}" -gt 0 ]]; then
  exit 2
fi
