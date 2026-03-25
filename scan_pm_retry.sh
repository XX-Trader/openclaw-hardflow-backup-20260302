#!/usr/bin/env bash
set -euo pipefail

echo "=== host=$(hostname) user=$(whoami) ==="

aTargets=(/home/ubuntu /tmp /var /opt /data /root /srv /etc /usr /backup)

for d in "${aTargets[@]}"; do
  if [ -d "$d" ]; then
    echo "-- $d"
    find "$d" -maxdepth 6 -type f \( -name 'oauth.json' -o -name '*oauth*' -o -name '*openai*' -o -name '*codex*' -o -name 'openai-codex*' -o -name '*token*' -o -name '*.cred*' -o -name '*credentials*' \) 2>/dev/null | head -n 120
  fi
done