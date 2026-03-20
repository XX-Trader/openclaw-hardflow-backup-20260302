param(
    [string[]]$Servers = @("pm-website", "大白pm", "nofx", "coingod", "tokyo-claw"),
    [string]$SshConfig = "D:\ssh_keys\ssh_config",
    [switch]$RestartGateway
)

$ErrorActionPreference = "Stop"

if (!(Test-Path $SshConfig)) {
    throw "ssh_config not found: $SshConfig"
}

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$localPolicyDir = Join-Path $repoRoot "scripts\openclaw-ops\policy"
$localHooksDir = Join-Path $repoRoot "hooks"
$localGatewayServiceManager = Join-Path $localPolicyDir "gateway_service_manager.py"
if (!(Test-Path $localHooksDir)) {
    $fallbackHooksDir = Join-Path $repoRoot ".claude\hardflow\hooks"
    if (Test-Path $fallbackHooksDir) {
        $localHooksDir = $fallbackHooksDir
    }
}

if (!(Test-Path $localPolicyDir)) { throw "missing policy dir: $localPolicyDir" }
if (!(Test-Path $localHooksDir)) { throw "missing hooks dir: $localHooksDir" }
if (!(Test-Path $localGatewayServiceManager)) { throw "missing gateway service manager: $localGatewayServiceManager" }

function Invoke-Remote {
    param([string]$Server, [string]$Command)
    & ssh -F $SshConfig -o BatchMode=yes -o ConnectTimeout=12 -o StrictHostKeyChecking=accept-new $Server $Command
}

function Upload-File {
    param([string]$Server, [string]$LocalPath, [string]$RemotePath)
    & scp -F $SshConfig -o BatchMode=yes -o ConnectTimeout=12 $LocalPath "${Server}:${RemotePath}" | Out-Null
}

$ok = 0
$failed = @()

foreach ($server in $Servers) {
    Write-Host "=========="
    Write-Host "[sync-policy] server=$server"
    try {
        $remoteHome = (Invoke-Remote -Server $server -Command 'printf "%s" "$HOME"' | Out-String).Trim()
        if ([string]::IsNullOrWhiteSpace($remoteHome)) { throw "cannot detect remote home" }

        $remotePolicyDir = "$remoteHome/.openclaw/workspace-ops-agent/ops/policy"
        $remoteHooksDir = "$remoteHome/.claude/hooks"
        $remoteDb = "$remoteHome/.openclaw/ops/task-center/task_center.db"
        $remoteOpsDir = "$remoteHome/.openclaw/ops"
        $remoteGatewayManager = "$remotePolicyDir/gateway_service_manager.py"

        Invoke-Remote -Server $server -Command "mkdir -p '$remotePolicyDir' '$remoteHooksDir' '$remoteHome/.openclaw/ops/task-center' '$remoteOpsDir'"

        Get-ChildItem -Path $localPolicyDir -File | ForEach-Object {
            Upload-File -Server $server -LocalPath $_.FullName -RemotePath "$remotePolicyDir/$($_.Name)"
        }
        Upload-File -Server $server -LocalPath (Join-Path $localPolicyDir "project_index_maintainer.py") -RemotePath "$remoteOpsDir/project_index_maintainer.py"
        Upload-File -Server $server -LocalPath (Join-Path $localPolicyDir "project-registry.example.json") -RemotePath "$remoteHome/.openclaw/ops/task-center/project-registry.example.json"

        foreach ($hookName in @("hardflow-policy-enforcer", "hardflow-command-guard")) {
            Invoke-Remote -Server $server -Command "mkdir -p '$remoteHooksDir/$hookName'"
            Upload-File -Server $server -LocalPath (Join-Path $localHooksDir "$hookName/HOOK.md") -RemotePath "$remoteHooksDir/$hookName/HOOK.md"
            $jsHandler = Join-Path $localHooksDir "$hookName/handler.js"
            $tsHandler = Join-Path $localHooksDir "$hookName/handler.ts"
            if (Test-Path $jsHandler) {
                Upload-File -Server $server -LocalPath $jsHandler -RemotePath "$remoteHooksDir/$hookName/handler.js"
            } else {
                Upload-File -Server $server -LocalPath $tsHandler -RemotePath "$remoteHooksDir/$hookName/handler.ts"
            }
        }

        Invoke-Remote -Server $server -Command "python3 '$remotePolicyDir/policy_enforcer.py' --db '$remoteDb' --policy-file '$remotePolicyDir/policy-config.json' --routing-file '$remotePolicyDir/routing-rules.json' --pricing-file '$remotePolicyDir/token-pricing.json' init"
        Invoke-Remote -Server $server -Command "openclaw config set --json hooks.internal.enabled true"
        Invoke-Remote -Server $server -Command "openclaw config set hooks.internal.load.extraDirs[0] '$remoteHooksDir'"
        Invoke-Remote -Server $server -Command "openclaw config set --json hooks.internal.entries.hardflow-command-guard.enabled true"
        Invoke-Remote -Server $server -Command "openclaw config set --json hooks.internal.entries.hardflow-policy-enforcer.enabled true"
        Invoke-Remote -Server $server -Command "python3 '$remotePolicyDir/policy_enforcer.py' --db '$remoteDb' --policy-file '$remotePolicyDir/policy-config.json' --routing-file '$remotePolicyDir/routing-rules.json' --pricing-file '$remotePolicyDir/token-pricing.json' validate-runtime"

        if ($RestartGateway) {
            Invoke-Remote -Server $server -Command "python3 '$remoteGatewayManager' --action restart --prefer system --emit-json >/dev/null"
        }

        Invoke-Remote -Server $server -Command "openclaw hooks check --json | sed -n '1,80p'"
        $ok++
    }
    catch {
        Write-Host "[sync-policy] FAILED server=$server error=$($_.Exception.Message)" -ForegroundColor Red
        $failed += $server
    }
}

Write-Host "=========="
Write-Host "[sync-policy] done ok=$ok fail=$($failed.Count)"
if ($failed.Count -gt 0) {
    Write-Host "[sync-policy] failed servers: $($failed -join ', ')" -ForegroundColor Yellow
    exit 2
}
