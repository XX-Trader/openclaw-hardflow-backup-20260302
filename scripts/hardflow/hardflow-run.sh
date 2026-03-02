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
POLICY_AGENT_ID="${POLICY_AGENT_ID:-coordinator}"
POLICY_MODEL="${POLICY_MODEL:-glmcode/glm-5}"

timestamp() {
  date -u +"%Y-%m-%dT%H:%M:%SZ"
}

usage() {
  cat <<'EOF'
Usage:
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

policy_enabled() {
  [[ "${POLICY_ENFORCER_ENABLED}" == "1" ]] && [[ -f "${POLICY_ENFORCER_PY}" ]]
}

policy_log_file() {
  local label="$1"
  printf '%s/policy-%s.log\n' "${RUN_DIR}" "${label//[^a-zA-Z0-9._-]/_}"
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
  python3 "${POLICY_ENFORCER_PY}" \
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

policy_ensure_task() {
  local reason="$1"
  local requirement="$2"
  local result_output="$3"
  local acceptance="$4"

  if ! policy_enabled; then
    return 0
  fi

  policy_load_task_id
  if [[ -n "${POLICY_TASK_ID}" ]]; then
    policy_save_task_id
    return 0
  fi

  POLICY_TASK_ID="wf-${RUN_ID}"
  policy_run "create-task-${POLICY_TASK_ID}" create-task \
    --task-id "${POLICY_TASK_ID}" \
    --task-type "workflow" \
    --reason "${reason}" \
    --source "hardflow" \
    --priority "high" \
    --risk-level "low" \
    --pool "jobs" \
    --assignee "${POLICY_AGENT_ID}" \
    --requirement "${requirement}" \
    --result-output "${result_output}" \
    --acceptance "${acceptance}" \
    --actor "${POLICY_ACTOR}"
  policy_save_task_id
}

policy_pre_stage() {
  local stage="$1"
  if ! policy_enabled; then
    return 0
  fi
  policy_ensure_task \
    "hardflow stage ${stage}" \
    "execute hardflow stage ${stage}" \
    "stage ${stage} completed without policy violations" \
    "stage exit code = 0 and required gates pass"
  policy_run "pre-${stage}" pre-stage \
    --task-id "${POLICY_TASK_ID}" \
    --stage "${stage}" \
    --agent-id "${POLICY_AGENT_ID}" \
    --model "${POLICY_MODEL}" \
    --actor "${POLICY_ACTOR}"
}

policy_post_stage() {
  local stage="$1"
  local exit_code="$2"
  local reason="${3:-}"
  if ! policy_enabled; then
    return 0
  fi
  policy_run "post-${stage}" post-stage \
    --task-id "${POLICY_TASK_ID}" \
    --stage "${stage}" \
    --exit-code "${exit_code}" \
    --reason "${reason}" \
    --actor "${POLICY_ACTOR}"
}

policy_complete() {
  if ! policy_enabled; then
    return 0
  fi
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

  policy_run "route-classify" route-task --description "${task}" --source "hardflow" || true
  policy_ensure_task \
    "${task}" \
    "${task}" \
    "classification.json, gates, timeline logs" \
    "review/test/score gates passed"
  policy_pre_stage "classify"

  cat > "${RUN_DIR}/classification.json" <<EOF
{
  "run_id": "${RUN_ID}",
  "task": "$(printf '%s' "${task}" | sed 's/"/\\"/g')",
  "roles": ["coordinator", "frontend-dev", "backend-dev", "tester", "reviewer", "security-reviewer", "deployer", "doc-writer"],
  "created_at": "$(timestamp)"
}
EOF

  if git -C "${ROOT_DIR}" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    {
      git -C "${ROOT_DIR}" diff --name-only --cached 2>/dev/null || true
      git -C "${ROOT_DIR}" diff --name-only 2>/dev/null || true
    } | sed '/^[[:space:]]*$/d' | sort -u > "${RUN_DIR}/baseline_dirty_files.txt"
  fi

  policy_post_stage "classify" "${stage_rc}" "classification stage failed" || return $?
  log "INFO" "classification done, task='${task}'"
}

cmd_dispatch() {
  local stage_rc=0
  policy_pre_stage "dispatch"
  if ! run_cmd_capture "DISPATCH_CMD" "${DISPATCH_CMD:-}" "${RUN_DIR}/dispatch.log" 0; then
    stage_rc=$?
  fi
  policy_post_stage "dispatch" "${stage_rc}" "dispatch stage failed" || return $?
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
  policy_pre_stage "implement"
  if ! run_cmd_capture "IMPLEMENT_CMD" "${IMPLEMENT_CMD:-}" "${RUN_DIR}/implement.log" 0; then
    stage_rc=$?
  fi
  policy_post_stage "implement" "${stage_rc}" "implement stage failed" || return $?
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

  policy_pre_stage "test-loop"

  local attempt
  local passed=0

  for ((attempt=1; attempt<=max_retries; attempt++)); do
    local attempt_dir="${RUN_DIR}/attempt-${attempt}"
    local test_log="${attempt_dir}/test.log"
    local fix_log="${attempt_dir}/fix.log"
    mkdir -p "${attempt_dir}"

    log "INFO" "test loop attempt ${attempt}/${max_retries}"
    if run_cmd_capture "TEST_CMD" "${TEST_CMD:-}" "${test_log}" 1; then
      passed=1
      policy_post_stage "test-loop" 0 "test loop passed" || return $?
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
      fi
    else
      regression_result="retry-exhausted"
    fi

    policy_post_stage "test-loop" 1 "test command failed at attempt ${attempt}" || return $?

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

  policy_post_stage "test-loop" 1 "test loop failed after retries" || return $?
  write_gate "tester" "false" "test loop failed after retries"
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
  policy_pre_stage "${stage_name}"

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
      policy_post_stage "${stage_name}" 1 "missing score command and scorecard input" || return $?
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
      policy_post_stage "${stage_name}" 0 "score gate passed" || return $?
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
  policy_post_stage "${stage_name}" 1 "score gate failed after retries" || return $?
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
  policy_pre_stage "review"
  if run_cmd_capture "REVIEW_CMD" "${REVIEW_CMD:-}" "${RUN_DIR}/review.log" 1; then
    policy_post_stage "review" 0 "review passed" || return $?
    write_gate "reviewer" "true" "review passed"
    log "INFO" "review passed"
    return 0
  fi

  stage_rc=$?
  policy_post_stage "review" "${stage_rc}" "review failed" || return $?
  write_gate "reviewer" "false" "review failed"
  log "ERROR" "review failed"
  return 1
}

cmd_deploy() {
  local stage_rc=0
  policy_pre_stage "deploy"
  if ! run_cmd_capture "DEPLOY_CMD" "${DEPLOY_CMD:-}" "${RUN_DIR}/deploy.log" 1; then
    stage_rc=$?
  fi
  policy_post_stage "deploy" "${stage_rc}" "deploy stage failed" || return $?
  if [[ ${stage_rc} -ne 0 ]]; then
    return ${stage_rc}
  fi
  log "INFO" "deploy stage done"
}

cmd_rollback_internal() {
  local reason="$1"

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

  policy_pre_stage "post-test"
  if run_cmd_capture "POST_TEST_CMD/TEST_CMD" "${cmd}" "${post_log}" 1; then
    policy_post_stage "post-test" 0 "post deploy test passed" || return $?
    write_gate "post_tester" "true" "post deploy test passed"
    write_gate "rollback" "true" "rollback not required"
    log "INFO" "post deploy test passed"
    return 0
  fi

  policy_post_stage "post-test" 1 "post deploy test failed" || return $?
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
  policy_pre_stage "git-push"
  if ! run_cmd_capture "GIT_PUSH_CMD" "${GIT_PUSH_CMD:-}" "${RUN_DIR}/git-push.log" 1; then
    stage_rc=$?
  fi
  policy_post_stage "git-push" "${stage_rc}" "git push stage failed" || return $?
  if [[ ${stage_rc} -ne 0 ]]; then
    return ${stage_rc}
  fi
  policy_complete || true
  log "INFO" "git push stage done"
}

policy_init_runtime

case "${SUBCOMMAND}" in
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
  rollback) cmd_rollback "$@" ;;
  git-push) cmd_git_push "$@" ;;
  *)
    usage
    exit 1
    ;;
esac
