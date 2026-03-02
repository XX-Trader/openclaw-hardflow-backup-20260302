#!/usr/bin/env bash
set -euo pipefail

GATE="${1:-}"
if [[ -z "${GATE}" ]]; then
  echo "usage: improve-gate.sh <gate>" >&2
  exit 2
fi

case "${GATE}" in
  requirements|solution|frontend|backend|security|release|final) ;;
  *)
    echo "unknown gate: ${GATE}" >&2
    exit 2
    ;;
esac

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
LOG_DIR="${ROOT_DIR}/.workflow/improve"
mkdir -p "${LOG_DIR}"
TS="$(date -u +"%Y-%m-%dT%H%M%SZ")"
LOG_FILE="${LOG_DIR}/${TS}-${GATE}.log"

{
  echo "ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  echo "gate=${GATE}"
  echo "result=improve action recorded"
  echo "note=replace with project-specific remediation automation"
} > "${LOG_FILE}"

echo "improve logged: ${LOG_FILE}"
