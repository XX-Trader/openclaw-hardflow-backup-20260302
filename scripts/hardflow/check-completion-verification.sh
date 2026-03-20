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

gate_file() {
  local gate_name="$1"
  printf '%s/%s.json\n' "${GATE_DIR}" "${gate_name}"
}

is_passed_file() {
  local file="$1"
  [[ -f "${file}" ]] && grep -Eq '"passed"[[:space:]]*:[[:space:]]*true' "${file}"
}

matches_run_id() {
  local file="$1"
  local current_run_id="$2"
  [[ -f "${file}" ]] && grep -Eq "\"run_id\"[[:space:]]*:[[:space:]]*\"${current_run_id}\"" "${file}"
}

write_gate() {
  local passed="$1"
  local reason="$2"
  local safe_reason
  safe_reason="${reason//\"/\'}"
  cat > "$(gate_file "completion_verification")" <<EOF
{"passed":${passed},"updated_at":"$(timestamp)","run_id":"${RUN_ID}","reason":"${safe_reason}"}
EOF
}

json_array() {
  local first=1
  local item=""
  printf '['
  for item in "$@"; do
    if [[ ${first} -eq 0 ]]; then
      printf ','
    fi
    item="${item//\\/\\\\}"
    item="${item//\"/\\\"}"
    printf '"%s"' "${item}"
    first=0
  done
  printf ']'
}

RUN_ID="$(run_id)"
RUN_DIR="${WORKFLOW_DIR}/runs/${RUN_ID}"
OUTPUT_DIR="${RUN_DIR}/verification"
OUTPUT_FILE="${OUTPUT_DIR}/completion.json"
mkdir -p "${OUTPUT_DIR}"

required_gates=(
  "deployment_acceptance"
  "quality_gate_predeploy"
  "quality_gate_postdeploy"
  "reviewer"
  "tester"
  "api_doc"
  "post_tester"
  "score_requirements"
  "score_solution"
  "score_frontend"
  "score_backend"
  "score_security"
  "score_release"
  "score_final"
)

required_logs=(
  ".workflow/runs/${RUN_ID}/timeline.log"
  ".workflow/runs/${RUN_ID}/review.log"
  ".workflow/runs/${RUN_ID}/deploy.log"
  ".workflow/runs/${RUN_ID}/post-test.log"
)

required_artifacts=(
  ".workflow/runs/${RUN_ID}/acceptance/deployment.json"
  ".workflow/runs/${RUN_ID}/classification.json"
  ".workflow/runs/${RUN_ID}/dispatch.json"
  ".workflow/runs/${RUN_ID}/scorecards/requirements.json"
  ".workflow/runs/${RUN_ID}/scorecards/solution.json"
  ".workflow/runs/${RUN_ID}/scorecards/frontend.json"
  ".workflow/runs/${RUN_ID}/scorecards/backend.json"
  ".workflow/runs/${RUN_ID}/scorecards/security.json"
  ".workflow/runs/${RUN_ID}/scorecards/release.json"
  ".workflow/runs/${RUN_ID}/scorecards/final.json"
)

missing=()
failed=()
stale=()

for gate_name in "${required_gates[@]}"; do
  current_gate_file="$(gate_file "${gate_name}")"
  if [[ ! -f "${current_gate_file}" ]]; then
    missing+=("gate:${gate_name}")
    continue
  fi
  if ! matches_run_id "${current_gate_file}" "${RUN_ID}"; then
    stale+=("gate:${gate_name}")
    continue
  fi
  if ! is_passed_file "${current_gate_file}"; then
    failed+=("gate:${gate_name}")
  fi
done

for relative_path in "${required_logs[@]}" "${required_artifacts[@]}"; do
  absolute_path="${ROOT_DIR}/${relative_path}"
  if [[ ! -s "${absolute_path}" ]]; then
    missing+=("${relative_path}")
  fi
done

if (( ${#missing[@]} > 0 || ${#failed[@]} > 0 || ${#stale[@]} > 0 )); then
  reason="run_id=${RUN_ID}; missing=${missing[*]:-none}; failed=${failed[*]:-none}; stale=${stale[*]:-none}"
  cat > "${OUTPUT_FILE}" <<EOF
{
  "run_id": "${RUN_ID}",
  "passed": false,
  "updated_at": "$(timestamp)",
  "required_gates": $(json_array "${required_gates[@]}"),
  "checked_logs": $(json_array "${required_logs[@]}"),
  "checked_artifacts": $(json_array "${required_artifacts[@]}"),
  "missing": $(json_array "${missing[@]}"),
  "failed": $(json_array "${failed[@]}"),
  "stale": $(json_array "${stale[@]}")
}
EOF
  echo "[completion-verification] blocked: ${reason}"
  write_gate "false" "${reason}"
  exit 1
fi

cat > "${OUTPUT_FILE}" <<EOF
{
  "run_id": "${RUN_ID}",
  "passed": true,
  "updated_at": "$(timestamp)",
  "required_gates": $(json_array "${required_gates[@]}"),
  "checked_logs": $(json_array "${required_logs[@]}"),
  "checked_artifacts": $(json_array "${required_artifacts[@]}")
}
EOF

echo "[completion-verification] passed: run_id=${RUN_ID}"
write_gate "true" "completion verification passed"
