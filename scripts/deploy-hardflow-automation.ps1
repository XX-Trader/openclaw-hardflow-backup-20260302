# 一键部署 HardFlow 自动化脚本到 nofx 服务器
# 在新的 PowerShell 终端中执行此脚本

$SSH_CFG = "F:/ssh_keys/ssh_config"
$LOCAL_BASE = "H:\GitHub\openclaw-hardflow-backup-20260302"
$REMOTE_OPS = "/root/.openclaw/ops"
$REMOTE_CFG = "/root/.openclaw/config"

Write-Host "=== HardFlow 自动化脚本部署 ===" -ForegroundColor Cyan

# 1. 确保远端目录存在
Write-Host "[1/4] 创建远端目录..." -ForegroundColor Yellow
ssh -F $SSH_CFG -o ConnectTimeout=10 nofx "mkdir -p /root/.openclaw/ops /root/.openclaw/config"

# 2. 传输 6 个脚本
Write-Host "[2/4] 传输自动化脚本..." -ForegroundColor Yellow
$scripts = @(
    "claim_verification_auditor.py",
    "memtidy_runner.py",
    "config_watchdog.py",
    "unified_exception_logger.py",
    "agent_self_evolution.py",
    "workflow_audit.py"
)
foreach ($s in $scripts) {
    $local = "$LOCAL_BASE\scripts\openclaw-ops\$s"
    Write-Host "  $s" -NoNewline
    scp -F $SSH_CFG -o ConnectTimeout=10 $local "nofx:/root/.openclaw/ops/$s"
    if ($LASTEXITCODE -eq 0) { Write-Host " OK" -ForegroundColor Green } else { Write-Host " FAIL" -ForegroundColor Red }
}

# 3. 传输配置文件
Write-Host "[3/4] 传输配置文件..." -ForegroundColor Yellow
scp -F $SSH_CFG -o ConnectTimeout=10 "$LOCAL_BASE\config\memtidy_rules.json" "nofx:/root/.openclaw/config/"
if ($LASTEXITCODE -eq 0) { Write-Host "  memtidy_rules.json OK" -ForegroundColor Green }

# 4. 传输 cron/jobs.json
Write-Host "[4/4] 传输 cron/jobs.json..." -ForegroundColor Yellow
$bakCmd = 'cp /root/.openclaw/cron/jobs.json /root/.openclaw/cron/jobs.json.bak 2>/dev/null; echo done'
ssh -F $SSH_CFG -o ConnectTimeout=10 nofx $bakCmd
scp -F $SSH_CFG -o ConnectTimeout=10 "$LOCAL_BASE\cron\jobs.json" "nofx:/root/.openclaw/cron/jobs.json"
if ($LASTEXITCODE -eq 0) { Write-Host "  jobs.json OK" -ForegroundColor Green }

# 5. 验证
Write-Host ""
Write-Host "=== 验证部署 ===" -ForegroundColor Cyan
$verifyCmd = 'echo "--- ops scripts ---"; ls /root/.openclaw/ops/*.py 2>/dev/null; echo "--- config ---"; ls /root/.openclaw/config/memtidy_rules.json 2>/dev/null; echo "--- cron ---"; python3 -c "import json; d=json.load(open(chr(47)+chr(114)+chr(111)+chr(111)+chr(116)+chr(47)+chr(46)+chr(111)+chr(112)+chr(101)+chr(110)+chr(99)+chr(108)+chr(97)+chr(119)+chr(47)+chr(99)+chr(114)+chr(111)+chr(110)+chr(47)+chr(106)+chr(111)+chr(98)+chr(115)+chr(46)+chr(106)+chr(115)+chr(111)+chr(110))); print(len(d.get(chr(106)+chr(111)+chr(98)+chr(115),[])))" 2>/dev/null'
ssh -F $SSH_CFG -o ConnectTimeout=10 nofx $verifyCmd

Write-Host ""
Write-Host "部署完成! 重启 OpenClaw 让新 cron job 生效:" -ForegroundColor Green
Write-Host '  ssh -F F:/ssh_keys/ssh_config nofx "cd /root/.openclaw && pm2 restart openclaw"' -ForegroundColor White
