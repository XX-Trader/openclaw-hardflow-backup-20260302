param(
    [string[]]$Servers = @("pm-website", "大白pm", "nofx", "coingod", "tokyo-claw", "hangqing-zhongxin"),
    [string]$SshConfig = "D:\学习资料\ssh_keys\ssh_config",
    [switch]$RestartGateway
)

$ErrorActionPreference = "Stop"

if (!(Test-Path $SshConfig)) {
    throw "ssh_config not found: $SshConfig"
}

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$localPolicyDir = Join-Path $repoRoot "scripts\openclaw-ops\policy"
$localHooksDir = Join-Path $repoRoot ".claude\hardflow\hooks"

if (!(Test-Path $localPolicyDir)) { throw "missing policy dir: $localPolicyDir" }
if (!(Test-Path $localHooksDir)) { throw "missing hooks dir: $localHooksDir" }

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

        Invoke-Remote -Server $server -Command "mkdir -p '$remotePolicyDir' '$remoteHooksDir' '$remoteHome/.openclaw/ops/task-center'"

        Get-ChildItem -Path $localPolicyDir -File | ForEach-Object {
            Upload-File -Server $server -LocalPath $_.FullName -RemotePath "$remotePolicyDir/$($_.Name)"
        }

        foreach ($hookName in @("hardflow-policy-enforcer", "hardflow-command-guard")) {
            Invoke-Remote -Server $server -Command "mkdir -p '$remoteHooksDir/$hookName'"
            Upload-File -Server $server -LocalPath (Join-Path $localHooksDir "$hookName/HOOK.md") -RemotePath "$remoteHooksDir/$hookName/HOOK.md"
            Upload-File -Server $server -LocalPath (Join-Path $localHooksDir "$hookName/handler.ts") -RemotePath "$remoteHooksDir/$hookName/handler.ts"
        }

        Invoke-Remote -Server $server -Command "python3 '$remotePolicyDir/policy_enforcer.py' --db '$remoteDb' --policy-file '$remotePolicyDir/policy-config.json' --routing-file '$remotePolicyDir/routing-rules.json' --pricing-file '$remotePolicyDir/token-pricing.json' init"
        Invoke-Remote -Server $server -Command "openclaw config set --json hooks.internal.enabled true"
        Invoke-Remote -Server $server -Command "openclaw config set hooks.internal.load.extraDirs[0] '$remoteHooksDir'"
        Invoke-Remote -Server $server -Command "openclaw config set --json hooks.internal.entries.hardflow-command-guard.enabled true"
        Invoke-Remote -Server $server -Command "openclaw config set --json hooks.internal.entries.hardflow-policy-enforcer.enabled true"
        Invoke-Remote -Server $server -Command "python3 '$remotePolicyDir/policy_enforcer.py' --db '$remoteDb' --policy-file '$remotePolicyDir/policy-config.json' --routing-file '$remotePolicyDir/routing-rules.json' --pricing-file '$remotePolicyDir/token-pricing.json' validate-runtime"

        if ($RestartGateway) {
            Invoke-Remote -Server $server -Command "openclaw gateway restart >/dev/null 2>&1 || true"
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
