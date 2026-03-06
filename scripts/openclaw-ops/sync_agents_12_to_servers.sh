#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "${REPO_ROOT}"

SSH_CONFIG="${SSH_CONFIG:-}"
if [[ -z "${SSH_CONFIG}" ]]; then
  for candidate in \
    "/d/学习资料/ssh_keys/ssh_config" \
    "/mnt/d/学习资料/ssh_keys/ssh_config" \
    "D:/学习资料/ssh_keys/ssh_config"
  do
    if [[ -f "${candidate}" ]]; then
      SSH_CONFIG="${candidate}"
      break
    fi
  done
fi

if [[ -z "${SSH_CONFIG}" || ! -f "${SSH_CONFIG}" ]]; then
  echo "[sync-agents] cannot find ssh_config. Set SSH_CONFIG explicitly." >&2
  exit 1
fi

DRY_RUN="${DRY_RUN:-0}"

if (( $# > 0 )); then
  SERVERS=("$@")
else
  SERVERS=("pm-website" "大白pm" "nofx" "coingod" "hangqing-zhongxin" "tokyo-claw")
fi

REMOTE_UPDATE_SCRIPT="$(cat <<'PY'
import copy
import json
import os
from datetime import datetime
from pathlib import Path

dry_run = os.environ.get("SYNC_DRY_RUN", "0") == "1"
home = Path.home()
cfg = home / ".openclaw" / "openclaw.json"
if not cfg.exists():
    print("NO_CONFIG")
    raise SystemExit(2)

data = json.loads(cfg.read_text(encoding="utf-8"))
changed = False

agents = data.setdefault("agents", {})
lst = agents.get("list")
if not isinstance(lst, list):
    lst = []
    agents["list"] = lst
    changed = True

index = {}
for item in lst:
    if isinstance(item, dict):
        aid = item.get("id")
        if isinstance(aid, str) and aid.strip():
            index[aid] = item

def get_model_ref():
    main_cfg = index.get("main")
    if isinstance(main_cfg, dict):
        mm = main_cfg.get("model")
        if isinstance(mm, dict) and mm:
            return copy.deepcopy(mm)
        if isinstance(mm, str) and mm.strip():
            return {"primary": mm.strip()}
    defaults_model = agents.get("defaults", {}).get("model")
    if isinstance(defaults_model, dict) and defaults_model:
        return copy.deepcopy(defaults_model)
    if isinstance(defaults_model, str) and defaults_model.strip():
        return {"primary": defaults_model.strip()}
    return {"primary": "openai-codex/gpt-5.3-codex"}

model_ref = get_model_ref()
web_agent_model = {"primary": "glmcode/glm-4.7"}

def desired_agent(agent_id: str, allow_agents=None, model=None):
    payload = {
        "id": agent_id,
        "name": agent_id,
        "workspace": str(home / ".openclaw" / f"workspace-{agent_id}"),
        "agentDir": str(home / ".openclaw" / "agents" / agent_id / "agent"),
        "model": copy.deepcopy(model if model is not None else model_ref),
    }
    if allow_agents:
        payload["subagents"] = {"allowAgents": list(allow_agents)}
    return payload

desired = [
    desired_agent("ops-agent", ["optimization-agent", "secretary-agent"]),
    desired_agent("optimization-agent", ["secretary-agent"]),
    desired_agent("secretary-agent"),
    desired_agent("web-agent", model=web_agent_model),
]

for entry in desired:
    if entry["id"] not in index:
        lst.append(entry)
        index[entry["id"]] = entry
        changed = True

main_cfg = index.get("main")
if isinstance(main_cfg, dict):
    subagents = main_cfg.get("subagents")
    if not isinstance(subagents, dict):
        subagents = {}
        main_cfg["subagents"] = subagents
        changed = True
    allow = subagents.get("allowAgents")
    if not isinstance(allow, list):
        allow = []
        subagents["allowAgents"] = allow
        changed = True
    for aid in ("ops-agent", "optimization-agent", "secretary-agent", "web-agent"):
        if aid not in allow:
            allow.append(aid)
            changed = True

tools = data.get("tools")
if isinstance(tools, dict):
    a2a = tools.get("agentToAgent")
    if isinstance(a2a, dict):
        allow = a2a.get("allow")
        if isinstance(allow, list):
            for aid in ("ops-agent", "optimization-agent", "secretary-agent", "web-agent"):
                if aid not in allow:
                    allow.append(aid)
                    changed = True

web_cfg = index.get("web-agent")
if isinstance(web_cfg, dict):
    model = web_cfg.get("model")
    if model != "glmcode/glm-4.7" and model != web_agent_model:
        web_cfg["model"] = copy.deepcopy(web_agent_model)
        changed = True

for aid in ("ops-agent", "optimization-agent", "secretary-agent", "web-agent"):
    (home / ".openclaw" / f"workspace-{aid}").mkdir(parents=True, exist_ok=True)
    (home / ".openclaw" / "agents" / aid / "agent").mkdir(parents=True, exist_ok=True)
    (home / ".openclaw" / "agents" / aid / "sessions").mkdir(parents=True, exist_ok=True)

if changed and not dry_run:
    backup = cfg.with_name(f"openclaw.json.bak.agents13.{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    backup.write_text(cfg.read_text(encoding="utf-8"), encoding="utf-8")
    cfg.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("UPDATED")
    print(f"BACKUP={backup}")
elif changed and dry_run:
    print("DRY_RUN_CHANGE")
else:
    print("NO_CHANGE")

final_ids = [
    x.get("id")
    for x in data.get("agents", {}).get("list", [])
    if isinstance(x, dict) and isinstance(x.get("id"), str)
]
print("COUNT", len(final_ids))
print("IDS", ",".join(final_ids))
PY
)"

REMOTE_VERIFY_SCRIPT="$(cat <<'PY'
import json
from pathlib import Path

p = Path.home() / ".openclaw" / "openclaw.json"
j = json.loads(p.read_text(encoding="utf-8"))
ids = [
    x.get("id")
    for x in j.get("agents", {}).get("list", [])
    if isinstance(x, dict) and isinstance(x.get("id"), str)
]
print("COUNT", len(ids))
print("IDS", ",".join(ids))
PY
)"

for server in "${SERVERS[@]}"; do
  echo "[sync-agents] === ${server} ==="

  if ! ssh -F "${SSH_CONFIG}" "${server}" "echo ok" >/dev/null 2>&1; then
    echo "[sync-agents] connect failed: ${server}" >&2
    continue
  fi

  ssh -F "${SSH_CONFIG}" "${server}" "SYNC_DRY_RUN=${DRY_RUN} python3 - <<'PY'
${REMOTE_UPDATE_SCRIPT}
PY"

  if [[ "${DRY_RUN}" != "1" ]]; then
    ssh -F "${SSH_CONFIG}" "${server}" "openclaw gateway restart >/dev/null 2>&1 || true"
  fi

  ssh -F "${SSH_CONFIG}" "${server}" "python3 - <<'PY'
${REMOTE_VERIFY_SCRIPT}
PY"
done

echo "[sync-agents] done"
