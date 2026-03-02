#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
WORKFLOW_DIR="${ROOT_DIR}/.workflow"
GATE_DIR="${WORKFLOW_DIR}/gates"
STATE_FILE="${WORKFLOW_DIR}/current_run_id"

mkdir -p "${GATE_DIR}"

timestamp() {
  date -u +"%Y-%m-%dT%H:%M:%SZ"
}

run_id() {
  if [[ -n "${HARD_FLOW_RUN_ID:-}" ]]; then
    printf '%s\n' "${HARD_FLOW_RUN_ID}"
    return
  fi
  if [[ -f "${STATE_FILE}" ]]; then
    cat "${STATE_FILE}"
    return
  fi
  date +%Y%m%d_%H%M%S
}

write_gate() {
  local stage="$1"
  local passed="$2"
  local reason="$3"
  local safe_reason
  safe_reason="${reason//\"/\'}"
  cat > "${GATE_DIR}/quality_gate_${stage}.json" <<EOF
{"passed":${passed},"updated_at":"$(timestamp)","run_id":"$(run_id)","reason":"${safe_reason}"}
EOF
}

is_passed() {
  local file="$1"
  [[ -f "${file}" ]] && grep -Eq '"passed"[[:space:]]*:[[:space:]]*true' "${file}"
}

stage="predeploy"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --stage)
      stage="${2:-predeploy}"
      shift 2
      ;;
    *)
      shift
      ;;
  esac
done

required_predeploy=("reviewer" "tester" "api_doc" "score_requirements" "score_solution" "score_frontend" "score_backend" "score_security")
required_postdeploy=("reviewer" "tester" "api_doc" "post_tester" "score_requirements" "score_solution" "score_frontend" "score_backend" "score_security" "score_release" "score_final")

required=("${required_predeploy[@]}")
if [[ "${stage}" == "postdeploy" ]]; then
  required=("${required_postdeploy[@]}")
fi

missing=()
failed=()

for gate in "${required[@]}"; do
  gate_file="${GATE_DIR}/${gate}.json"
  if [[ ! -f "${gate_file}" ]]; then
    missing+=("${gate}")
    continue
  fi
  if ! is_passed "${gate_file}"; then
    failed+=("${gate}")
  fi
done

# If post deploy test failed, rollback must at least be executed and passed.
if [[ "${stage}" == "postdeploy" ]]; then
  post_tester_file="${GATE_DIR}/post_tester.json"
  rollback_file="${GATE_DIR}/rollback.json"

  if [[ -f "${post_tester_file}" ]] && ! is_passed "${post_tester_file}"; then
    if [[ ! -f "${rollback_file}" ]]; then
      missing+=("rollback")
    elif ! is_passed "${rollback_file}"; then
      failed+=("rollback")
    fi
  fi
fi

if (( ${#missing[@]} > 0 || ${#failed[@]} > 0 )); then
  reason="stage=${stage}; missing=${missing[*]:-none}; failed=${failed[*]:-none}"
  echo "[quality-gate] blocked: ${reason}"
  write_gate "${stage}" "false" "${reason}"
  exit 1
fi

echo "[quality-gate] passed: stage=${stage}; required=${required[*]}"
write_gate "${stage}" "true" "gate passed"
