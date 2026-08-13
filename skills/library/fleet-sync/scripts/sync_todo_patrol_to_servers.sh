#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  bash skills/library/fleet-sync/scripts/sync_todo_patrol_to_servers.sh HOST_A [HOST_B ...]

Environment:
  SSH_CONFIG=~/.ssh/config
  HARDFLOW_FLEET_SERVERS=HOST_A,HOST_B
  HARDFLOW_REMOTE_WORKFLOW_REPO=~/workflow-infra
  HARDFLOW_REMOTE_RUNTIME_HOME=~/.openclaw
  HARDFLOW_NOTIFICATION_CHANNEL=<channel>       # optional
  HARDFLOW_NOTIFICATION_TARGET=<target>         # optional
  HARDFLOW_TIMEZONE=Asia/Shanghai               # optional
  DRY_RUN=1                                     # render without writing remotely
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

SSH_CFG="${SSH_CONFIG:-${HOME}/.ssh/config}"
if [[ ! -f "${SSH_CFG}" ]]; then
  echo "[sync] ssh_config not found: ${SSH_CFG}" >&2
  exit 1
fi

if [[ "$#" -gt 0 ]]; then
  SERVERS=("$@")
elif [[ -n "${HARDFLOW_FLEET_SERVERS:-}" ]]; then
  IFS=',' read -r -a SERVERS <<< "${HARDFLOW_FLEET_SERVERS}"
else
  echo "[sync] provide hosts as arguments or HARDFLOW_FLEET_SERVERS" >&2
  exit 2
fi

quote_command() {
  local result="" item quoted
  for item in "$@"; do
    printf -v quoted '%q' "${item}"
    result+="${result:+ }${quoted}"
  done
  printf '%s' "${result}"
}

ok_count=0
fail_count=0
for server in "${SERVERS[@]}"; do
  server="${server//[[:space:]]/}"
  [[ -n "${server}" ]] || continue
  echo "[sync] host=${server}"

  if ! remote_home="$(ssh -F "${SSH_CFG}" -o BatchMode=yes -o ConnectTimeout=12 "${server}" 'printf "%s" "$HOME"')"; then
    echo "[sync] connect failed: ${server}" >&2
    fail_count=$((fail_count + 1))
    continue
  fi

  remote_repo="${HARDFLOW_REMOTE_WORKFLOW_REPO:-${remote_home}/workflow-infra}"
  remote_runtime="${HARDFLOW_REMOTE_RUNTIME_HOME:-${remote_home}/.openclaw}"
  args=(
    python3 "${remote_repo}/setup.py"
    --runtime-home "${remote_runtime}"
    --repo-root "${remote_repo}"
    --job-name 'TODO 巡检（15分钟）'
    --emit-json
  )
  [[ -n "${HARDFLOW_NOTIFICATION_CHANNEL:-}" ]] && args+=(--notification-channel "${HARDFLOW_NOTIFICATION_CHANNEL}")
  [[ -n "${HARDFLOW_NOTIFICATION_TARGET:-}" ]] && args+=(--notification-target "${HARDFLOW_NOTIFICATION_TARGET}")
  [[ -n "${HARDFLOW_TIMEZONE:-}" ]] && args+=(--timezone "${HARDFLOW_TIMEZONE}")
  [[ "${DRY_RUN:-0}" == "1" ]] && args+=(--dry-run)

  command="$(quote_command "${args[@]}")"
  if ssh -F "${SSH_CFG}" -o BatchMode=yes "${server}" "test -f $(printf '%q' "${remote_repo}/setup.py") && ${command}"; then
    ok_count=$((ok_count + 1))
  else
    echo "[sync] install failed: ${server}" >&2
    fail_count=$((fail_count + 1))
  fi
done

echo "[sync] done ok=${ok_count} fail=${fail_count}"
[[ "${fail_count}" -eq 0 ]]
