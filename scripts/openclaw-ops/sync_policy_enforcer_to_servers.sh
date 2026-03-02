#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

if [[ -n "${SSH_CONFIG:-}" && -f "${SSH_CONFIG}" ]]; then
  SSH_CFG="${SSH_CONFIG}"
elif [[ -f "/mnt/d/学习资料/ssh_keys/ssh_config" ]]; then
  SSH_CFG="/mnt/d/学习资料/ssh_keys/ssh_config"
elif [[ -f "D:/学习资料/ssh_keys/ssh_config" ]]; then
  SSH_CFG="D:/学习资料/ssh_keys/ssh_config"
else
  echo "[sync-policy] ssh_config not found. set SSH_CONFIG first." >&2
  exit 1
fi

if (( $# > 0 )); then
  SERVERS=("$@")
else
  SERVERS=("pm-website" "大白pm" "nofx" "coingod" "tokyo-claw" "hangqing-zhongxin")
fi

RESTART_GATEWAY="${RESTART_GATEWAY:-0}"
SSH_CONNECT_TIMEOUT="${SSH_CONNECT_TIMEOUT:-12}"
SSH_CMD_TIMEOUT="${SSH_CMD_TIMEOUT:-180}"

LOCAL_POLICY_DIR="${REPO_ROOT}/scripts/openclaw-ops/policy"
LOCAL_HOOKS_DIR="${REPO_ROOT}/hooks"
if [[ ! -d "${LOCAL_HOOKS_DIR}" && -d "${REPO_ROOT}/.claude/hardflow/hooks" ]]; then
  LOCAL_HOOKS_DIR="${REPO_ROOT}/.claude/hardflow/hooks"
fi

if [[ ! -d "${LOCAL_POLICY_DIR}" ]]; then
  echo "[sync-policy] local policy dir missing: ${LOCAL_POLICY_DIR}" >&2
  exit 1
fi
if [[ ! -d "${LOCAL_HOOKS_DIR}" ]]; then
  echo "[sync-policy] local hooks dir missing: ${LOCAL_HOOKS_DIR}" >&2
  exit 1
fi

ok_count=0
fail_count=0

SSH_OPTS=(
  -F "${SSH_CFG}"
  -o BatchMode=yes
  -o ConnectTimeout="${SSH_CONNECT_TIMEOUT}"
  -o StrictHostKeyChecking=accept-new
  -o ServerAliveInterval=15
  -o ServerAliveCountMax=2
)

ssh_run() {
  local server="$1"
  local cmd="$2"
  timeout "${SSH_CMD_TIMEOUT}" ssh "${SSH_OPTS[@]}" "${server}" "${cmd}"
}

scp_run() {
  local src="$1"
  local dst="$2"
  timeout "${SSH_CMD_TIMEOUT}" scp "${SSH_OPTS[@]}" "${src}" "${dst}"
}

for server in "${SERVERS[@]}"; do
  echo "=========="
  echo "[sync-policy] server=${server}"

  if ! ssh_run "${server}" "echo ok" >/dev/null 2>&1; then
    echo "[sync-policy] connect failed: ${server}" >&2
    fail_count=$((fail_count + 1))
    continue
  fi

  remote_home="$(ssh_run "${server}" 'printf "%s" "$HOME"')"
  remote_policy_dir="${remote_home}/.openclaw/workspace-ops-agent/ops/policy"
  remote_hooks_dir="${remote_home}/.claude/hooks"
  remote_db="${remote_home}/.openclaw/ops/task-center/task_center.db"
  remote_ops_dir="${remote_home}/.openclaw/ops"

  ssh_run "${server}" "mkdir -p '${remote_policy_dir}' '${remote_hooks_dir}' '${remote_home}/.openclaw/ops/task-center' '${remote_ops_dir}'"

  scp_run "${LOCAL_POLICY_DIR}/"*.py "${server}:${remote_policy_dir}/" >/dev/null
  scp_run "${LOCAL_POLICY_DIR}/"*.json "${server}:${remote_policy_dir}/" >/dev/null
  scp_run "${LOCAL_POLICY_DIR}/README.md" "${server}:${remote_policy_dir}/README.md" >/dev/null
  scp_run "${LOCAL_POLICY_DIR}/runtime.env.example" "${server}:${remote_policy_dir}/runtime.env.example" >/dev/null
  scp_run "${LOCAL_POLICY_DIR}/project_index_maintainer.py" "${server}:${remote_ops_dir}/project_index_maintainer.py" >/dev/null
  scp_run "${LOCAL_POLICY_DIR}/project-registry.example.json" "${server}:${remote_home}/.openclaw/ops/task-center/project-registry.example.json" >/dev/null

  for hook_name in hardflow-policy-enforcer hardflow-command-guard; do
    ssh_run "${server}" "mkdir -p '${remote_hooks_dir}/${hook_name}'"
    scp_run "${LOCAL_HOOKS_DIR}/${hook_name}/HOOK.md" "${server}:${remote_hooks_dir}/${hook_name}/HOOK.md" >/dev/null
    scp_run "${LOCAL_HOOKS_DIR}/${hook_name}/handler.ts" "${server}:${remote_hooks_dir}/${hook_name}/handler.ts" >/dev/null
  done

  ssh_run "${server}" "python3 '${remote_policy_dir}/policy_enforcer.py' --db '${remote_db}' --policy-file '${remote_policy_dir}/policy-config.json' --routing-file '${remote_policy_dir}/routing-rules.json' --pricing-file '${remote_policy_dir}/token-pricing.json' init"

  ssh_run "${server}" "openclaw config set --json hooks.internal.enabled true"
  ssh_run "${server}" "openclaw config set hooks.internal.load.extraDirs[0] '${remote_hooks_dir}'"
  ssh_run "${server}" "openclaw config set --json hooks.internal.entries.hardflow-command-guard.enabled true"
  ssh_run "${server}" "openclaw config set --json hooks.internal.entries.hardflow-policy-enforcer.enabled true"

  ssh_run "${server}" "python3 '${remote_policy_dir}/policy_enforcer.py' --db '${remote_db}' --policy-file '${remote_policy_dir}/policy-config.json' --routing-file '${remote_policy_dir}/routing-rules.json' --pricing-file '${remote_policy_dir}/token-pricing.json' validate-runtime"

  if [[ "${RESTART_GATEWAY}" == "1" ]]; then
    ssh_run "${server}" "openclaw gateway restart >/dev/null 2>&1 || true"
  fi

  ssh_run "${server}" "openclaw hooks check --json | sed -n '1,80p'" || true

  ok_count=$((ok_count + 1))
done

echo "=========="
echo "[sync-policy] done ok=${ok_count} fail=${fail_count}"
if [[ ${fail_count} -gt 0 ]]; then
  exit 2
fi
