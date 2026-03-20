#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
WORKFLOW_DIR="${ROOT_DIR}/.workflow"
STATE_FILE="${WORKFLOW_DIR}/current_run_id"
TASK_STATE_FILE="${WORKFLOW_DIR}/current_task_id"
GATE_DIR="${WORKFLOW_DIR}/gates"
ISSUE_SCHEMA_VERSION="1"
HARDFLOW_ENV_FILE="${HARDFLOW_ENV_FILE:-}"

if [[ -z "${HARDFLOW_ENV_FILE}" ]]; then
  for candidate in \
    "${HOME:-}/.openclaw/hardflow/hardflow.env" \
    "${HOME:-}/.claude/hardflow/hardflow.env" \
    "${ROOT_DIR}/.workflow/hardflow.env"; do
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

PYTHON_BIN="${HARDFLOW_PYTHON_BIN:-$(resolve_python_bin)}"

POLICY_ENFORCER_PY_DEFAULT="${ROOT_DIR}/scripts/openclaw-ops/policy/policy_enforcer.py"
POLICY_ENFORCER_PY="${POLICY_ENFORCER_PY:-${POLICY_ENFORCER_PY_DEFAULT}}"
POLICY_DB_FILE="${POLICY_DB_FILE:-${WORKFLOW_DIR}/task-center/task_center.db}"
POLICY_FILE="${POLICY_FILE:-${ROOT_DIR}/scripts/openclaw-ops/policy/policy-config.json}"
POLICY_ROUTING_FILE="${POLICY_ROUTING_FILE:-${ROOT_DIR}/scripts/openclaw-ops/policy/routing-rules.json}"
POLICY_PRICING_FILE="${POLICY_PRICING_FILE:-${ROOT_DIR}/scripts/openclaw-ops/policy/token-pricing.json}"
if [[ -z "${POLICY_ENFORCER_ENABLED:-}" ]]; then
  if [[ -f "${POLICY_ENFORCER_PY}" ]]; then
    POLICY_ENFORCER_ENABLED="1"
  else
    POLICY_ENFORCER_ENABLED="0"
  fi
fi
POLICY_ENFORCER_STRICT="${POLICY_ENFORCER_STRICT:-1}"
POLICY_TASK_ID="${POLICY_TASK_ID:-}"
POLICY_ACTOR="${POLICY_ACTOR:-hardflow-run}"
POLICY_AGENT_ID="${POLICY_AGENT_ID:-backend-dev}"
POLICY_MODEL="${POLICY_MODEL:-openai-codex/gpt-5.4}"
POLICY_ENTRY_AGENT="${POLICY_ENTRY_AGENT:-coordinator}"
POLICY_DISPATCHER_AGENT="${POLICY_DISPATCHER_AGENT:-coordinator}"
POLICY_AGENT_CLASSIFY="${POLICY_AGENT_CLASSIFY:-${POLICY_ENTRY_AGENT}}"
POLICY_AGENT_DISPATCH="${POLICY_AGENT_DISPATCH:-${POLICY_DISPATCHER_AGENT}}"
POLICY_AGENT_IMPLEMENT="${POLICY_AGENT_IMPLEMENT:-backend-dev}"
POLICY_AGENT_TEST_LOOP="${POLICY_AGENT_TEST_LOOP:-tester}"
POLICY_AGENT_REVIEW="${POLICY_AGENT_REVIEW:-reviewer}"
POLICY_AGENT_SCORE="${POLICY_AGENT_SCORE:-${POLICY_DISPATCHER_AGENT}}"
POLICY_AGENT_DEPLOY="${POLICY_AGENT_DEPLOY:-deployer}"
POLICY_AGENT_POST_TEST="${POLICY_AGENT_POST_TEST:-tester}"
POLICY_AGENT_GIT_PUSH="${POLICY_AGENT_GIT_PUSH:-deployer}"
POLICY_USAGE_INPUT_TOKENS="${POLICY_USAGE_INPUT_TOKENS:-0}"
POLICY_USAGE_OUTPUT_TOKENS="${POLICY_USAGE_OUTPUT_TOKENS:-0}"
HARDFLOW_REQUIRE_ATOMIC_TASK_JSON="${HARDFLOW_REQUIRE_ATOMIC_TASK_JSON:-1}"
HARDFLOW_RESET_CONTEXT_EACH_ATTEMPT="${HARDFLOW_RESET_CONTEXT_EACH_ATTEMPT:-1}"
HARDFLOW_CONTEXT_RESET_CMD="${HARDFLOW_CONTEXT_RESET_CMD:-}"
HARDFLOW_ENFORCE_WRITE_SCOPE="${HARDFLOW_ENFORCE_WRITE_SCOPE:-0}"
HARDFLOW_BACKEND_WRITE_PREFIXES="${HARDFLOW_BACKEND_WRITE_PREFIXES:-api/}"
HARDFLOW_FRONTEND_WRITE_PREFIXES="${HARDFLOW_FRONTEND_WRITE_PREFIXES:-src/}"
AUTO_GIT_ROLLBACK_ON_TEST_LOOP_FAIL="${AUTO_GIT_ROLLBACK_ON_TEST_LOOP_FAIL:-1}"
HARDFLOW_ROLLBACK_FORCE_DIRTY="${HARDFLOW_ROLLBACK_FORCE_DIRTY:-0}"

timestamp() {
  date -u +"%Y-%m-%dT%H:%M:%SZ"
}

usage() {
  cat <<'EOF'
Usage:
  hardflow-run.sh workflow --task "task text" [--max-retries N] [--score-max-retries N]
  hardflow-run.sh classify --task "task text"
  hardflow-run.sh dispatch
  hardflow-run.sh implement
  hardflow-run.sh test-loop [--max-retries N]
  hardflow-run.sh score-gate --gate <name> [--max-retries N] [--scorecard FILE]
  hardflow-run.sh score-all [--max-retries N]
  hardflow-run.sh score-report [--gate <name>] [--format text|json]
  hardflow-run.sh review
  hardflow-run.sh deploy
  hardflow-run.sh post-test
  hardflow-run.sh acceptance-test
  hardflow-run.sh verify-completion
  hardflow-run.sh rollback [--reason TEXT]
  hardflow-run.sh git-push

Env (optional):
  DISPATCH_CMD
  IMPLEMENT_CMD
  TEST_CMD
  FIX_CMD
  REVIEW_CMD
  DEPLOY_CMD
  POST_TEST_CMD
  ROLLBACK_CMD
  GIT_PUSH_CMD
  DEPLOY_ACCEPT_GATEWAY_CMD
  DEPLOY_ACCEPT_STATUS_CMD
  DEPLOY_ACCEPT_PLUGINS_CMD
  DEPLOY_ACCEPT_HOOKS_CMD
  DEPLOY_ACCEPT_JOBS_CMD
  DEPLOY_ACCEPT_OPENVIKING_CMD
  DEPLOY_ACCEPT_OPENVIKING_HEALTH_URL
  DEPLOY_ACCEPT_TELEGRAM_CMD
  DEPLOY_ACCEPT_FEISHU_CMD
  MAX_RETRIES
  AUTO_ROLLBACK_ON_POST_TEST_FAIL   # 1(default) / 0
  SCORE_MAX_RETRIES
  SCORE_REQUIREMENTS_CMD
  SCORE_SOLUTION_CMD
  SCORE_FRONTEND_CMD
  SCORE_BACKEND_CMD
  SCORE_SECURITY_CMD
  SCORE_RELEASE_CMD
  SCORE_FINAL_CMD
  IMPROVE_REQUIREMENTS_CMD
  IMPROVE_SOLUTION_CMD
  IMPROVE_FRONTEND_CMD
  IMPROVE_BACKEND_CMD
  IMPROVE_SECURITY_CMD
  IMPROVE_RELEASE_CMD
  IMPROVE_FINAL_CMD
  POLICY_ENFORCER_ENABLED
  POLICY_ENFORCER_STRICT
  POLICY_ENFORCER_PY
  POLICY_DB_FILE
  POLICY_FILE
  POLICY_ROUTING_FILE
  POLICY_PRICING_FILE
  POLICY_TASK_ID
  POLICY_AGENT_ID
  POLICY_MODEL
  POLICY_ENTRY_AGENT
  POLICY_DISPATCHER_AGENT
  POLICY_AGENT_CLASSIFY
  POLICY_AGENT_DISPATCH
  POLICY_AGENT_IMPLEMENT
  POLICY_AGENT_TEST_LOOP
  POLICY_AGENT_REVIEW
  POLICY_AGENT_SCORE
  POLICY_AGENT_DEPLOY
  POLICY_AGENT_POST_TEST
  POLICY_AGENT_GIT_PUSH
  POLICY_USAGE_INPUT_TOKENS
  POLICY_USAGE_OUTPUT_TOKENS
  HARDFLOW_REQUIRE_ATOMIC_TASK_JSON
  HARDFLOW_RESET_CONTEXT_EACH_ATTEMPT
  HARDFLOW_CONTEXT_RESET_CMD
  HARDFLOW_ENFORCE_WRITE_SCOPE
  HARDFLOW_BACKEND_WRITE_PREFIXES
  HARDFLOW_FRONTEND_WRITE_PREFIXES
  AUTO_GIT_ROLLBACK_ON_TEST_LOOP_FAIL
  HARDFLOW_ROLLBACK_FORCE_DIRTY
EOF
}

SUBCOMMAND="${1:-}"
if [[ -z "${SUBCOMMAND}" ]]; then
  usage
  exit 1
fi
shift || true

mkdir -p "${WORKFLOW_DIR}" "${GATE_DIR}"

resolve_run_id() {
  local id
  if [[ -n "${HARD_FLOW_RUN_ID:-}" ]]; then
    id="${HARD_FLOW_RUN_ID}"
  elif [[ "${SUBCOMMAND}" == "classify" ]]; then
    id="$(date +%Y%m%d_%H%M%S)"
    printf '%s\n' "${id}" > "${STATE_FILE}"
  elif [[ -f "${STATE_FILE}" ]]; then
    id="$(cat "${STATE_FILE}")"
  else
    id="$(date +%Y%m%d_%H%M%S)"
    printf '%s\n' "${id}" > "${STATE_FILE}"
  fi
  printf '%s\n' "${id}"
}

RUN_ID="$(resolve_run_id)"
RUN_DIR="${WORKFLOW_DIR}/runs/${RUN_ID}"
mkdir -p "${RUN_DIR}"
TIMELINE_FILE="${RUN_DIR}/timeline.log"
ISSUE_FILE="${RUN_DIR}/issues.ndjson"
BASELINE_DIRTY_FILE="${RUN_DIR}/baseline_dirty_files.txt"
CURRENT_DIRTY_FILE="${RUN_DIR}/current_dirty_files.txt"
NEW_DIRTY_FILE="${RUN_DIR}/new_dirty_files.txt"
SAVEPOINT_FILE="${RUN_DIR}/savepoint_commit.txt"
PROGRESS_FILE="${WORKFLOW_DIR}/progress.txt"
ATOMIC_TASK_FILE="${WORKFLOW_DIR}/task.json"
CONTEXT_RUNTIME_DIR="${WORKFLOW_DIR}/context/runtime"

touch "${ISSUE_FILE}"

log() {
  local level="$1"
  shift
  local msg="$*"
  printf '%s [%s] %s\n' "$(timestamp)" "${level}" "${msg}" | tee -a "${TIMELINE_FILE}"
}

json_escape() {
  printf '%s' "$1" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g'
}

git_head() {
  if git -C "${ROOT_DIR}" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    git -C "${ROOT_DIR}" rev-parse HEAD 2>/dev/null || true
  else
    true
  fi
}

collect_dirty_files() {
  local out_file="$1"
  : > "${out_file}"
  if ! git -C "${ROOT_DIR}" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    return 0
  fi
  {
    git -C "${ROOT_DIR}" diff --name-only --cached 2>/dev/null || true
    git -C "${ROOT_DIR}" diff --name-only 2>/dev/null || true
  } | sed '/^[[:space:]]*$/d' | sort -u > "${out_file}"
}

collect_new_dirty_files() {
  local out_file="$1"
  collect_dirty_files "${CURRENT_DIRTY_FILE}"
  if [[ -f "${BASELINE_DIRTY_FILE}" ]]; then
    comm -23 "${CURRENT_DIRTY_FILE}" "${BASELINE_DIRTY_FILE}" > "${out_file}" || true
  else
    cp "${CURRENT_DIRTY_FILE}" "${out_file}"
  fi
}

save_git_savepoint() {
  local reason="${1:-manual}"
  local head
  head="$(git_head)"
  if [[ -z "${head}" ]]; then
    log "WARN" "skip savepoint (${reason}): git head unavailable"
    return 0
  fi
  printf '%s\n' "${head}" > "${SAVEPOINT_FILE}"
  log "INFO" "savepoint set (${reason}): ${head}"
}

ensure_atomic_task_json() {
  local task_text="$1"
  if [[ "${HARDFLOW_REQUIRE_ATOMIC_TASK_JSON}" != "1" ]]; then
    return 0
  fi
  local guard_py="${SCRIPT_DIR}/atomic_task_guard.py"
  if [[ ! -f "${guard_py}" ]]; then
    log "ERROR" "atomic task guard missing: ${guard_py}"
    return 2
  fi
  if "${PYTHON_BIN}" "${guard_py}" \
    --task-file "${ATOMIC_TASK_FILE}" \
    --task-text "${task_text}" \
    --min-items 4 >"${RUN_DIR}/task-atomic.log" 2>&1; then
    log "INFO" "atomic task.json ready: ${ATOMIC_TASK_FILE}"
    return 0
  fi
  log "ERROR" "atomic task.json check failed, see ${RUN_DIR}/task-atomic.log"
  return 2
}

refresh_progress_context() {
  local stage="$1"
  local attempt="${2:-0}"

  if [[ "${HARDFLOW_RESET_CONTEXT_EACH_ATTEMPT}" != "1" ]]; then
    return 0
  fi

  mkdir -p "${CONTEXT_RUNTIME_DIR}" "$(dirname "${PROGRESS_FILE}")"
  cat > "${PROGRESS_FILE}" <<EOF
# hardflow-progress
run_id=${RUN_ID}
stage=${stage}
attempt=${attempt}
updated_at=$(timestamp)

## latest_timeline
$(tail -n 20 "${TIMELINE_FILE}" 2>/dev/null || true)

## latest_issues
$(tail -n 10 "${ISSUE_FILE}" 2>/dev/null || true)
EOF

  cat > "${CONTEXT_RUNTIME_DIR}/runtime.json" <<EOF
{"run_id":"$(json_escape "${RUN_ID}")","stage":"$(json_escape "${stage}")","attempt":"$(json_escape "${attempt}")","progress_file":"$(json_escape "${PROGRESS_FILE}")","updated_at":"$(timestamp)"}
EOF
  export HARDFLOW_PROGRESS_FILE="${PROGRESS_FILE}"

  if [[ -n "${HARDFLOW_CONTEXT_RESET_CMD}" ]]; then
    run_cmd_capture \
      "HARDFLOW_CONTEXT_RESET_CMD" \
      "${HARDFLOW_CONTEXT_RESET_CMD}" \
      "${RUN_DIR}/context-reset-${stage}-${attempt}.log" \
      0 || true
  fi
}

enforce_agent_write_scope() {
  local agent_id="$1"
  local stage="$2"
  if [[ "${HARDFLOW_ENFORCE_WRITE_SCOPE}" != "1" ]]; then
    return 0
  fi

  local allow_csv=""
  case "${agent_id}" in
    backend-dev) allow_csv="${HARDFLOW_BACKEND_WRITE_PREFIXES}" ;;
    frontend-dev) allow_csv="${HARDFLOW_FRONTEND_WRITE_PREFIXES}" ;;
    *) return 0 ;;
  esac

  collect_new_dirty_files "${NEW_DIRTY_FILE}"
  if [[ ! -s "${NEW_DIRTY_FILE}" ]]; then
    return 0
  fi

  if policy_enabled; then
    if ! policy_run "write-scope-${stage}" assert-write-scope \
      --agent-id "${agent_id}" \
      --changed-files-file "${NEW_DIRTY_FILE}"; then
      return $?
    fi
  fi

  IFS=',' read -r -a allow_prefixes <<< "${allow_csv}"
  local violations=()
  while IFS= read -r file; do
    [[ -z "${file}" ]] && continue
    local allowed=0
    local prefix
    for prefix in "${allow_prefixes[@]}"; do
      [[ -z "${prefix}" ]] && continue
      if [[ "${file}" == "${prefix}"* ]]; then
        allowed=1
        break
      fi
    done
    if [[ "${file}" == ".workflow/"* ]]; then
      allowed=1
    fi
    if [[ ${allowed} -eq 0 ]]; then
      violations+=("${file}")
    fi
  done < "${NEW_DIRTY_FILE}"

  if (( ${#violations[@]} == 0 )); then
    return 0
  fi

  printf '%s\n' "${violations[@]}" > "${RUN_DIR}/write-scope-violations-${stage}.txt"
  log "ERROR" "write scope violation by ${agent_id} at ${stage}, see ${RUN_DIR}/write-scope-violations-${stage}.txt"
  return 65
}

auto_git_reset_to_savepoint() {
  local reason="$1"
  local rollback_log="${RUN_DIR}/rollback.log"

  if [[ "${AUTO_GIT_ROLLBACK_ON_TEST_LOOP_FAIL}" != "1" ]]; then
    log "WARN" "auto git rollback disabled: AUTO_GIT_ROLLBACK_ON_TEST_LOOP_FAIL=${AUTO_GIT_ROLLBACK_ON_TEST_LOOP_FAIL}"
    return 0
  fi
  if ! git -C "${ROOT_DIR}" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    log "WARN" "skip git rollback (${reason}): not a git repository"
    return 0
  fi
  if [[ ! -f "${SAVEPOINT_FILE}" ]]; then
    log "WARN" "skip git rollback (${reason}): savepoint missing"
    return 0
  fi
  if [[ "${HARDFLOW_ROLLBACK_FORCE_DIRTY}" != "1" ]] && [[ -s "${BASELINE_DIRTY_FILE}" ]]; then
    log "WARN" "skip git rollback (${reason}): baseline dirty tree detected; set HARDFLOW_ROLLBACK_FORCE_DIRTY=1 to override"
    write_gate "rollback" "false" "rollback skipped due to baseline dirty files"
    return 0
  fi

  local savepoint
  savepoint="$(cat "${SAVEPOINT_FILE}" 2>/dev/null || true)"
  if [[ -z "${savepoint}" ]]; then
    log "WARN" "skip git rollback (${reason}): savepoint empty"
    return 0
  fi

  set +e
  git -C "${ROOT_DIR}" reset --hard "${savepoint}" >"${rollback_log}" 2>&1
  local rc=$?
  set -e

  if [[ ${rc} -eq 0 ]]; then
    write_gate "rollback" "true" "git reset --hard to savepoint ${savepoint} (${reason})"
    log "WARN" "auto git rollback applied (${reason}) => ${savepoint}"
    return 0
  fi

  write_gate "rollback" "false" "git rollback failed (${reason})"
  log "ERROR" "auto git rollback failed (${reason}), see ${rollback_log}"
  return ${rc}
}

policy_enabled() {
  [[ "${POLICY_ENFORCER_ENABLED}" == "1" ]] && [[ -f "${POLICY_ENFORCER_PY}" ]]
}

policy_log_file() {
  local label="$1"
  printf '%s/policy-%s.log\n' "${RUN_DIR}" "${label//[^a-zA-Z0-9._-]/_}"
}

policy_agent_for_stage() {
  local stage="$1"
  case "${stage}" in
    classify) printf '%s\n' "${POLICY_AGENT_CLASSIFY}" ;;
    dispatch) printf '%s\n' "${POLICY_AGENT_DISPATCH}" ;;
    implement) printf '%s\n' "${POLICY_AGENT_IMPLEMENT}" ;;
    test-loop) printf '%s\n' "${POLICY_AGENT_TEST_LOOP}" ;;
    review) printf '%s\n' "${POLICY_AGENT_REVIEW}" ;;
    score-*) printf '%s\n' "${POLICY_AGENT_SCORE}" ;;
    deploy) printf '%s\n' "${POLICY_AGENT_DEPLOY}" ;;
    post-test) printf '%s\n' "${POLICY_AGENT_POST_TEST}" ;;
    acceptance-test) printf '%s\n' "${POLICY_AGENT_POST_TEST}" ;;
    verify-completion) printf '%s\n' "${POLICY_AGENT_REVIEW}" ;;
    git-push) printf '%s\n' "${POLICY_AGENT_GIT_PUSH}" ;;
    *) printf '%s\n' "${POLICY_AGENT_ID}" ;;
  esac
}

policy_run() {
  local label="$1"
  shift

  if ! policy_enabled; then
    return 0
  fi

  local log_file
  local rc
  log_file="$(policy_log_file "${label}")"

  set +e
  "${PYTHON_BIN}" "${POLICY_ENFORCER_PY}" \
    --db "${POLICY_DB_FILE}" \
    --policy-file "${POLICY_FILE}" \
    --routing-file "${POLICY_ROUTING_FILE}" \
    --pricing-file "${POLICY_PRICING_FILE}" \
    "$@" >"${log_file}" 2>&1
  rc=$?
  set -e

  if [[ ${rc} -ne 0 ]]; then
    if [[ "${POLICY_ENFORCER_STRICT}" == "1" ]]; then
      log "ERROR" "policy ${label} failed (rc=${rc}), log=${log_file}"
      return ${rc}
    fi
    log "WARN" "policy ${label} failed (rc=${rc}) but strict mode is disabled, log=${log_file}"
  fi
  return 0
}

policy_init_runtime() {
  policy_run "init" init
}

policy_load_task_id() {
  if [[ -z "${POLICY_TASK_ID}" && -f "${TASK_STATE_FILE}" ]]; then
    POLICY_TASK_ID="$(cat "${TASK_STATE_FILE}")"
  fi
}

policy_save_task_id() {
  if [[ -n "${POLICY_TASK_ID}" ]]; then
    printf '%s\n' "${POLICY_TASK_ID}" > "${TASK_STATE_FILE}"
  fi
}

policy_task_exists() {
  local task_id="$1"
  if [[ -z "${task_id}" || ! -f "${POLICY_DB_FILE}" ]]; then
    return 1
  fi
  "${PYTHON_BIN}" - "${POLICY_DB_FILE}" "${task_id}" <<'PY'
import sqlite3
import sys
from pathlib import Path

db_path = Path(sys.argv[1])
task_id = sys.argv[2]
if not db_path.exists():
    raise SystemExit(1)

conn = sqlite3.connect(str(db_path))
try:
    row = conn.execute("SELECT 1 FROM tasks WHERE task_id = ? LIMIT 1", (task_id,)).fetchone()
finally:
    conn.close()

raise SystemExit(0 if row else 1)
PY
}

policy_ensure_task() {
  local reason="$1"
  local requirement="$2"
  local result_output="$3"
  local acceptance="$4"
  local observable_outputs="${POLICY_OBSERVABLE_OUTPUTS:-${result_output}}"
  local acceptance_thresholds="${POLICY_ACCEPTANCE_THRESHOLDS:-${acceptance}}"
  local context_json=""

  if ! policy_enabled; then
    return 0
  fi

  policy_load_task_id
  if [[ -n "${POLICY_TASK_ID}" ]]; then
    if policy_task_exists "${POLICY_TASK_ID}"; then
      policy_save_task_id
      return 0
    fi
  fi

  POLICY_TASK_ID="${POLICY_TASK_ID:-wf-${RUN_ID}}"
  context_json="$(cat <<EOF
{"problem":"$(json_escape "${reason}")","location":"$(json_escape "${ROOT_DIR}/scripts/hardflow/hardflow-run.sh")","first_seen_at":"$(timestamp)","impact":"$(json_escape "workflow stage cannot proceed when policy gating blocks internal verification stages")","evidence":"$(json_escape "${observable_outputs}")","current_state":"$(json_escape "${reason}")","expected_state":"$(json_escape "${result_output}")","operation_path":"$(json_escape "${ROOT_DIR}/scripts/hardflow/hardflow-run.sh")","reproduction_steps":"$(json_escape "${requirement}")","scope":"hardflow-workflow-stage","constraints":"$(json_escape "internal hardflow orchestration stage; must remain executable without extra human clarification")","acceptance_criteria":"$(json_escape "${acceptance}")","full_background":"$(json_escape "${reason}")"}
EOF
)"
  policy_run "create-task-${POLICY_TASK_ID}" create-task \
    --task-id "${POLICY_TASK_ID}" \
    --task-type "workflow" \
    --reason "${reason}" \
    --source "hardflow" \
    --request-source "ai" \
    --priority "high" \
    --risk-level "low" \
    --pool "jobs" \
    --entry-agent "${POLICY_ENTRY_AGENT}" \
    --assignee "${POLICY_DISPATCHER_AGENT}" \
    --requirement "${requirement}" \
    --result-output "${result_output}" \
    --acceptance "${acceptance}" \
    --context-json "${context_json}" \
    --observable-outputs "${observable_outputs}" \
    --acceptance-thresholds "${acceptance_thresholds}" \
    --need-human-confirm "false" \
    --human-confirmed "true" \
    --actor "${POLICY_ACTOR}"
  policy_save_task_id
}

policy_pre_stage() {
  local stage="$1"
  local input_ref="${2:-}"
  local stage_agent=""
  if ! policy_enabled; then
    return 0
  fi
  stage_agent="$(policy_agent_for_stage "${stage}")"
  policy_ensure_task \
    "hardflow stage ${stage}" \
    "execute hardflow stage ${stage}" \
    "stage ${stage} completed without policy violations" \
    "stage exit code = 0 and required gates pass"
  policy_run "pre-${stage}" pre-stage \
    --task-id "${POLICY_TASK_ID}" \
    --stage "${stage}" \
    --agent-id "${stage_agent}" \
    --model "${POLICY_MODEL}" \
    --input-ref "${input_ref}" \
    --actor "${POLICY_ACTOR}"
}

policy_post_stage() {
  local stage="$1"
  local exit_code="$2"
  local reason="${3:-}"
  local output_ref="${4:-}"
  if ! policy_enabled; then
    return 0
  fi
  policy_run "post-${stage}" post-stage \
    --task-id "${POLICY_TASK_ID}" \
    --stage "${stage}" \
    --exit-code "${exit_code}" \
    --reason "${reason}" \
    --output-ref "${output_ref}" \
    --actor "${POLICY_ACTOR}"
}

policy_record_token_minimal() {
  local usage_agent=""
  if ! policy_enabled; then
    return 0
  fi
  usage_agent="$(policy_agent_for_stage "git-push")"
  policy_run "record-token-${POLICY_TASK_ID}" record-token \
    --task-id "${POLICY_TASK_ID}" \
    --agent-id "${usage_agent}" \
    --model "${POLICY_MODEL}" \
    --input-tokens "${POLICY_USAGE_INPUT_TOKENS}" \
    --output-tokens "${POLICY_USAGE_OUTPUT_TOKENS}" || true
}

policy_complete() {
  if ! policy_enabled; then
    return 0
  fi
  policy_record_token_minimal
  policy_run "complete-${POLICY_TASK_ID}" complete-task \
    --task-id "${POLICY_TASK_ID}" \
    --result-score "${POLICY_RESULT_SCORE:-100}" \
    --stability-score "${POLICY_STABILITY_SCORE:-100}" \
    --critical-pass "${POLICY_CRITICAL_PASS:-true}" \
    --actor "${POLICY_ACTOR}"
}

write_gate() {
  local gate_name="$1"
  local passed="$2"
  local reason="$3"
  local safe_reason
  safe_reason="$(json_escape "${reason}")"
  cat > "${GATE_DIR}/${gate_name}.json" <<EOF
{"passed":${passed},"updated_at":"$(timestamp)","run_id":"${RUN_ID}","reason":"${safe_reason}"}
EOF
}

gate_passed() {
  local gate_name="$1"
  local gate_file="${GATE_DIR}/${gate_name}.json"
  [[ -f "${gate_file}" ]] && grep -Eq '"passed"[[:space:]]*:[[:space:]]*true' "${gate_file}"
}

gate_matches_run() {
  local gate_name="$1"
  local gate_file="${GATE_DIR}/${gate_name}.json"
  [[ -f "${gate_file}" ]] && grep -Eq "\"run_id\"[[:space:]]*:[[:space:]]*\"${RUN_ID}\"" "${gate_file}"
}

require_completion_verification() {
  local gate_name="completion_verification"
  local gate_file="${GATE_DIR}/${gate_name}.json"
  if [[ ! -f "${gate_file}" ]]; then
    log "ERROR" "git-push blocked: completion verification missing, run 'hardflow-run.sh verify-completion' first"
    return 1
  fi
  if ! gate_matches_run "${gate_name}"; then
    log "ERROR" "git-push blocked: completion verification is stale for current run_id=${RUN_ID}"
    return 1
  fi
  if ! gate_passed "${gate_name}"; then
    log "ERROR" "git-push blocked: completion verification failed, see ${gate_file}"
    return 1
  fi
  return 0
}

run_cmd_capture() {
  local label="$1"
  local cmd="$2"
  local log_file="$3"
  local required="${4:-1}"

  if [[ -z "${cmd}" ]]; then
    if [[ "${required}" == "1" ]]; then
      log "ERROR" "${label} is not configured, stage aborted"
      return 2
    fi
    log "WARN" "${label} is not configured, stage skipped"
    return 0
  fi

  mkdir -p "$(dirname "${log_file}")"
  log "INFO" "${label} => ${cmd}"

  set +e
  bash -lc "${cmd}" >"${log_file}" 2>&1
  local rc=$?
  set -e

  if [[ ${rc} -ne 0 ]]; then
    log "WARN" "${label} failed, rc=${rc}, log=${log_file}"
    return ${rc}
  fi

  return 0
}

score_gate_cmd_var() {
  case "$1" in
    requirements) printf '%s\n' "SCORE_REQUIREMENTS_CMD" ;;
    solution) printf '%s\n' "SCORE_SOLUTION_CMD" ;;
    frontend) printf '%s\n' "SCORE_FRONTEND_CMD" ;;
    backend) printf '%s\n' "SCORE_BACKEND_CMD" ;;
    security) printf '%s\n' "SCORE_SECURITY_CMD" ;;
    release) printf '%s\n' "SCORE_RELEASE_CMD" ;;
    final) printf '%s\n' "SCORE_FINAL_CMD" ;;
    *) return 1 ;;
  esac
}

improve_gate_cmd_var() {
  case "$1" in
    requirements) printf '%s\n' "IMPROVE_REQUIREMENTS_CMD" ;;
    solution) printf '%s\n' "IMPROVE_SOLUTION_CMD" ;;
    frontend) printf '%s\n' "IMPROVE_FRONTEND_CMD" ;;
    backend) printf '%s\n' "IMPROVE_BACKEND_CMD" ;;
    security) printf '%s\n' "IMPROVE_SECURITY_CMD" ;;
    release) printf '%s\n' "IMPROVE_RELEASE_CMD" ;;
    final) printf '%s\n' "IMPROVE_FINAL_CMD" ;;
    *) return 1 ;;
  esac
}

record_issue() {
  local stage="$1"
  local attempt="$2"
  local status="$3"
  local command="$4"
  local failure_reason="$5"
  local reproduce_steps="$6"
  local fix_command="$7"
  local fix_commit_before="$8"
  local fix_commit_after="$9"
  shift 9
  local regression_result="${1:-unknown}"
  local test_log="${2:-}"
  local fix_log="${3:-}"

  local issue_id
  issue_id="${RUN_ID}-${stage}-${attempt}-$(date +%s)"

  cat >> "${ISSUE_FILE}" <<EOF
{"schema_version":"${ISSUE_SCHEMA_VERSION}","issue_id":"$(json_escape "${issue_id}")","run_id":"$(json_escape "${RUN_ID}")","ts":"$(timestamp)","stage":"$(json_escape "${stage}")","attempt":${attempt},"status":"$(json_escape "${status}")","command":"$(json_escape "${command}")","failure_reason":"$(json_escape "${failure_reason}")","reproduce_steps":"$(json_escape "${reproduce_steps}")","fix_command":"$(json_escape "${fix_command}")","fix_commit_before":"$(json_escape "${fix_commit_before}")","fix_commit_after":"$(json_escape "${fix_commit_after}")","regression_result":"$(json_escape "${regression_result}")","test_log":"$(json_escape "${test_log}")","fix_log":"$(json_escape "${fix_log}")"}
EOF
}

cmd_classify() {
  local task=""
  local stage_rc=0

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --task)
        task="${2:-}"
        shift 2
        ;;
      *)
        log "WARN" "unknown arg: $1"
        shift
        ;;
    esac
  done

  if [[ -z "${task//[[:space:]]/}" ]]; then
    task="(empty)"
  fi

  refresh_progress_context "classify" "0"
  if ! ensure_atomic_task_json "${task}"; then
    return 2
  fi

  policy_run "route-classify" route-task --description "${task}" --source "hardflow" || true
  policy_ensure_task \
    "${task}" \
    "${task}" \
    "classification.json, gates, timeline logs" \
    "review/test/score gates passed"
  policy_pre_stage "classify" "${RUN_DIR}/classification.json"

  cat > "${RUN_DIR}/classification.json" <<EOF
{
  "run_id": "${RUN_ID}",
  "task": "$(printf '%s' "${task}" | sed 's/"/\\"/g')",
  "roles": ["coordinator", "frontend-dev", "backend-dev", "tester", "reviewer", "security-reviewer", "deployer", "doc-writer"],
  "created_at": "$(timestamp)"
}
EOF

  collect_dirty_files "${BASELINE_DIRTY_FILE}"
  save_git_savepoint "classify"

  policy_post_stage "classify" "${stage_rc}" "classification stage failed" "${RUN_DIR}/classification.json" || return $?
  log "INFO" "classification done, task='${task}'"
}

cmd_dispatch() {
  local stage_rc=0
  policy_pre_stage "dispatch" "${RUN_DIR}/dispatch.log"
  refresh_progress_context "dispatch" "0"
  if ! run_cmd_capture "DISPATCH_CMD" "${DISPATCH_CMD:-}" "${RUN_DIR}/dispatch.log" 0; then
    stage_rc=$?
  fi
  policy_post_stage "dispatch" "${stage_rc}" "dispatch stage failed" "${RUN_DIR}/dispatch.log" || return $?
  if [[ ${stage_rc} -ne 0 ]]; then
    return ${stage_rc}
  fi
  cat > "${RUN_DIR}/dispatch.json" <<EOF
{"run_id":"${RUN_ID}","dispatched_at":"$(timestamp)","status":"ok"}
EOF
  log "INFO" "dispatch stage done"
}

cmd_implement() {
  local stage_rc=0
  policy_pre_stage "implement" "${RUN_DIR}/implement.log"
  refresh_progress_context "implement" "0"
  if ! run_cmd_capture "IMPLEMENT_CMD" "${IMPLEMENT_CMD:-}" "${RUN_DIR}/implement.log" 0; then
    stage_rc=$?
  fi
  if [[ ${stage_rc} -eq 0 ]]; then
    if ! enforce_agent_write_scope "${POLICY_AGENT_IMPLEMENT}" "implement"; then
      stage_rc=$?
    fi
  fi
  policy_post_stage "implement" "${stage_rc}" "implement stage failed" "${RUN_DIR}/implement.log" || return $?
  if [[ ${stage_rc} -ne 0 ]]; then
    return ${stage_rc}
  fi
  log "INFO" "implement stage done"
}

cmd_test_loop() {
  local max_retries="${MAX_RETRIES:-3}"

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --max-retries)
        max_retries="${2:-3}"
        shift 2
        ;;
      *)
        shift
        ;;
    esac
  done

  if ! [[ "${max_retries}" =~ ^[0-9]+$ ]]; then
    log "ERROR" "max_retries must be a number"
    return 2
  fi

  policy_pre_stage "test-loop" "${RUN_DIR}/attempts"

  local attempt
  local passed=0

  for ((attempt=1; attempt<=max_retries; attempt++)); do
    local attempt_dir="${RUN_DIR}/attempt-${attempt}"
    local test_log="${attempt_dir}/test.log"
    local fix_log="${attempt_dir}/fix.log"
    mkdir -p "${attempt_dir}"
    refresh_progress_context "test-loop" "${attempt}"

    log "INFO" "test loop attempt ${attempt}/${max_retries}"
    if run_cmd_capture "TEST_CMD" "${TEST_CMD:-}" "${test_log}" 1; then
      passed=1
      policy_post_stage "test-loop" 0 "test loop passed" "${test_log}" || return $?
      log "INFO" "tests passed at attempt ${attempt}"
      break
    fi

    local fix_before
    local fix_after
    local regression_result
    fix_before="$(git_head)"
    fix_after="${fix_before}"
    regression_result="retry-pending"

    if (( attempt < max_retries )); then
      if run_cmd_capture "FIX_CMD" "${FIX_CMD:-}" "${fix_log}" 0; then
        fix_after="$(git_head)"
        if ! enforce_agent_write_scope "${POLICY_AGENT_IMPLEMENT}" "fix-attempt-${attempt}"; then
          {
            echo ""
            echo "[write-scope] violation detected after FIX_CMD"
          } >> "${fix_log}"
        fi
      fi
    else
      regression_result="retry-exhausted"
    fi

    policy_post_stage "test-loop" 1 "test command failed at attempt ${attempt}" "${test_log}" || return $?

    record_issue \
      "test-loop" \
      "${attempt}" \
      "failed" \
      "${TEST_CMD:-}" \
      "test command failed" \
      "run hardflow-run.sh test-loop --max-retries ${max_retries}" \
      "${FIX_CMD:-}" \
      "${fix_before}" \
      "${fix_after}" \
      "${regression_result}" \
      "${test_log}" \
      "${fix_log}"
  done

  if (( passed == 1 )); then
    write_gate "tester" "true" "test loop passed"
    return 0
  fi

  policy_post_stage "test-loop" 1 "test loop failed after retries" "${test_log:-}" || return $?
  write_gate "tester" "false" "test loop failed after retries"
  auto_git_reset_to_savepoint "test-loop-failed" || true
  log "ERROR" "test loop finished with failure"
  return 1
}

cmd_score_gate() {
  local gate=""
  local max_retries="${SCORE_MAX_RETRIES:-${MAX_RETRIES:-3}}"
  local source_scorecard=""
  local stage_name=""

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --gate)
        gate="${2:-}"
        shift 2
        ;;
      --max-retries)
        max_retries="${2:-3}"
        shift 2
        ;;
      --scorecard)
        source_scorecard="${2:-}"
        shift 2
        ;;
      *)
        shift
        ;;
    esac
  done

  if [[ -z "${gate}" ]]; then
    log "ERROR" "score-gate requires --gate"
    return 2
  fi

  if ! [[ "${max_retries}" =~ ^[0-9]+$ ]]; then
    log "ERROR" "score-gate max_retries must be a number"
    return 2
  fi

  stage_name="score-${gate}"
  policy_pre_stage "${stage_name}" "${RUN_DIR}/score-gates/${gate}"

  local score_var
  local improve_var
  score_var="$(score_gate_cmd_var "${gate}")" || {
    log "ERROR" "unknown score gate: ${gate}"
    return 2
  }
  improve_var="$(improve_gate_cmd_var "${gate}")" || {
    log "ERROR" "unknown score gate: ${gate}"
    return 2
  }

  local score_cmd="${!score_var:-}"
  local improve_cmd="${!improve_var:-}"
  local gate_file_final="${GATE_DIR}/score_${gate}.json"
  local passed=0
  local attempt

  for ((attempt=1; attempt<=max_retries; attempt++)); do
    local attempt_dir="${RUN_DIR}/score-gates/${gate}/attempt-${attempt}"
    local score_log="${attempt_dir}/score.log"
    local validation_log="${attempt_dir}/validation.log"
    local improve_log="${attempt_dir}/improve.log"
    local scorecard_file="${attempt_dir}/scorecard.json"
    local gate_file="${gate_file_final}"

    mkdir -p "${attempt_dir}" "${RUN_DIR}/scorecards"
    refresh_progress_context "${stage_name}" "${attempt}"

    log "INFO" "score gate '${gate}' attempt ${attempt}/${max_retries}"

    if [[ -n "${score_cmd}" ]]; then
      log "INFO" "${score_var} => ${score_cmd}"
      set +e
      SCORECARD_FILE="${scorecard_file}" HARD_FLOW_GATE="${gate}" bash -lc "${score_cmd}" >"${score_log}" 2>&1
      local score_rc=$?
      set -e
      if [[ ${score_rc} -ne 0 ]]; then
        log "WARN" "score command failed for gate='${gate}', rc=${score_rc}"
        local score_regression_result="retry-pending"
        if (( attempt >= max_retries )); then
          score_regression_result="retry-exhausted"
        fi
        record_issue \
          "score-${gate}" \
          "${attempt}" \
          "failed" \
          "${score_cmd}" \
          "score command failed" \
          "run hardflow-run.sh score-gate --gate ${gate} --max-retries ${max_retries}" \
          "${improve_cmd}" \
          "$(git_head)" \
          "$(git_head)" \
          "${score_regression_result}" \
          "${score_log}" \
          "${improve_log}"
      fi
    elif [[ -n "${source_scorecard}" && -f "${source_scorecard}" ]]; then
      cp "${source_scorecard}" "${scorecard_file}"
      log "INFO" "using provided scorecard for gate='${gate}': ${source_scorecard}"
    else
      log "ERROR" "score gate '${gate}' has no ${score_var} and no --scorecard input"
      write_gate "score_${gate}" "false" "missing score command and scorecard input"
      policy_post_stage "${stage_name}" 1 "missing score command and scorecard input" "${RUN_DIR}/score-gates/${gate}" || return $?
      return 2
    fi

    if [[ ! -s "${scorecard_file}" ]]; then
      log "WARN" "scorecard missing for gate='${gate}', file=${scorecard_file}"
      if (( attempt < max_retries )) && [[ -n "${improve_cmd}" ]]; then
        log "INFO" "${improve_var} => ${improve_cmd}"
        set +e
        HARD_FLOW_GATE="${gate}" bash -lc "${improve_cmd}" >"${improve_log}" 2>&1
        set -e
      fi
      continue
    fi

    set +e
    node "${SCRIPT_DIR}/check-score-gate.mjs" \
      --policy "${SCRIPT_DIR}/score-policy.json" \
      --gate "${gate}" \
      --scorecard "${scorecard_file}" \
      --output "${gate_file}" \
      --run-id "${RUN_ID}" \
      --audit-log "${RUN_DIR}/score-gate-audit.ndjson" >"${validation_log}" 2>&1
    local gate_rc=$?
    set -e

    if [[ ${gate_rc} -eq 0 ]]; then
      cp "${scorecard_file}" "${RUN_DIR}/scorecards/${gate}.json"
      passed=1
      policy_post_stage "${stage_name}" 0 "score gate passed" "${validation_log}" || return $?
      log "INFO" "score gate '${gate}' passed"
      cmd_score_report --gate "${gate}" --format text || true
      break
    fi

    log "WARN" "score gate '${gate}' failed, see ${validation_log}"
    local gate_regression_result="retry-pending"
    if (( attempt >= max_retries )); then
      gate_regression_result="retry-exhausted"
    fi

    record_issue \
      "score-${gate}" \
      "${attempt}" \
      "failed" \
      "${score_cmd}" \
      "score gate threshold not met" \
      "run hardflow-run.sh score-gate --gate ${gate} --max-retries ${max_retries}" \
      "${improve_cmd}" \
      "$(git_head)" \
      "$(git_head)" \
      "${gate_regression_result}" \
      "${validation_log}" \
      "${improve_log}"

    if (( attempt < max_retries )) && [[ -n "${improve_cmd}" ]]; then
      log "INFO" "${improve_var} => ${improve_cmd}"
      set +e
      HARD_FLOW_GATE="${gate}" bash -lc "${improve_cmd}" >"${improve_log}" 2>&1
      local improve_rc=$?
      set -e
      if [[ ${improve_rc} -ne 0 ]]; then
        log "WARN" "improve command failed for gate='${gate}', rc=${improve_rc}"
      fi
    fi
  done

  if (( passed == 1 )); then
    return 0
  fi

  if [[ ! -f "${gate_file_final}" ]]; then
    cat > "${gate_file_final}" <<EOF
{"passed":false,"updated_at":"$(timestamp)","run_id":"${RUN_ID}","gate":"${gate}","reason":"score gate '${gate}' failed after retries"}
EOF
  fi
  log "ERROR" "score gate '${gate}' failed after retries"
  policy_post_stage "${stage_name}" 1 "score gate failed after retries" "${RUN_DIR}/score-gates/${gate}" || return $?
  cmd_score_report --gate "${gate}" --format text || true
  return 1
}

cmd_score_all() {
  local max_retries="${SCORE_MAX_RETRIES:-${MAX_RETRIES:-3}}"

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --max-retries)
        max_retries="${2:-3}"
        shift 2
        ;;
      *)
        shift
        ;;
    esac
  done

  local gates=("requirements" "solution" "frontend" "backend" "security" "release" "final")
  local gate
  for gate in "${gates[@]}"; do
    cmd_score_gate --gate "${gate}" --max-retries "${max_retries}"
  done
}

run_hardflow_subcommand() {
  local label="$1"
  shift
  log "INFO" "workflow step '${label}'"
  bash "${SCRIPT_DIR}/hardflow-run.sh" "$@"
}

cmd_workflow() {
  local task=""
  local max_retries="${MAX_RETRIES:-3}"
  local score_max_retries="${SCORE_MAX_RETRIES:-${MAX_RETRIES:-3}}"

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --task)
        task="${2:-}"
        shift 2
        ;;
      --max-retries)
        max_retries="${2:-3}"
        shift 2
        ;;
      --score-max-retries)
        score_max_retries="${2:-3}"
        shift 2
        ;;
      *)
        shift
        ;;
    esac
  done

  if [[ -z "${task}" ]]; then
    log "ERROR" "workflow requires --task"
    return 2
  fi

  run_hardflow_subcommand "classify" classify --task "${task}"
  run_hardflow_subcommand "score-g0-requirements" score-gate --gate requirements --max-retries "${score_max_retries}"
  run_hardflow_subcommand "dispatch" dispatch
  run_hardflow_subcommand "score-g1-solution" score-gate --gate solution --max-retries "${score_max_retries}"
  run_hardflow_subcommand "implement" implement
  run_hardflow_subcommand "test-loop" test-loop --max-retries "${max_retries}"
  run_hardflow_subcommand "review" review
  run_hardflow_subcommand "score-g2-frontend" score-gate --gate frontend --max-retries "${score_max_retries}"
  run_hardflow_subcommand "score-g3-backend" score-gate --gate backend --max-retries "${score_max_retries}"
  run_hardflow_subcommand "score-g4-security" score-gate --gate security --max-retries "${score_max_retries}"
  log "INFO" "workflow step 'api-doc-gate'"
  bash "${SCRIPT_DIR}/check-api-doc-gate.sh"
  log "INFO" "workflow step 'quality-gate-predeploy'"
  bash "${SCRIPT_DIR}/check-review-test-gate.sh" --stage predeploy
  log "INFO" "workflow step 'preview-deploy'"
  bash "${SCRIPT_DIR}/preview-action.sh" deploy
  run_hardflow_subcommand "deploy" deploy
  if ! run_hardflow_subcommand "post-test" post-test; then
    log "ERROR" "post-test failed; workflow stopped before release/final gates"
    return 1
  fi
  run_hardflow_subcommand "score-g5-release" score-gate --gate release --max-retries "${score_max_retries}"
  run_hardflow_subcommand "score-g6-final" score-gate --gate final --max-retries "${score_max_retries}"
  log "INFO" "workflow step 'quality-gate-postdeploy'"
  bash "${SCRIPT_DIR}/check-review-test-gate.sh" --stage postdeploy
  if ! run_hardflow_subcommand "acceptance-test" acceptance-test; then
    log "ERROR" "acceptance-test failed; workflow stopped before completion verification"
    return 1
  fi
  if ! run_hardflow_subcommand "verify-completion" verify-completion; then
    log "ERROR" "verify-completion failed; workflow stopped before git-push"
    return 1
  fi
  log "INFO" "workflow step 'preview-git-push'"
  bash "${SCRIPT_DIR}/preview-action.sh" git-push
  run_hardflow_subcommand "git-push" git-push
  run_hardflow_subcommand "score-report" score-report --format text
}

cmd_score_report() {
  local gate=""
  local format="text"

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --gate)
        gate="${2:-}"
        shift 2
        ;;
      --format)
        format="${2:-text}"
        shift 2
        ;;
      *)
        shift
        ;;
    esac
  done

  local cmd=(node "${SCRIPT_DIR}/score-report.mjs" --workspace "${ROOT_DIR}" --run-id "${RUN_ID}" --format "${format}")
  if [[ -n "${gate}" ]]; then
    cmd+=(--gate "${gate}")
  fi
  "${cmd[@]}"
}

cmd_review() {
  local stage_rc=0
  policy_pre_stage "review" "${RUN_DIR}/review.log"
  refresh_progress_context "review" "0"
  if run_cmd_capture "REVIEW_CMD" "${REVIEW_CMD:-}" "${RUN_DIR}/review.log" 1; then
    policy_post_stage "review" 0 "review passed" "${RUN_DIR}/review.log" || return $?
    write_gate "reviewer" "true" "review passed"
    log "INFO" "review passed"
    return 0
  fi

  stage_rc=$?
  policy_post_stage "review" "${stage_rc}" "review failed" "${RUN_DIR}/review.log" || return $?
  write_gate "reviewer" "false" "review failed"
  log "ERROR" "review failed"
  return 1
}

cmd_deploy() {
  local stage_rc=0
  policy_pre_stage "deploy" "${RUN_DIR}/deploy.log"
  refresh_progress_context "deploy" "0"
  if ! run_cmd_capture "DEPLOY_CMD" "${DEPLOY_CMD:-}" "${RUN_DIR}/deploy.log" 1; then
    stage_rc=$?
  fi
  policy_post_stage "deploy" "${stage_rc}" "deploy stage failed" "${RUN_DIR}/deploy.log" || return $?
  if [[ ${stage_rc} -ne 0 ]]; then
    return ${stage_rc}
  fi
  log "INFO" "deploy stage done"
}

cmd_rollback_internal() {
  local reason="$1"

  if [[ -z "${ROLLBACK_CMD:-}" ]]; then
    if auto_git_reset_to_savepoint "manual-${reason}"; then
      return 0
    fi
    write_gate "rollback" "false" "rollback failed without ROLLBACK_CMD: ${reason}"
    return 1
  fi

  if run_cmd_capture "ROLLBACK_CMD" "${ROLLBACK_CMD:-}" "${RUN_DIR}/rollback.log" 1; then
    write_gate "rollback" "true" "rollback passed: ${reason}"
    log "INFO" "rollback done (${reason})"
    return 0
  fi

  write_gate "rollback" "false" "rollback failed: ${reason}"
  log "ERROR" "rollback failed (${reason})"
  return 1
}

cmd_post_test() {
  local cmd="${POST_TEST_CMD:-${TEST_CMD:-}}"
  local post_log="${RUN_DIR}/post-test.log"

  policy_pre_stage "post-test" "${post_log}"
  refresh_progress_context "post-test" "0"
  if run_cmd_capture "POST_TEST_CMD/TEST_CMD" "${cmd}" "${post_log}" 1; then
    policy_post_stage "post-test" 0 "post deploy test passed" "${post_log}" || return $?
    write_gate "post_tester" "true" "post deploy test passed"
    write_gate "rollback" "true" "rollback not required"
    log "INFO" "post deploy test passed"
    return 0
  fi

  policy_post_stage "post-test" 1 "post deploy test failed" "${post_log}" || return $?
  write_gate "post_tester" "false" "post deploy test failed"

  record_issue \
    "post-test" \
    "1" \
    "failed" \
    "${cmd}" \
    "post deploy test failed" \
    "run hardflow-run.sh post-test after deploy" \
    "${ROLLBACK_CMD:-}" \
    "$(git_head)" \
    "$(git_head)" \
    "manual-check-required" \
    "${post_log}" \
    "${RUN_DIR}/rollback.log"

  if [[ "${AUTO_ROLLBACK_ON_POST_TEST_FAIL:-1}" == "1" ]]; then
    log "WARN" "post deploy test failed, auto rollback enabled"
    cmd_rollback_internal "post-test-failed" || true
  else
    write_gate "rollback" "false" "rollback disabled after post-test failure"
    log "WARN" "post deploy test failed, auto rollback disabled"
  fi

  return 1
}

cmd_acceptance_test() {
  local acceptance_log="${RUN_DIR}/acceptance-test.log"
  local acceptance_artifact="${RUN_DIR}/acceptance/deployment.json"
  local stage_rc=0
  local stage_reason="deployment acceptance passed"

  policy_pre_stage "acceptance-test" "${acceptance_artifact}"
  refresh_progress_context "acceptance-test" "0"

  set +e
  bash "${SCRIPT_DIR}/check-deployment-acceptance.sh" >"${acceptance_log}" 2>&1
  stage_rc=$?
  set -e

  if [[ ${stage_rc} -ne 0 ]]; then
    stage_reason="deployment acceptance failed"
  fi

  policy_post_stage "acceptance-test" "${stage_rc}" "${stage_reason}" "${acceptance_artifact}" || return $?
  if [[ ${stage_rc} -ne 0 ]]; then
    log "ERROR" "deployment acceptance failed, see ${acceptance_log}"
    return ${stage_rc}
  fi

  log "INFO" "deployment acceptance passed"
}

cmd_verify_completion() {
  local verify_log="${RUN_DIR}/verify-completion.log"
  local verification_artifact="${RUN_DIR}/verification/completion.json"
  local stage_rc=0
  local stage_reason="completion verification passed"

  policy_pre_stage "verify-completion" "${verification_artifact}"
  refresh_progress_context "verify-completion" "0"

  set +e
  bash "${SCRIPT_DIR}/check-completion-verification.sh" >"${verify_log}" 2>&1
  stage_rc=$?
  set -e

  if [[ ${stage_rc} -ne 0 ]]; then
    stage_reason="completion verification failed"
  fi

  policy_post_stage "verify-completion" "${stage_rc}" "${stage_reason}" "${verification_artifact}" || return $?
  if [[ ${stage_rc} -ne 0 ]]; then
    log "ERROR" "completion verification failed, see ${verify_log}"
    return ${stage_rc}
  fi

  log "INFO" "completion verification passed"
}

cmd_rollback() {
  local reason="manual"

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --reason)
        reason="${2:-manual}"
        shift 2
        ;;
      *)
        shift
        ;;
    esac
  done

  cmd_rollback_internal "${reason}"
}

cmd_git_push() {
  local stage_rc=0
  require_completion_verification
  policy_pre_stage "git-push" "${RUN_DIR}/git-push.log"
  refresh_progress_context "git-push" "0"
  if ! run_cmd_capture "GIT_PUSH_CMD" "${GIT_PUSH_CMD:-}" "${RUN_DIR}/git-push.log" 1; then
    stage_rc=$?
  fi
  policy_post_stage "git-push" "${stage_rc}" "git push stage failed" "${RUN_DIR}/git-push.log" || return $?
  if [[ ${stage_rc} -ne 0 ]]; then
    return ${stage_rc}
  fi
  policy_complete || true
  log "INFO" "git push stage done"
}

policy_init_runtime

case "${SUBCOMMAND}" in
  workflow) cmd_workflow "$@" ;;
  classify) cmd_classify "$@" ;;
  dispatch) cmd_dispatch "$@" ;;
  implement) cmd_implement "$@" ;;
  test-loop) cmd_test_loop "$@" ;;
  score-gate) cmd_score_gate "$@" ;;
  score-all) cmd_score_all "$@" ;;
  score-report) cmd_score_report "$@" ;;
  review) cmd_review "$@" ;;
  deploy) cmd_deploy "$@" ;;
  post-test) cmd_post_test "$@" ;;
  acceptance-test) cmd_acceptance_test "$@" ;;
  verify-completion) cmd_verify_completion "$@" ;;
  rollback) cmd_rollback "$@" ;;
  git-push) cmd_git_push "$@" ;;
  *)
    usage
    exit 1
    ;;
esac
