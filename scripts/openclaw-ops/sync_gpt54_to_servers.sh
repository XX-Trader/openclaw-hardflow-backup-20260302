#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

SSH_BIN="${SSH_BIN:-}"
SCP_BIN="${SCP_BIN:-}"
if [[ -z "${SSH_BIN}" ]]; then
  if command -v ssh.exe >/dev/null 2>&1; then
    SSH_BIN="ssh.exe"
  else
    SSH_BIN="ssh"
  fi
fi
if [[ -z "${SCP_BIN}" ]]; then
  if command -v scp.exe >/dev/null 2>&1; then
    SCP_BIN="scp.exe"
  else
    SCP_BIN="scp"
  fi
fi

USE_WINDOWS_OPENSSH=0
if [[ "${SSH_BIN}" == *".exe" || "${SCP_BIN}" == *".exe" ]]; then
  USE_WINDOWS_OPENSSH=1
fi

if [[ -n "${SSH_CONFIG:-}" ]]; then
  SSH_CFG="${SSH_CONFIG}"
elif [[ -f "/d/ssh_keys/ssh_config" ]]; then
  if [[ "${USE_WINDOWS_OPENSSH}" == "1" ]]; then
    SSH_CFG="D:/ssh_keys/ssh_config"
  else
    SSH_CFG="/d/ssh_keys/ssh_config"
  fi
elif [[ -f "/mnt/d/ssh_keys/ssh_config" ]]; then
  if [[ "${USE_WINDOWS_OPENSSH}" == "1" ]]; then
    SSH_CFG="D:/ssh_keys/ssh_config"
  else
    SSH_CFG="/mnt/d/ssh_keys/ssh_config"
  fi
elif [[ -f "D:/ssh_keys/ssh_config" ]]; then
  SSH_CFG="D:/ssh_keys/ssh_config"
else
  echo "[sync-gpt54] ssh_config not found. set SSH_CONFIG first." >&2
  exit 1
fi

if (( $# > 0 )); then
  SERVERS=("$@")
else
  SERVERS=("pm-website" "大白pm" "nofx" "coingod" "tokyo-claw")
fi

DRY_RUN="${DRY_RUN:-0}"
RESTART_GATEWAY="${RESTART_GATEWAY:-1}"
SSH_CONNECT_TIMEOUT="${SSH_CONNECT_TIMEOUT:-12}"
SSH_CMD_TIMEOUT="${SSH_CMD_TIMEOUT:-180}"

MODEL_AGENTS=(
  "agent-factory"
  "backend-dev"
  "coordinator"
  "deployer"
  "doc-writer"
  "frontend-dev"
  "main"
  "ops-agent"
  "project-agent"
  "reviewer"
  "tester"
)

OPS_FILES=(
  "scripts/openclaw-ops/model_tier_profiles.json"
  "scripts/openclaw-ops/MODEL_TIER_SWITCH.md"
  "scripts/openclaw-ops/switch_model_tier.py"
  "scripts/openclaw-ops/sync_agents_12_to_servers.sh"
)

POLICY_FILES=(
  "scripts/openclaw-ops/policy/gateway_service_manager.py"
  "scripts/openclaw-ops/policy/io_write_gateway.py"
  "scripts/openclaw-ops/policy/policy-config.json"
  "scripts/openclaw-ops/policy/policy_enforcer.py"
  "scripts/openclaw-ops/policy/routing-rules.json"
  "scripts/openclaw-ops/policy/task_center.py"
  "scripts/openclaw-ops/policy/token-pricing.json"
)

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
  timeout "${SSH_CMD_TIMEOUT}" "${SSH_BIN}" "${SSH_OPTS[@]}" "${server}" "${cmd}"
}

scp_run() {
  local src="$1"
  local dst="$2"
  if [[ "${USE_WINDOWS_OPENSSH}" == "1" ]]; then
    src="$(wslpath -w "${src}")"
  fi
  timeout "${SSH_CMD_TIMEOUT}" "${SCP_BIN}" "${SSH_OPTS[@]}" "${src}" "${dst}"
}

REMOTE_PATCH_OPENCLAW="$(cat <<'PY'
import json
import os
from datetime import datetime
from pathlib import Path

old_ref = "openai-codex/gpt-5.3-codex"
new_ref = "openai-codex/gpt-5.4"
old_id = "gpt-5.3-codex"
new_id = "gpt-5.4"
old_name = "GPT-5.3 Codex"
new_name = "GPT-5.4"
dry_run = os.environ.get("SYNC_DRY_RUN", "0") == "1"

cfg = Path.home() / ".openclaw" / "openclaw.json"
data = json.loads(cfg.read_text(encoding="utf-8"))

def rewrite(value):
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            next_key = new_ref if key == old_ref else key
            out[next_key] = rewrite(item)
        return out
    if isinstance(value, list):
        return [rewrite(item) for item in value]
    if value == old_ref:
        return new_ref
    if value == old_id:
        return new_id
    if value == old_name:
        return new_name
    return value

updated = rewrite(data)
providers = updated.setdefault("models", {}).setdefault("providers", {})
openai_cfg = providers.get("openai-codex")
if isinstance(openai_cfg, dict):
    model_list = openai_cfg.get("models")
    if isinstance(model_list, list):
        filtered = []
        has_new = False
        for item in model_list:
            if not isinstance(item, dict):
                filtered.append(item)
                continue
            model_id = item.get("id")
            if model_id == old_id:
                patched = dict(item)
                patched["id"] = new_id
                patched["name"] = new_name
                filtered.append(patched)
                has_new = True
                continue
            if model_id == new_id:
                has_new = True
            filtered.append(item)
        if not has_new:
            filtered.insert(0, {"id": new_id, "name": new_name})
        openai_cfg["models"] = filtered

agents_cfg = updated.setdefault("agents", {})
defaults = agents_cfg.setdefault("defaults", {})
default_models = defaults.get("models")
if isinstance(default_models, dict):
    codex_meta = default_models.pop(old_ref, None)
    if new_ref not in default_models:
        default_models[new_ref] = codex_meta if isinstance(codex_meta, dict) else {"alias": "codex"}

agent_list = agents_cfg.get("list")
if isinstance(agent_list, list):
    for item in agent_list:
        if isinstance(item, dict) and item.get("id") in {"reviewer", "optimization-agent"}:
            item["model"] = new_ref
changed = updated != data
if changed and not dry_run:
    backup = cfg.with_name(f"openclaw.json.bak.gpt54.{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    backup.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    cfg.write_text(json.dumps(updated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"UPDATED {cfg}")
    print(f"BACKUP {backup}")
elif changed:
    print("DRY_RUN_CHANGE")
else:
    print("NO_CHANGE")
PY
)"

REMOTE_VERIFY="$(cat <<'PY'
import re
from pathlib import Path

targets = [
    Path.home() / ".openclaw" / "openclaw.json",
    Path.home() / ".openclaw" / "agents" / "agent_index.json",
    Path.home() / ".openclaw" / "agents" / "agent_index.md",
    Path.home() / ".openclaw" / "ops" / "model_tier_profiles.json",
    Path.home() / ".openclaw" / "ops" / "switch_model_tier.py",
    Path.home() / ".openclaw" / "ops" / "policy" / "policy-config.json",
    Path.home() / ".openclaw" / "ops" / "policy" / "policy_enforcer.py",
    Path.home() / ".openclaw" / "ops" / "policy" / "token-pricing.json",
]

targets.extend(
    Path.home() / ".openclaw" / "agents" / agent / "agent" / "models.json"
    for agent in (
        "agent-factory",
        "backend-dev",
        "coordinator",
        "deployer",
        "doc-writer",
        "frontend-dev",
        "main",
        "ops-agent",
        "project-agent",
        "reviewer",
        "tester",
    )
)

legacy_pattern = re.compile(r"gpt-5\.3-codex(?!-spark)")
legacy_name_pattern = re.compile(r"GPT-5\.3 Codex(?! Spark)")
new_pattern = re.compile(r"gpt-5\.4")
problems = []
present = []

for path in targets:
    if not path.exists():
        problems.append(f"missing:{path}")
        continue
    text = path.read_text(encoding="utf-8")
    if legacy_pattern.search(text) or legacy_name_pattern.search(text):
        problems.append(f"legacy:{path}")
    if new_pattern.search(text):
        present.append(str(path))

print(f"checked={len(targets)}")
print(f"present_new={len(present)}")
if problems:
    print("status=fail")
    for item in problems:
        print(item)
    raise SystemExit(2)
print("status=ok")
PY
)"

ok_count=0
fail_count=0

for server in "${SERVERS[@]}"; do
  echo "=========="
  echo "[sync-gpt54] server=${server}"

  if ! ssh_run "${server}" "echo ok" >/dev/null 2>&1; then
    echo "[sync-gpt54] connect failed: ${server}" >&2
    fail_count=$((fail_count + 1))
    continue
  fi

  remote_home="$(ssh_run "${server}" 'printf "%s" "$HOME"' | tr -d '\r')"
  remote_openclaw_home="${remote_home}/.openclaw"
  remote_agents_dir="${remote_openclaw_home}/agents"
  remote_ops_dir="${remote_openclaw_home}/ops"
  remote_ops_policy_dir="${remote_ops_dir}/policy"
  remote_workspace_ops_policy_dir="${remote_openclaw_home}/workspace-ops-agent/ops/policy"
  remote_task_db="${remote_ops_dir}/task-center/task_center.db"

  ssh_run "${server}" "mkdir -p '${remote_agents_dir}' '${remote_ops_dir}' '${remote_ops_policy_dir}' '${remote_workspace_ops_policy_dir}' '${remote_ops_dir}/task-center'"

  if [[ "${DRY_RUN}" != "1" ]]; then
    for agent in "${MODEL_AGENTS[@]}"; do
      ssh_run "${server}" "mkdir -p '${remote_agents_dir}/${agent}/agent'"
      scp_run "${REPO_ROOT}/agents/${agent}/models.json" "${server}:${remote_agents_dir}/${agent}/agent/models.json" >/dev/null
    done

    scp_run "${REPO_ROOT}/agents/agent_index.json" "${server}:${remote_agents_dir}/agent_index.json" >/dev/null
    scp_run "${REPO_ROOT}/agents/agent_index.md" "${server}:${remote_agents_dir}/agent_index.md" >/dev/null

    for rel in "${OPS_FILES[@]}"; do
      base_name="$(basename "${rel}")"
      scp_run "${REPO_ROOT}/${rel}" "${server}:${remote_ops_dir}/${base_name}" >/dev/null
    done

    for rel in "${POLICY_FILES[@]}"; do
      base_name="$(basename "${rel}")"
      scp_run "${REPO_ROOT}/${rel}" "${server}:${remote_ops_policy_dir}/${base_name}" >/dev/null
      scp_run "${REPO_ROOT}/${rel}" "${server}:${remote_workspace_ops_policy_dir}/${base_name}" >/dev/null
    done
  fi

  ssh_run "${server}" "SYNC_DRY_RUN=${DRY_RUN} python3 - <<'PY'
${REMOTE_PATCH_OPENCLAW}
PY"

  if [[ "${DRY_RUN}" != "1" ]]; then
    ssh_run "${server}" "python3 '${remote_workspace_ops_policy_dir}/policy_enforcer.py' --db '${remote_task_db}' --policy-file '${remote_workspace_ops_policy_dir}/policy-config.json' --routing-file '${remote_workspace_ops_policy_dir}/routing-rules.json' --pricing-file '${remote_workspace_ops_policy_dir}/token-pricing.json' validate-runtime" || true
    if [[ "${RESTART_GATEWAY}" == "1" ]]; then
      ssh_run "${server}" "python3 '${remote_workspace_ops_policy_dir}/gateway_service_manager.py' --action restart --prefer system --emit-json >/dev/null"
    fi
  fi

  if ssh_run "${server}" "python3 - <<'PY'
${REMOTE_VERIFY}
PY"; then
    ok_count=$((ok_count + 1))
  else
    fail_count=$((fail_count + 1))
  fi
done

echo "=========="
echo "[sync-gpt54] done ok=${ok_count} fail=${fail_count}"
if [[ ${fail_count} -gt 0 ]]; then
  exit 2
fi
