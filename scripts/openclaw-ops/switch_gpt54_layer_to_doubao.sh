#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY_SCRIPT="${SCRIPT_DIR}/switch_model_tier.py"

if [[ ! -f "${PY_SCRIPT}" ]]; then
  echo "script not found: ${PY_SCRIPT}" >&2
  exit 1
fi

exec python3 "${PY_SCRIPT}" high_doubao "$@"
