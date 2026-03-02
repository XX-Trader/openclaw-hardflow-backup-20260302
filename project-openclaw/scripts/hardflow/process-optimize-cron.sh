#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-daily}"
WORKSPACE="${2:-$HOME/.openclaw/workspace}"
HARDFLOW_ENV_FILE="${HARDFLOW_ENV_FILE:-}"

if [[ "${MODE}" != "daily" && "${MODE}" != "weekly" && "${MODE}" != "monthly" ]]; then
  echo "[process-optimize-cron] invalid mode: ${MODE}" >&2
  exit 1
fi

if [[ -z "${HARDFLOW_ENV_FILE}" ]]; then
  for candidate in \
    "${HOME:-}/.openclaw/hardflow/hardflow.env" \
    "${HOME:-}/.claude/hardflow/hardflow.env" \
    "${WORKSPACE}/.workflow/hardflow.env"; do
    if [[ -f "${candidate}" ]]; then
      HARDFLOW_ENV_FILE="${candidate}"
      break
    fi
  done
fi

if [[ -n "${HARDFLOW_ENV_FILE}" && -f "${HARDFLOW_ENV_FILE}" ]]; then
  # shellcheck disable=SC1090
  source "${HARDFLOW_ENV_FILE}"
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROCESS_SCRIPT="${SCRIPT_DIR}/process-optimize.mjs"

if [[ ! -f "${PROCESS_SCRIPT}" ]]; then
  echo "[process-optimize-cron] missing script: ${PROCESS_SCRIPT}" >&2
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

node "${PROCESS_SCRIPT}" --workspace "${WORKSPACE}" --mode "${MODE}"

if command -v openclaw >/dev/null 2>&1; then
  openclaw memory index --force >/dev/null 2>&1 || true
fi

echo "[process-optimize-cron] mode=${MODE} workspace=${WORKSPACE} done"
