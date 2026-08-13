param(
    [string[]]$Servers = @(),
    [string]$SshConfig = "",
    [switch]$DryRun,
    [switch]$SkipGatewayRestart
)

$ErrorActionPreference = "Stop"

$repoRoot = if ($env:HARDFLOW_WORKFLOW_REPO) {
    $env:HARDFLOW_WORKFLOW_REPO
} else {
    (& git -C $PSScriptRoot rev-parse --show-toplevel).Trim()
}
if ([string]::IsNullOrWhiteSpace($SshConfig)) {
    $SshConfig = if ($env:SSH_CONFIG) { $env:SSH_CONFIG } else { Join-Path $HOME ".ssh/config" }
}
$sshExe = (Get-Command $(if ($env:SSH_EXE) { $env:SSH_EXE } else { "ssh" }) -ErrorAction Stop).Source
$scpExe = (Get-Command $(if ($env:SCP_EXE) { $env:SCP_EXE } else { "scp" }) -ErrorAction Stop).Source

if (-not (Test-Path $SshConfig)) {
    throw "ssh_config not found: $SshConfig"
}

if (-not $Servers -or $Servers.Count -eq 0) {
    if ($env:HARDFLOW_FLEET_SERVERS) {
        $Servers = @($env:HARDFLOW_FLEET_SERVERS -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ })
    } else {
        $Servers = Select-String -Path $SshConfig -Pattern '^Host\s+' |
        ForEach-Object { ($_ -split '\s+', 2)[1].Trim() } |
        Where-Object { $_ -and $_ -notmatch '[*?]' }
    }
}
if (-not $Servers -or $Servers.Count -eq 0) {
    throw "provide hosts with -Servers or HARDFLOW_FLEET_SERVERS"
}

$modelAgents = @(
    "backend-dev",
    "coordinator",
    "deployer",
    "doc-writer",
    "frontend-dev",
    "ops-agent",
    "optimization-agent",
    "project-agent",
    "reviewer",
    "tester",
    "web-agent"
)

$opsFiles = @(
    "scripts/openclaw-ops/shared/chat_output.py",
    "skills/library/openclaw-workflow-manager/scripts/model_tier_profiles.json",
    "skills/library/openclaw-workflow-manager/scripts/MODEL_TIER_SWITCH.md",
    "skills/library/openclaw-workflow-manager/scripts/switch_model_tier.py",
    "skills/library/fleet-sync/scripts/sync_agents_12_to_servers.sh",
    "scripts/openclaw-ops/shared/utf8_runtime.py",
    "skills/library/openclaw-workflow-manager/scripts/workflow_views.py"
)

$policyFiles = @(
    "skills/library/control-plane-ops/scripts/policy/alert_dedupe.py",
    "skills/library/control-plane-ops/scripts/policy/dataclass_compat.py",
    "skills/library/control-plane-ops/scripts/policy/gateway_service_manager.py",
    "skills/library/control-plane-ops/scripts/policy/io_write_gateway.py",
    "skills/library/control-plane-ops/scripts/policy/policy-config.json",
    "skills/library/control-plane-ops/scripts/policy/policy_enforcer.py",
    "skills/library/control-plane-ops/scripts/policy/routing-rules.json",
    "skills/library/control-plane-ops/scripts/policy/task_capability_binding.py",
    "skills/library/control-plane-ops/scripts/policy/task_center.py",
    "skills/library/control-plane-ops/scripts/policy/task_executor_runner.py",
    "skills/library/control-plane-ops/scripts/policy/token-pricing.json"
)

$patchPy = @'
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
'@

$verifyPy = @'
import re
from pathlib import Path

targets = [
    Path.home() / ".openclaw" / "openclaw.json",
    Path.home() / ".openclaw" / "agents" / "agent_index.json",
    Path.home() / ".openclaw" / "agents" / "agent_index.md",
    Path.home() / ".openclaw" / "ops" / "chat_output.py",
    Path.home() / ".openclaw" / "ops" / "model_tier_profiles.json",
    Path.home() / ".openclaw" / "ops" / "switch_model_tier.py",
    Path.home() / ".openclaw" / "ops" / "utf8_runtime.py",
    Path.home() / ".openclaw" / "ops" / "workflow_views.py",
    Path.home() / ".openclaw" / "ops" / "policy" / "alert_dedupe.py",
    Path.home() / ".openclaw" / "ops" / "policy" / "policy-config.json",
    Path.home() / ".openclaw" / "ops" / "policy" / "dataclass_compat.py",
    Path.home() / ".openclaw" / "ops" / "policy" / "policy_enforcer.py",
    Path.home() / ".openclaw" / "ops" / "policy" / "task_capability_binding.py",
    Path.home() / ".openclaw" / "ops" / "policy" / "token-pricing.json",
    Path.home() / ".openclaw" / "ops" / "policy" / "task_center.py",
    Path.home() / ".openclaw" / "ops" / "policy" / "task_executor_runner.py",
]

targets.extend(
    Path.home() / ".openclaw" / "agents" / agent / "agent" / "models.json"
    for agent in (
        "backend-dev",
        "coordinator",
        "deployer",
        "doc-writer",
        "frontend-dev",
        "ops-agent",
        "optimization-agent",
        "project-agent",
        "reviewer",
        "tester",
        "web-agent",
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
'@

$tempDir = Join-Path $env:TEMP "openclaw-gpt54-rollout"
New-Item -ItemType Directory -Force -Path $tempDir | Out-Null
$patchFile = Join-Path $tempDir "openclaw_patch_gpt54.py"
$verifyFile = Join-Path $tempDir "openclaw_verify_gpt54.py"
[System.IO.File]::WriteAllText($patchFile, $patchPy, (New-Object System.Text.UTF8Encoding($false)))
[System.IO.File]::WriteAllText($verifyFile, $verifyPy, (New-Object System.Text.UTF8Encoding($false)))

function Invoke-Ssh {
    param(
        [Parameter(Mandatory = $true)][string]$Server,
        [Parameter(Mandatory = $true)][string]$Command
    )
    & $sshExe -F $sshConfig $Server $Command
    if ($LASTEXITCODE -ne 0) {
        throw "ssh failed on $Server"
    }
}

function Copy-ToRemote {
    param(
        [Parameter(Mandatory = $true)][string]$LocalPath,
        [Parameter(Mandatory = $true)][string]$Server,
        [Parameter(Mandatory = $true)][string]$RemotePath
    )
    & $scpExe -F $sshConfig $LocalPath "$($Server):$RemotePath"
    if ($LASTEXITCODE -ne 0) {
        throw "scp failed: $LocalPath -> $Server`:$RemotePath"
    }
}

$okCount = 0
$failCount = 0

foreach ($server in $Servers) {
    Write-Host "=========="
    Write-Host "[sync-gpt54] server=$server"

    try {
        Invoke-Ssh -Server $server -Command "echo ok" | Out-Null
        $remoteHome = (& $sshExe -F $sshConfig $server "python3 -c 'from pathlib import Path; print(Path.home())'").Trim()
        if (-not $remoteHome) {
            throw "cannot resolve remote home: $server"
        }

        $remoteOpenclawHome = "$remoteHome/.openclaw"
        $remoteAgentsDir = "$remoteOpenclawHome/agents"
        $remoteOpsDir = "$remoteOpenclawHome/ops"
        $remoteOpsPolicyDir = "$remoteOpsDir/policy"
        $remoteWorkspaceOpsPolicyDir = "$remoteOpenclawHome/workspace-ops-agent/ops/policy"
        $remoteTaskDb = "$remoteOpsDir/task-center/task_center.db"

        Invoke-Ssh -Server $server -Command "mkdir -p '$remoteAgentsDir' '$remoteOpsDir' '$remoteOpsPolicyDir' '$remoteWorkspaceOpsPolicyDir' '$remoteOpsDir/task-center' '/tmp'"

        Copy-ToRemote -LocalPath $patchFile -Server $server -RemotePath "/tmp/openclaw_patch_gpt54.py"
        Copy-ToRemote -LocalPath $verifyFile -Server $server -RemotePath "/tmp/openclaw_verify_gpt54.py"

        if (-not $DryRun) {
            foreach ($agent in $modelAgents) {
                $remoteAgentDir = "$remoteAgentsDir/$agent/agent"
                Invoke-Ssh -Server $server -Command "mkdir -p '$remoteAgentDir'"
                Copy-ToRemote -LocalPath (Join-Path $repoRoot "agents/$agent/models.json") -Server $server -RemotePath "$remoteAgentDir/models.json"
            }

            Copy-ToRemote -LocalPath (Join-Path $repoRoot "agents/agent_index.json") -Server $server -RemotePath "$remoteAgentsDir/agent_index.json"
            Copy-ToRemote -LocalPath (Join-Path $repoRoot "agents/agent_index.md") -Server $server -RemotePath "$remoteAgentsDir/agent_index.md"

            foreach ($rel in $opsFiles) {
                $baseName = [System.IO.Path]::GetFileName($rel)
                Copy-ToRemote -LocalPath (Join-Path $repoRoot $rel) -Server $server -RemotePath "$remoteOpsDir/$baseName"
            }

            foreach ($rel in $policyFiles) {
                $baseName = [System.IO.Path]::GetFileName($rel)
                $localPath = Join-Path $repoRoot $rel
                Copy-ToRemote -LocalPath $localPath -Server $server -RemotePath "$remoteOpsPolicyDir/$baseName"
                Copy-ToRemote -LocalPath $localPath -Server $server -RemotePath "$remoteWorkspaceOpsPolicyDir/$baseName"
            }
        }

        $dryRunValue = if ($DryRun) { "1" } else { "0" }
        Invoke-Ssh -Server $server -Command "SYNC_DRY_RUN=$dryRunValue python3 /tmp/openclaw_patch_gpt54.py"

        if (-not $DryRun) {
            try {
                Invoke-Ssh -Server $server -Command "python3 '$remoteOpsPolicyDir/policy_enforcer.py' --db '$remoteTaskDb' --policy-file '$remoteOpsPolicyDir/policy-config.json' --routing-file '$remoteOpsPolicyDir/routing-rules.json' --pricing-file '$remoteOpsPolicyDir/token-pricing.json' validate-runtime"
                Invoke-Ssh -Server $server -Command "python3 '$remoteOpsPolicyDir/task_executor_runner.py' --help >/dev/null"
                Invoke-Ssh -Server $server -Command "python3 '$remoteWorkspaceOpsPolicyDir/policy_enforcer.py' --db '$remoteTaskDb' --policy-file '$remoteWorkspaceOpsPolicyDir/policy-config.json' --routing-file '$remoteWorkspaceOpsPolicyDir/routing-rules.json' --pricing-file '$remoteWorkspaceOpsPolicyDir/token-pricing.json' validate-runtime"
            } catch {
                Write-Warning "[sync-gpt54] validate-runtime failed on $server, continue"
            }
            if (-not $SkipGatewayRestart) {
                Invoke-Ssh -Server $server -Command "python3 '$remoteWorkspaceOpsPolicyDir/gateway_service_manager.py' --action restart --prefer system --emit-json >/dev/null"
            }
        }

        Invoke-Ssh -Server $server -Command "python3 /tmp/openclaw_verify_gpt54.py"
        $okCount += 1
    } catch {
        Write-Warning "[sync-gpt54] failed on $server : $($_.Exception.Message)"
        $failCount += 1
    }
}

Write-Host "=========="
Write-Host "[sync-gpt54] done ok=$okCount fail=$failCount"

if ($failCount -gt 0) {
    exit 2
}
