#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
WORKFLOW_DIR="${ROOT_DIR}/.workflow"
STATE_FILE="${WORKFLOW_DIR}/current_run_id"
GATE_DIR="${WORKFLOW_DIR}/gates"

action="${1:-deploy}"

if [[ -n "${HARD_FLOW_RUN_ID:-}" ]]; then
  run_id="${HARD_FLOW_RUN_ID}"
elif [[ -f "${STATE_FILE}" ]]; then
  run_id="$(cat "${STATE_FILE}")"
else
  run_id="unknown"
fi

echo "=== HardFlow Approval Preview ==="
echo "action: ${action}"
echo "run_id: ${run_id}"
echo "timestamp: $(date -u +"%Y-%m-%dT%H:%M:%SZ")"
echo
echo "gate files:"
for gate in reviewer tester api_doc \
  score_requirements score_solution score_frontend score_backend score_security score_release score_final \
  post_tester rollback quality_gate_predeploy quality_gate_postdeploy; do
  file="${GATE_DIR}/${gate}.json"
  if [[ -f "${file}" ]]; then
    echo "- ${gate}: $(tr -d '\n' < "${file}")"
  else
    echo "- ${gate}: (missing)"
  fi
done
echo
echo "note: side effects of '${action}' run only after approval"
