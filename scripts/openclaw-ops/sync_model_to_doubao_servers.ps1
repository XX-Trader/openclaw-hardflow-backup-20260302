param(
    [string[]]$Servers = @("pm-website", "大白pm", "nofx", "coingod", "tokyo-claw"),
    [string]$SshConfig = "D:\学习资料\ssh_keys\ssh_config",
    [string]$PrimaryModel = "kimicode/Doubao-Seed-2.0-Code",
    [string]$FallbackModel = "glmcode/glm-5",
    [string]$DoubaoProvider = "kimicode",
    [string]$DoubaoModelId = "Doubao-Seed-2.0-Code",
    [string]$DoubaoBaseUrl = "https://ark.cn-beijing.volces.com/api/coding/v3",
    [string]$DoubaoApiKey = "82c9795c-30f3-47d8-9cfe-e2275c35b28e",
    [switch]$DryRun,
    [switch]$RestartGateway
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)

if (!(Test-Path $SshConfig)) {
    throw "ssh_config not found: $SshConfig"
}

$RemotePy = @'
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
desired_defaults_model = {"primary": primary, "fallbacks": [fallback]}
if defaults.get("model") != desired_defaults_model:
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
        val = item.get("model")
        if isinstance(val, str):
            if val != primary:
                item["model"] = primary
                changed = True
        elif isinstance(val, dict):
            if val != desired_defaults_model:
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
'@

function Invoke-Remote {
    param([string]$Server, [string]$Command)
    & ssh -F $SshConfig -o BatchMode=yes -o ConnectTimeout=12 -o StrictHostKeyChecking=accept-new $Server $Command
}

function Upload-File {
    param([string]$Server, [string]$LocalPath, [string]$RemotePath)
    & scp -F $SshConfig -o BatchMode=yes -o ConnectTimeout=12 $LocalPath "${Server}:${RemotePath}" | Out-Null
}

$tmpScript = Join-Path $env:TEMP "openclaw-model-sync-remote.py"
Set-Content -Path $tmpScript -Value $RemotePy -Encoding UTF8

$ok = 0
$failed = @()

foreach ($server in $Servers) {
    Write-Host "=========="
    Write-Host "[sync-model] server=$server"
    try {
        $remoteHome = (Invoke-Remote -Server $server -Command 'printf "%s" "$HOME"' | Out-String).Trim()
        if ([string]::IsNullOrWhiteSpace($remoteHome)) { throw "cannot detect remote home" }

        $remoteDir = "$remoteHome/.openclaw/workspace-ops-agent/ops"
        $remoteScript = "$remoteDir/model_sync_remote.py"

        Invoke-Remote -Server $server -Command "mkdir -p '$remoteDir'"
        Upload-File -Server $server -LocalPath $tmpScript -RemotePath $remoteScript

        $dryFlag = if ($DryRun) { "1" } else { "0" }
        Invoke-Remote -Server $server -Command "SYNC_PRIMARY_MODEL='$PrimaryModel' SYNC_FALLBACK_MODEL='$FallbackModel' SYNC_DOUBAO_PROVIDER='$DoubaoProvider' SYNC_DOUBAO_MODEL_ID='$DoubaoModelId' SYNC_DOUBAO_BASE_URL='$DoubaoBaseUrl' SYNC_DOUBAO_API_KEY='$DoubaoApiKey' SYNC_DRY_RUN='$dryFlag' python3 '$remoteScript'"

        if (!$DryRun -and $RestartGateway) {
            Invoke-Remote -Server $server -Command "openclaw gateway restart >/dev/null 2>&1 || true"
        }

        $ok++
    }
    catch {
        Write-Host "[sync-model] FAILED server=$server error=$($_.Exception.Message)" -ForegroundColor Red
        $failed += $server
    }
}

Write-Host "=========="
Write-Host "[sync-model] done ok=$ok fail=$($failed.Count)"
if ($failed.Count -gt 0) {
    Write-Host "[sync-model] failed servers: $($failed -join ', ')" -ForegroundColor Yellow
    exit 2
}
