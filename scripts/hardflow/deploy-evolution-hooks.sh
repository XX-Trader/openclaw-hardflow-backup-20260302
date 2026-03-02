#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
LOCAL_HOOKS_DIR="${REPO_ROOT}/.claude/hardflow/hooks"
LOCAL_REMOTE_ENABLE="${REPO_ROOT}/scripts/hardflow/remote-enable-evolution-hooks.py"
LOCAL_MAINTAIN_SCRIPT="${REPO_ROOT}/scripts/hardflow/experience-maintain.mjs"
LOCAL_MAINTAIN_CRON="${REPO_ROOT}/scripts/hardflow/experience-maintain-cron.sh"
LOCAL_PROCESS_OPTIMIZE_SCRIPT="${REPO_ROOT}/scripts/hardflow/process-optimize.mjs"
LOCAL_PROCESS_OPTIMIZE_CRON="${REPO_ROOT}/scripts/hardflow/process-optimize-cron.sh"
LOCAL_INSTALL_CRON_SCRIPT="${REPO_ROOT}/scripts/hardflow/remote-install-maintenance-cron.sh"

SSH_CONFIG=""
for candidate in \
  "/d/瀛︿範璧勬枡/ssh_keys/ssh_config" \
  "/mnt/d/瀛︿範璧勬枡/ssh_keys/ssh_config" \
  "D:/瀛︿範璧勬枡/ssh_keys/ssh_config"
do
  if [[ -f "${candidate}" ]]; then
    SSH_CONFIG="${candidate}"
    break
  fi
done

if [[ -z "${SSH_CONFIG}" ]]; then
  echo "[deploy] cannot find ssh_config (checked D:/, /d/, /mnt/d)" >&2
  exit 1
fi

SSH_BIN="ssh"
SCP_BIN="scp"

DEFAULT_TARGET_ALIASES=(
  "pm-website"
  "澶х櫧pm"
  "nofx"
  "coingod"
  "hangqing-zhongxin"
  "tokyo-claw"
)

TARGET_ALIASES=("${DEFAULT_TARGET_ALIASES[@]}")
if (( $# > 0 )); then
  TARGET_ALIASES=("$@")
fi

for file in \
  "${LOCAL_REMOTE_ENABLE}" \
  "${LOCAL_MAINTAIN_SCRIPT}" \
  "${LOCAL_MAINTAIN_CRON}" \
  "${LOCAL_PROCESS_OPTIMIZE_SCRIPT}" \
  "${LOCAL_PROCESS_OPTIMIZE_CRON}" \
  "${LOCAL_INSTALL_CRON_SCRIPT}"
do
  if [[ ! -f "${file}" ]]; then
    echo "[deploy] required file not found: ${file}" >&2
    exit 1
  fi
done
if [[ ! -d "${LOCAL_HOOKS_DIR}" ]]; then
  echo "[deploy] hooks dir not found: ${LOCAL_HOOKS_DIR}" >&2
  exit 1
fi

deploy_one() {
  local alias="$1"
  echo "[deploy] === ${alias} ==="

  # 1) Upload hooks and tools.
  "${SSH_BIN}" -F "${SSH_CONFIG}" "${alias}" "rm -rf ~/.openclaw/hardflow-hooks && mkdir -p ~/.openclaw/hardflow-hooks ~/.openclaw/hardflow-hooks/tools ~/.openclaw/logs"
  "${SCP_BIN}" -F "${SSH_CONFIG}" -r "${LOCAL_HOOKS_DIR}"/* "${alias}:~/.openclaw/hardflow-hooks/"
  "${SCP_BIN}" -F "${SSH_CONFIG}" "${LOCAL_REMOTE_ENABLE}" "${alias}:~/.openclaw/hardflow-hooks/tools/remote-enable-evolution-hooks.py"
  "${SCP_BIN}" -F "${SSH_CONFIG}" "${LOCAL_MAINTAIN_SCRIPT}" "${alias}:~/.openclaw/hardflow-hooks/tools/experience-maintain.mjs"
  "${SCP_BIN}" -F "${SSH_CONFIG}" "${LOCAL_MAINTAIN_CRON}" "${alias}:~/.openclaw/hardflow-hooks/tools/experience-maintain-cron.sh"
  "${SCP_BIN}" -F "${SSH_CONFIG}" "${LOCAL_PROCESS_OPTIMIZE_SCRIPT}" "${alias}:~/.openclaw/hardflow-hooks/tools/process-optimize.mjs"
  "${SCP_BIN}" -F "${SSH_CONFIG}" "${LOCAL_PROCESS_OPTIMIZE_CRON}" "${alias}:~/.openclaw/hardflow-hooks/tools/process-optimize-cron.sh"
  "${SCP_BIN}" -F "${SSH_CONFIG}" "${LOCAL_INSTALL_CRON_SCRIPT}" "${alias}:~/.openclaw/hardflow-hooks/tools/remote-install-maintenance-cron.sh"
  "${SSH_BIN}" -F "${SSH_CONFIG}" "${alias}" "chmod +x ~/.openclaw/hardflow-hooks/tools/experience-maintain-cron.sh ~/.openclaw/hardflow-hooks/tools/process-optimize-cron.sh ~/.openclaw/hardflow-hooks/tools/remote-install-maintenance-cron.sh"

  # 2) Enable hooks and bootstrap memory files.
  "${SSH_BIN}" -F "${SSH_CONFIG}" "${alias}" "python3 ~/.openclaw/hardflow-hooks/tools/remote-enable-evolution-hooks.py"

  # 3) Install daily/weekly/monthly cron maintenance jobs.
  "${SSH_BIN}" -F "${SSH_CONFIG}" "${alias}" "bash ~/.openclaw/hardflow-hooks/tools/remote-install-maintenance-cron.sh"

  # 4) Run one immediate daily maintenance pass.
  "${SSH_BIN}" -F "${SSH_CONFIG}" "${alias}" "bash ~/.openclaw/hardflow-hooks/tools/experience-maintain-cron.sh daily || true"
  "${SSH_BIN}" -F "${SSH_CONFIG}" "${alias}" "bash ~/.openclaw/hardflow-hooks/tools/process-optimize-cron.sh daily || true"

  # 5) Verify hooks and memory status.
  "${SSH_BIN}" -F "${SSH_CONFIG}" "${alias}" "openclaw hooks check || true"
  "${SSH_BIN}" -F "${SSH_CONFIG}" "${alias}" "openclaw hooks list | sed -n '1,200p' || true"
  "${SSH_BIN}" -F "${SSH_CONFIG}" "${alias}" "openclaw gateway restart || true"
  "${SSH_BIN}" -F "${SSH_CONFIG}" "${alias}" "openclaw gateway health || true"
  "${SSH_BIN}" -F "${SSH_CONFIG}" "${alias}" "openclaw memory status --json | sed -n '1,120p' || true"
}

main() {
  echo "[deploy] targets: ${TARGET_ALIASES[*]}"
  for alias in "${TARGET_ALIASES[@]}"; do
    deploy_one "${alias}"
  done
  echo "[deploy] completed for ${#TARGET_ALIASES[@]} servers"
}

main "$@"
