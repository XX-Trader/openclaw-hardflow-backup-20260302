#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
WORKFLOW_DIR="${ROOT_DIR}/.workflow"
STATE_FILE="${WORKFLOW_DIR}/current_run_id"
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

  log "INFO" "classification done, task='${task}'"
}

cmd_dispatch() {
  run_cmd_capture "DISPATCH_CMD" "${DISPATCH_CMD:-}" "${RUN_DIR}/dispatch.log" 0
  cat > "${RUN_DIR}/dispatch.json" <<EOF
{"run_id":"${RUN_ID}","dispatched_at":"$(timestamp)","status":"ok"}
EOF
  log "INFO" "dispatch stage done"
}

cmd_implement() {
  run_cmd_capture "IMPLEMENT_CMD" "${IMPLEMENT_CMD:-}" "${RUN_DIR}/implement.log" 0
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

  write_gate "tester" "false" "test loop failed after retries"
  log "ERROR" "test loop finished with failure"
  return 1
}

cmd_score_gate() {
  local gate=""
  local max_retries="${SCORE_MAX_RETRIES:-${MAX_RETRIES:-3}}"
  local source_scorecard=""

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
  if run_cmd_capture "REVIEW_CMD" "${REVIEW_CMD:-}" "${RUN_DIR}/review.log" 1; then
    write_gate "reviewer" "true" "review passed"
    log "INFO" "review passed"
    return 0
  fi

  write_gate "reviewer" "false" "review failed"
  log "ERROR" "review failed"
  return 1
}

cmd_deploy() {
  run_cmd_capture "DEPLOY_CMD" "${DEPLOY_CMD:-}" "${RUN_DIR}/deploy.log" 1
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

  if run_cmd_capture "POST_TEST_CMD/TEST_CMD" "${cmd}" "${post_log}" 1; then
    write_gate "post_tester" "true" "post deploy test passed"
    write_gate "rollback" "true" "rollback not required"
    log "INFO" "post deploy test passed"
    return 0
  fi

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
  run_cmd_capture "GIT_PUSH_CMD" "${GIT_PUSH_CMD:-}" "${RUN_DIR}/git-push.log" 1
  log "INFO" "git push stage done"
}

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
