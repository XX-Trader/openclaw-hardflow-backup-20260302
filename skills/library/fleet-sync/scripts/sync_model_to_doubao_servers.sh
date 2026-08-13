#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${HARDFLOW_WORKFLOW_REPO:-$(git -C "${SCRIPT_DIR}" rev-parse --show-toplevel)}"
cd "${REPO_ROOT}"

SSH_CFG="${SSH_CONFIG:-${HOME}/.ssh/config}"
if [[ ! -f "${SSH_CFG}" ]]; then
  echo "[sync-model] ssh_config not found. set SSH_CONFIG first." >&2
  exit 1
fi

if (( $# > 0 )); then
  SERVERS=("$@")
elif [[ -n "${HARDFLOW_FLEET_SERVERS:-}" ]]; then
  IFS=',' read -r -a SERVERS <<< "${HARDFLOW_FLEET_SERVERS}"
else
  echo "[sync-model] provide hosts as arguments or HARDFLOW_FLEET_SERVERS." >&2
  exit 2
fi

DRY_RUN="${DRY_RUN:-0}"
RESTART_GATEWAY="${RESTART_GATEWAY:-1}"
LOCAL_GATEWAY_SERVICE_MANAGER="${REPO_ROOT}/skills/library/control-plane-ops/scripts/policy/gateway_service_manager.py"

PRIMARY_MODEL="${PRIMARY_MODEL:-kimicode/doubao-seed-2.0-pro}"
FALLBACK_MODEL="${FALLBACK_MODEL:-openai-codex/gpt-5.3-codex}"
DOUBAO_PROVIDER="${DOUBAO_PROVIDER:-kimicode}"
DOUBAO_MODEL_ID="${DOUBAO_MODEL_ID:-doubao-seed-2.0-pro}"
DOUBAO_BASE_URL="${DOUBAO_BASE_URL:-https://ark.cn-beijing.volces.com/api/coding/v3}"
DOUBAO_API_KEY="${DOUBAO_API_KEY:-${KIMI_API_KEY:-}}"

if [[ -z "${DOUBAO_API_KEY}" ]]; then
  echo "[sync-model] DOUBAO_API_KEY or KIMI_API_KEY must be set; refusing to use a hardcoded model key." >&2
  exit 1
fi

if [[ ! -f "${LOCAL_GATEWAY_SERVICE_MANAGER}" ]]; then
  echo "[sync-model] gateway service manager missing: ${LOCAL_GATEWAY_SERVICE_MANAGER}" >&2
  exit 1
fi

REMOTE_GATEWAY_MANAGER="$(cat "${LOCAL_GATEWAY_SERVICE_MANAGER}")"

SSH_OPTS=(
  -F "${SSH_CFG}"
  -o BatchMode=yes
  -o ConnectTimeout=12
  -o StrictHostKeyChecking=accept-new
)

REMOTE_UPDATE_SCRIPT="$(cat <<'PY'
import json
import os
from datetime import datetime
from pathlib import Path

primary = os.environ["SYNC_PRIMARY_MODEL"]
fallback = os.environ["SYNC_FALLBACK_MODEL"]
provider = os.environ["SYNC_DOUBAO_PROVIDER"]
model_id = os.environ["SYNC_DOUBAO_MODEL_ID"]
base_url = os.environ["SYNC_DOUBAO_BASE_URL"]
api_key = os.environ["SYNC_DOUBAO_API_KEY"]
dry_run = os.environ.get("SYNC_DRY_RUN", "0") == "1"

cfg = Path.home() / ".openclaw" / "openclaw.json"
if not cfg.exists():
    print("NO_CONFIG")
    raise SystemExit(2)

raw = cfg.read_text(encoding="utf-8")
if raw.startswith("\ufeff"):
    raw = raw.lstrip("\ufeff")
data = json.loads(raw)
changed = False

providers = data.setdefault("models", {}).setdefault("providers", {})
prov = providers.setdefault(provider, {})

if prov.get("baseUrl") != base_url:
    prov["baseUrl"] = base_url
    changed = True
if prov.get("api") != "openai-completions":
    prov["api"] = "openai-completions"
    changed = True
if prov.get("apiKey") != api_key:
    prov["apiKey"] = api_key
    changed = True

desired_models = [{"id": model_id, "name": model_id}]
if prov.get("models") != desired_models:
    prov["models"] = desired_models
    changed = True

agents = data.setdefault("agents", {})
defaults = agents.setdefault("defaults", {})
defaults_model = defaults.get("model")
desired_defaults_model = {"primary": primary, "fallbacks": [fallback]}
if defaults_model != desired_defaults_model:
    defaults["model"] = desired_defaults_model
    changed = True

desired_defaults_models = {
    primary: {"alias": "doubao"},
    "glmcode/glm-5": {"alias": "glm"},
}
if "glmcode/glm-4.7" in defaults.get("models", {}):
    desired_defaults_models["glmcode/glm-4.7"] = {"alias": "glm47"}
if defaults.get("models") != desired_defaults_models:
    defaults["models"] = desired_defaults_models
    changed = True

agent_list = agents.get("list")
if isinstance(agent_list, list):
    for item in agent_list:
        if not isinstance(item, dict):
            continue
        if "model" not in item:
            item["model"] = primary
            changed = True
            continue
        model_val = item.get("model")
        if isinstance(model_val, str):
            if model_val != primary:
                item["model"] = primary
                changed = True
        elif isinstance(model_val, dict):
            if model_val != desired_defaults_model:
                item["model"] = desired_defaults_model
                changed = True

if changed and not dry_run:
    backup = cfg.with_name(f"openclaw.json.bak.modelsync.{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    backup.write_text(raw, encoding="utf-8")
    cfg.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("UPDATED")
    print(f"BACKUP={backup}")
elif changed and dry_run:
    print("DRY_RUN_CHANGE")
else:
    print("NO_CHANGE")

# keep policy runtime aligned to avoid model whitelist blocks
policy_dir = Path.home() / ".openclaw" / "workspace-ops-agent" / "ops" / "policy"
policy_cfg = policy_dir / "policy-config.json"
token_pricing = policy_dir / "token-pricing.json"

if policy_cfg.exists():
    cfg_raw = policy_cfg.read_text(encoding="utf-8")
    if cfg_raw.startswith("\ufeff"):
        cfg_raw = cfg_raw.lstrip("\ufeff")
    policy = json.loads(cfg_raw)
    p_changed = False
    if policy.get("primary_model") != primary:
        policy["primary_model"] = primary
        p_changed = True
    if policy.get("fallback_models") != [fallback]:
        policy["fallback_models"] = [fallback]
        p_changed = True
    allowed = [primary, "glmcode/glm-5", "glmcode/glm-4.7"]
    if policy.get("allowed_models") != allowed:
        policy["allowed_models"] = allowed
        p_changed = True
    if p_changed and not dry_run:
        backup = policy_cfg.with_name(f"policy-config.json.bak.modelsync.{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        backup.write_text(cfg_raw, encoding="utf-8")
        policy_cfg.write_text(json.dumps(policy, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"POLICY_UPDATED={policy_cfg}")
    elif p_changed and dry_run:
        print(f"POLICY_DRY_RUN_CHANGE={policy_cfg}")

if token_pricing.exists():
    pricing_raw = token_pricing.read_text(encoding="utf-8")
    if pricing_raw.startswith("\ufeff"):
        pricing_raw = pricing_raw.lstrip("\ufeff")
    pricing = json.loads(pricing_raw)
    models = pricing.get("models")
    if not isinstance(models, dict):
        models = {}
        pricing["models"] = models
    desired = {
        primary: models.get(primary, {"input": 0, "output": 0}),
        "glmcode/glm-5": models.get("glmcode/glm-5", {"input": 0, "output": 0}),
        "glmcode/glm-4.7": models.get("glmcode/glm-4.7", {"input": 0, "output": 0}),
    }
    if models != desired:
        if not dry_run:
            backup = token_pricing.with_name(f"token-pricing.json.bak.modelsync.{datetime.now().strftime('%Y%m%d_%H%M%S')}")
            backup.write_text(pricing_raw, encoding="utf-8")
            pricing["models"] = desired
            token_pricing.write_text(json.dumps(pricing, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(f"PRICING_UPDATED={token_pricing}")
        else:
            print(f"PRICING_DRY_RUN_CHANGE={token_pricing}")
PY
)"

ok_count=0
fail_count=0

restart_gateway_remote() {
  local server="$1"
  ssh "${SSH_OPTS[@]}" "${server}" "python3 - --action restart --prefer system --emit-json >/dev/null <<'PY'
${REMOTE_GATEWAY_MANAGER}
PY"
}

for server in "${SERVERS[@]}"; do
  echo "=========="
  echo "[sync-model] server=${server}"

  if ! ssh "${SSH_OPTS[@]}" "${server}" "echo ok" >/dev/null 2>&1; then
    echo "[sync-model] connect failed: ${server}" >&2
    fail_count=$((fail_count + 1))
    continue
  fi

  if ! ssh "${SSH_OPTS[@]}" "${server}" \
    "SYNC_PRIMARY_MODEL='${PRIMARY_MODEL}' \
     SYNC_FALLBACK_MODEL='${FALLBACK_MODEL}' \
     SYNC_DOUBAO_PROVIDER='${DOUBAO_PROVIDER}' \
     SYNC_DOUBAO_MODEL_ID='${DOUBAO_MODEL_ID}' \
     SYNC_DOUBAO_BASE_URL='${DOUBAO_BASE_URL}' \
     SYNC_DOUBAO_API_KEY='${DOUBAO_API_KEY}' \
     SYNC_DRY_RUN='${DRY_RUN}' \
     python3 - <<'PY'
${REMOTE_UPDATE_SCRIPT}
PY"; then
    echo "[sync-model] update failed: ${server}" >&2
    fail_count=$((fail_count + 1))
    continue
  fi

  if [[ "${DRY_RUN}" != "1" && "${RESTART_GATEWAY}" == "1" ]]; then
    restart_gateway_remote "${server}" || true
  fi

  ok_count=$((ok_count + 1))
done

echo "=========="
echo "[sync-model] done ok=${ok_count} fail=${fail_count}"
if [[ ${fail_count} -gt 0 ]]; then
  exit 2
fi
