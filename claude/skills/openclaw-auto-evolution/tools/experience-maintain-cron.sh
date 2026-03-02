#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-daily}"
WORKSPACE="${2:-$HOME/.openclaw/workspace}"

if [[ "${MODE}" != "daily" && "${MODE}" != "weekly" && "${MODE}" != "monthly" ]]; then
  echo "[experience-maintain-cron] invalid mode: ${MODE}" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MAINTAIN_SCRIPT="${SCRIPT_DIR}/experience-maintain.mjs"

if [[ ! -f "${MAINTAIN_SCRIPT}" ]]; then
  echo "[experience-maintain-cron] missing script: ${MAINTAIN_SCRIPT}" >&2
  exit 1
fi

mkdir -p "${WORKSPACE}/memory"
TODAY_FILE="${WORKSPACE}/memory/$(date +%F).md"
touch "${TODAY_FILE}"

if [[ ! -f "${WORKSPACE}/MEMORY.md" ]]; then
  cat > "${WORKSPACE}/MEMORY.md" <<'EOF'
# MEMORY.md

## Purpose
- Keep durable context for recurring tasks and operational decisions.

## Policy
- Prefer concise daily records in `memory/YYYY-MM-DD.md`.
- Keep only actionable conclusions and verified outcomes.
EOF
fi

node "${MAINTAIN_SCRIPT}" --workspace "${WORKSPACE}" --mode "${MODE}"

if command -v openclaw >/dev/null 2>&1; then
  openclaw memory index --force >/dev/null 2>&1 || true
fi

echo "[experience-maintain-cron] mode=${MODE} workspace=${WORKSPACE} done"
