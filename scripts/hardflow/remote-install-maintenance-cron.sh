#!/usr/bin/env bash
set -euo pipefail

mkdir -p ~/.openclaw/logs
tmp_file="$(mktemp)"

cat > "${tmp_file}" <<'EOF'
# BEGIN HARDFLOW PROCESS OPTIMIZATION
5 2 * * * /usr/bin/env bash $HOME/.openclaw/hardflow-hooks/tools/process-optimize-cron.sh daily >> $HOME/.openclaw/logs/process-optimization.log 2>&1
20 2 * * 1 /usr/bin/env bash $HOME/.openclaw/hardflow-hooks/tools/process-optimize-cron.sh weekly >> $HOME/.openclaw/logs/process-optimization.log 2>&1
35 2 1 * * /usr/bin/env bash $HOME/.openclaw/hardflow-hooks/tools/process-optimize-cron.sh monthly >> $HOME/.openclaw/logs/process-optimization.log 2>&1
# END HARDFLOW PROCESS OPTIMIZATION
EOF

( crontab -l 2>/dev/null | sed '/# BEGIN HARDFLOW EXPERIENCE MAINTENANCE/,/# END HARDFLOW EXPERIENCE MAINTENANCE/d'; cat "${tmp_file}" ) | crontab -
rm -f "${tmp_file}"

crontab -l | sed -n '/# BEGIN HARDFLOW EXPERIENCE MAINTENANCE/,/# END HARDFLOW EXPERIENCE MAINTENANCE/p'
