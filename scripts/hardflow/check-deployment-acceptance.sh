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

resolve_python_bin() {
  if command -v python3 >/dev/null 2>&1; then
    printf '%s\n' "python3"
    return 0
  fi
  if command -v python >/dev/null 2>&1; then
    printf '%s\n' "python"
    return 0
  fi
  printf '%s\n' "python3"
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

write_gate() {
  local passed="$1"
  local reason="$2"
  local safe_reason
  safe_reason="${reason//\"/\'}"
  cat > "$(gate_file "deployment_acceptance")" <<EOF
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
ACCEPTANCE_DIR="${RUN_DIR}/acceptance"
OUTPUT_FILE="${ACCEPTANCE_DIR}/deployment.json"
PYTHON_BIN="${DEPLOY_ACCEPT_PYTHON_BIN:-$(resolve_python_bin)}"
mkdir -p "${ACCEPTANCE_DIR}"

passed_checks=()
failed_checks=()
skipped_checks=()
required_checks=()
optional_checks=()

run_check() {
  local check_name="$1"
  local command_text="$2"
  local required_flag="$3"
  local log_file="${ACCEPTANCE_DIR}/${check_name}.log"
  local rc=0

  if [[ "${required_flag}" == "required" ]]; then
    required_checks+=("${check_name}")
  else
    optional_checks+=("${check_name}")
  fi

  if [[ -z "${command_text}" ]]; then
    skipped_checks+=("${check_name}")
    return 0
  fi

  set +e
  bash -lc "${command_text}" >"${log_file}" 2>&1
  rc=$?
  set -e

  if [[ ${rc} -eq 0 ]]; then
    passed_checks+=("${check_name}")
    return 0
  fi

  failed_checks+=("${check_name}")
  return ${rc}
}

gateway_cmd="${DEPLOY_ACCEPT_GATEWAY_CMD:-openclaw gateway status}"
status_cmd="${DEPLOY_ACCEPT_STATUS_CMD:-openclaw status}"
plugins_cmd="${DEPLOY_ACCEPT_PLUGINS_CMD:-openclaw plugins list}"
hooks_cmd="${DEPLOY_ACCEPT_HOOKS_CMD:-openclaw hooks check --json}"
jobs_cmd="${DEPLOY_ACCEPT_JOBS_CMD:-openclaw cron status --json}"
openviking_cmd="${DEPLOY_ACCEPT_OPENVIKING_CMD:-${PYTHON_BIN} \"${ROOT_DIR}/scripts/openclaw-ops/check_openviking_stack.py\" --workspace-root \"${ROOT_DIR}\" --run-id \"${RUN_ID}\"}"
telegram_cmd="${DEPLOY_ACCEPT_TELEGRAM_CMD:-}"
feishu_cmd="${DEPLOY_ACCEPT_FEISHU_CMD:-}"

run_check "gateway_status" "${gateway_cmd}" "required" || true
run_check "openclaw_status" "${status_cmd}" "required" || true
run_check "plugins_list" "${plugins_cmd}" "required" || true
run_check "hooks_check" "${hooks_cmd}" "required" || true
run_check "jobs_status" "${jobs_cmd}" "required" || true
run_check "openviking_stack" "${openviking_cmd}" "required" || true
run_check "telegram_status" "${telegram_cmd}" "optional" || true
run_check "feishu_status" "${feishu_cmd}" "optional" || true

if (( ${#failed_checks[@]} > 0 )); then
  cat > "${OUTPUT_FILE}" <<EOF
{
  "run_id": "${RUN_ID}",
  "passed": false,
  "updated_at": "$(timestamp)",
  "required_checks": $(json_array "${required_checks[@]}"),
  "optional_checks": $(json_array "${optional_checks[@]}"),
  "passed_checks": $(json_array "${passed_checks[@]}"),
  "failed_checks": $(json_array "${failed_checks[@]}"),
  "skipped_checks": $(json_array "${skipped_checks[@]}"),
  "log_dir": ".workflow/runs/${RUN_ID}/acceptance"
}
EOF
  echo "[deployment-acceptance] blocked: run_id=${RUN_ID}; failed=${failed_checks[*]}"
  write_gate "false" "deployment acceptance failed: ${failed_checks[*]}"
  exit 1
fi

cat > "${OUTPUT_FILE}" <<EOF
{
  "run_id": "${RUN_ID}",
  "passed": true,
  "updated_at": "$(timestamp)",
  "required_checks": $(json_array "${required_checks[@]}"),
  "optional_checks": $(json_array "${optional_checks[@]}"),
  "passed_checks": $(json_array "${passed_checks[@]}"),
  "failed_checks": $(json_array "${failed_checks[@]}"),
  "skipped_checks": $(json_array "${skipped_checks[@]}"),
  "log_dir": ".workflow/runs/${RUN_ID}/acceptance"
}
EOF

echo "[deployment-acceptance] passed: run_id=${RUN_ID}; passed=${passed_checks[*]}"
write_gate "true" "deployment acceptance passed"
