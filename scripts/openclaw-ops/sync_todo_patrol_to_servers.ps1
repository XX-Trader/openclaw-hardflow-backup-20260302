param(
    [string[]]$Servers = @("pm-website", "大白pm", "nofx", "coingod", "tokyo-claw"),
    [string]$SshConfig = "D:\学习资料\ssh_keys\ssh_config",
    [int]$EveryMs = 900000,
    [string]$DeliveryTo = "",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

function Invoke-Remote {
    param(
        [string]$Server,
        [string]$Command,
        [string]$ConfigPath
    )
    & ssh -F $ConfigPath -o BatchMode=yes -o ConnectTimeout=12 -o StrictHostKeyChecking=accept-new $Server $Command
}

function Upload-File {
    param(
        [string]$Server,
        [string]$LocalPath,
        [string]$RemotePath,
        [string]$ConfigPath
    )
    & scp -F $ConfigPath -o BatchMode=yes -o ConnectTimeout=12 $LocalPath "${Server}:${RemotePath}" | Out-Null
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$localPatrol = Join-Path $scriptDir "todo_patrol.py"
$localInstaller = Join-Path $scriptDir "install_todo_patrol_job.py"

if (!(Test-Path $SshConfig)) {
    throw "ssh_config not found: $SshConfig"
}
if (!(Test-Path $localPatrol)) {
    throw "missing file: $localPatrol"
}
if (!(Test-Path $localInstaller)) {
    throw "missing file: $localInstaller"
}

$ok = 0
$failed = @()

foreach ($server in $Servers) {
    Write-Host "=========="
    Write-Host "[sync] server=$server"
    try {
        $remoteHome = (Invoke-Remote -Server $server -ConfigPath $SshConfig -Command 'printf "%s" "$HOME"' | Out-String).Trim()
        if ([string]::IsNullOrWhiteSpace($remoteHome)) {
            throw "cannot detect remote home"
        }

        $remoteOpsRoot = "$remoteHome/.openclaw/workspace-ops-agent"
        $remoteOpsDir = "$remoteOpsRoot/ops"
        $remotePatrol = "$remoteOpsDir/todo_patrol.py"
        $remoteInstaller = "$remoteOpsDir/install_todo_patrol_job.py"

        Write-Host "[sync] remoteHome=$remoteHome"
        Write-Host "[sync] remoteOpsDir=$remoteOpsDir"

        if ($DryRun) {
            Write-Host "[sync] DRY_RUN only"
            $ok++
            continue
        }

        Invoke-Remote -Server $server -ConfigPath $SshConfig -Command "mkdir -p '$remoteOpsDir' '$remoteHome/.openclaw/cron' '$remoteOpsRoot/logs'"
        Upload-File -Server $server -ConfigPath $SshConfig -LocalPath $localPatrol -RemotePath $remotePatrol
        Upload-File -Server $server -ConfigPath $SshConfig -LocalPath $localInstaller -RemotePath $remoteInstaller

        $installCmd = "chmod 755 '$remotePatrol' '$remoteInstaller' && python3 '$remoteInstaller' --ops-script '$remotePatrol' --every-ms $EveryMs"
        if ($DeliveryTo) {
            $installCmd += " --to '$DeliveryTo'"
        }
        Invoke-Remote -Server $server -ConfigPath $SshConfig -Command $installCmd

        Write-Host "[sync] smoke test --dry-run"
        Invoke-Remote -Server $server -ConfigPath $SshConfig -Command "python3 '$remotePatrol' --dry-run --task sync-smoke | sed -n '1,24p'"

        $ok++
    }
    catch {
        Write-Host "[sync] FAILED server=$server error=$($_.Exception.Message)" -ForegroundColor Red
        $failed += $server
    }
}

Write-Host "=========="
Write-Host "[sync] done ok=$ok fail=$($failed.Count)"
if ($failed.Count -gt 0) {
    Write-Host "[sync] failed servers: $($failed -join ', ')" -ForegroundColor Yellow
    exit 2
}
