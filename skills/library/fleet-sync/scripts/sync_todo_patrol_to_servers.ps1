param(
    [string[]]$Servers = @(),
    [string]$SshConfig = "",
    [string]$RemoteRepo = "",
    [string]$RemoteRuntimeHome = "",
    [string]$NotificationChannel = "",
    [string]$NotificationTarget = "",
    [string]$Timezone = "",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

if (-not $Servers -or $Servers.Count -eq 0) {
    $Servers = @($env:HARDFLOW_FLEET_SERVERS -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ })
}
if (-not $Servers -or $Servers.Count -eq 0) {
    throw "provide hosts with -Servers or HARDFLOW_FLEET_SERVERS"
}
if ([string]::IsNullOrWhiteSpace($SshConfig)) {
    $SshConfig = if ($env:SSH_CONFIG) { $env:SSH_CONFIG } else { Join-Path $HOME ".ssh/config" }
}
if (!(Test-Path -LiteralPath $SshConfig)) {
    throw "ssh_config not found: $SshConfig"
}
if ([string]::IsNullOrWhiteSpace($RemoteRepo)) { $RemoteRepo = $env:HARDFLOW_REMOTE_WORKFLOW_REPO }
if ([string]::IsNullOrWhiteSpace($RemoteRuntimeHome)) { $RemoteRuntimeHome = $env:HARDFLOW_REMOTE_RUNTIME_HOME }
if ([string]::IsNullOrWhiteSpace($NotificationChannel)) { $NotificationChannel = $env:HARDFLOW_NOTIFICATION_CHANNEL }
if ([string]::IsNullOrWhiteSpace($NotificationTarget)) { $NotificationTarget = $env:HARDFLOW_NOTIFICATION_TARGET }
if ([string]::IsNullOrWhiteSpace($Timezone)) { $Timezone = $env:HARDFLOW_TIMEZONE }

function Quote-Sh([string]$Value) {
    $quote = [string][char]39
    $doubleQuote = [string][char]34
    $escapedQuote = $quote + $doubleQuote + $quote + $doubleQuote + $quote
    return $quote + $Value.Replace($quote, $escapedQuote) + $quote
}

$ok = 0
$failed = @()
foreach ($server in $Servers) {
    try {
        $remoteHome = (& ssh -F $SshConfig -o BatchMode=yes -o ConnectTimeout=12 $server 'printf "%s" "$HOME"' | Out-String).Trim()
        if ([string]::IsNullOrWhiteSpace($remoteHome)) { throw "remote home is empty" }

        $repo = if ($RemoteRepo) { $RemoteRepo } else { "$remoteHome/workflow-infra" }
        $runtime = if ($RemoteRuntimeHome) { $RemoteRuntimeHome } else { "$remoteHome/.openclaw" }
        $parts = @(
            "python3", "$repo/setup.py",
            "--runtime-home", $runtime,
            "--repo-root", $repo,
            "--job-name", "TODO 巡检（15分钟）",
            "--emit-json"
        )
        if ($NotificationChannel) { $parts += @("--notification-channel", $NotificationChannel) }
        if ($NotificationTarget) { $parts += @("--notification-target", $NotificationTarget) }
        if ($Timezone) { $parts += @("--timezone", $Timezone) }
        if ($DryRun) { $parts += "--dry-run" }
        $quoted = (($parts | ForEach-Object { Quote-Sh ([string]$_) }) -join ' ')
        $setupPath = Quote-Sh "$repo/setup.py"
        $command = "test -f $setupPath && $quoted"
        & ssh -F $SshConfig -o BatchMode=yes $server $command
        if ($LASTEXITCODE -ne 0) { throw "remote installer exit=$LASTEXITCODE" }
        $ok++
    }
    catch {
        Write-Host "[sync] failed host=$server error=$($_.Exception.Message)" -ForegroundColor Red
        $failed += $server
    }
}

Write-Host "[sync] done ok=$ok fail=$($failed.Count)"
if ($failed.Count -gt 0) { exit 2 }
