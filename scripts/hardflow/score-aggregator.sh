#!/usr/bin/env bash
# scripts/hardflow/score-aggregator.sh
#
# 评分聚合器 — HardFlow 三步评分流水线的 Step 3
#
# 角色：纯确定性聚合，不调用任何 LLM / Agent。
# 输入：.workflow/runs/<run_id>/evidence/ 下的证据文件
# 输出：scorecard.json（符合 SCORECARD_SCHEMA.md 格式）
#
# 环境变量（由 hardflow-run.sh 设置）：
#   SCORECARD_FILE — 输出的 scorecard 路径
#   HARD_FLOW_GATE — 当前 gate 名称
#   HARD_FLOW_RUN_DIR — 当前 run 目录（含 evidence/）
#
# 用法：
#   SCORECARD_FILE=/tmp/sc.json HARD_FLOW_GATE=frontend \
#     bash scripts/hardflow/score-aggregator.sh
#
# 或直接传参：
#   bash scripts/hardflow/score-aggregator.sh <gate> <scorecard_file>

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# ─── 参数解析 ───────────────────────────────────────────
GATE="${1:-${HARD_FLOW_GATE:-}}"
SCORECARD_FILE="${2:-${SCORECARD_FILE:-}}"
RUN_DIR="${HARD_FLOW_RUN_DIR:-${ROOT_DIR}/.workflow/runs/current}"
EVIDENCE_DIR="${RUN_DIR}/evidence"
REVIEWER="${SCORE_REVIEWER:-reviewer}"
POLICY_FILE="${SCRIPT_DIR}/score-policy.json"

if [[ -z "${GATE}" || -z "${SCORECARD_FILE}" ]]; then
  echo "usage: score-aggregator.sh <gate> <scorecard_file>" >&2
  echo "  or set HARD_FLOW_GATE and SCORECARD_FILE env vars" >&2
  exit 2
fi

case "${GATE}" in
  requirements|solution|frontend|backend|refine|security|release|final) ;;
  *)
    echo "unknown gate: ${GATE}" >&2
    exit 2
    ;;
esac

mkdir -p "$(dirname "${SCORECARD_FILE}")" "${EVIDENCE_DIR}"
TS="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

# ─── 证据读取辅助函数 ─────────────────────────────────────

## 从 JSON 文件读取字段值，缺失时返回默认值
## 参数：$1=文件路径  $2=jq 表达式  $3=默认值
json_read() {
  local file="$1" expr="$2" default="${3:-0}"
  if [[ -f "${file}" ]]; then
    local val
    val="$(jq -r "${expr} // empty" "${file}" 2>/dev/null || true)"
    if [[ -n "${val}" && "${val}" != "null" ]]; then
      echo "${val}"
      return
    fi
  fi
  echo "${default}"
}

## 将浮点数四舍五入为整数并限制在 0-100 范围
clamp_score() {
  local val="$1"
  local int_val
  int_val="$(printf '%.0f' "${val}" 2>/dev/null || echo 0)"
  if (( int_val < 0 )); then int_val=0; fi
  if (( int_val > 100 )); then int_val=100; fi
  echo "${int_val}"
}

# ─── 检测可用证据 ──────────────────────────────────────

# 确定性证据
LINT_REPORT="${EVIDENCE_DIR}/lint-report.json"
TEST_RESULTS="${EVIDENCE_DIR}/test-results.json"
COVERAGE_REPORT="${EVIDENCE_DIR}/coverage-report.json"
BUILD_RESULT="${EVIDENCE_DIR}/build-result.json"
TYPECHECK_LOG="${EVIDENCE_DIR}/typecheck.json"
SECURITY_SCAN="${EVIDENCE_DIR}/security-scan.json"

# LLM 评价证据（由 reviewer 在 review 阶段产出）
REVIEW_EVIDENCE="${EVIDENCE_DIR}/review-evidence.json"

has_lint=false; [[ -f "${LINT_REPORT}" ]] && has_lint=true
has_test=false; [[ -f "${TEST_RESULTS}" ]] && has_test=true
has_coverage=false; [[ -f "${COVERAGE_REPORT}" ]] && has_coverage=true
has_build=false; [[ -f "${BUILD_RESULT}" ]] && has_build=true
has_typecheck=false; [[ -f "${TYPECHECK_LOG}" ]] && has_typecheck=true
has_security=false; [[ -f "${SECURITY_SCAN}" ]] && has_security=true
has_review=false; [[ -f "${REVIEW_EVIDENCE}" ]] && has_review=true

echo "[score-aggregator] gate=${GATE} evidence_dir=${EVIDENCE_DIR}"
echo "[score-aggregator] lint=${has_lint} test=${has_test} coverage=${has_coverage} build=${has_build} typecheck=${has_typecheck} security=${has_security} review=${has_review}"

# ─── 确定性分数计算 ─────────────────────────────────────

# lint 通过率 → 0-100 分
lint_score=0
lint_detail=""
if ${has_lint}; then
  lint_pass="$(json_read "${LINT_REPORT}" '.pass // .passed' 'false')"
  lint_warnings="$(json_read "${LINT_REPORT}" '.warnings // .warning_count' '0')"
  lint_errors="$(json_read "${LINT_REPORT}" '.errors // .error_count' '0')"
  if [[ "${lint_pass}" == "true" && "${lint_errors}" == "0" ]]; then
    lint_score=95
    if (( lint_warnings > 5 )); then lint_score=88; fi
    if (( lint_warnings > 10 )); then lint_score=82; fi
  elif [[ "${lint_errors}" == "0" ]]; then
    lint_score=80
  else
    lint_score=$(( 70 - lint_errors * 5 ))
    if (( lint_score < 20 )); then lint_score=20; fi
  fi
  lint_detail="pass=${lint_pass},warnings=${lint_warnings},errors=${lint_errors}"
fi

# 测试通过率 → 0-100 分
test_score=0
test_detail=""
if ${has_test}; then
  test_total="$(json_read "${TEST_RESULTS}" '.total // .tests_total' '0')"
  test_passed="$(json_read "${TEST_RESULTS}" '.passed // .tests_passed' '0')"
  test_failed="$(json_read "${TEST_RESULTS}" '.failed // .tests_failed' '0')"
  if (( test_total > 0 )); then
    pass_rate="$(echo "scale=4; ${test_passed} / ${test_total}" | bc 2>/dev/null || echo "0")"
    test_score="$(clamp_score "$(echo "scale=0; ${pass_rate} * 100" | bc 2>/dev/null || echo "0")")"
  fi
  test_detail="total=${test_total},passed=${test_passed},failed=${test_failed}"
fi

# 覆盖率 → 0-100 分
coverage_score=0
coverage_detail=""
if ${has_coverage}; then
  cov_pct="$(json_read "${COVERAGE_REPORT}" '.coverage // .line_coverage // .total_coverage' '0')"
  coverage_score="$(clamp_score "${cov_pct}")"
  coverage_detail="coverage=${cov_pct}%"
fi

# 构建结果 → 通过/失败
build_pass=false
if ${has_build}; then
  bp="$(json_read "${BUILD_RESULT}" '.success // .pass // .passed' 'false')"
  [[ "${bp}" == "true" ]] && build_pass=true
fi

# 类型检查 → 通过/失败
typecheck_pass=false
if ${has_typecheck}; then
  tp="$(json_read "${TYPECHECK_LOG}" '.pass // .passed // .success' 'false')"
  [[ "${tp}" == "true" ]] && typecheck_pass=true
fi

# ─── reviewer 评价读取 ─────────────────────────────────

# reviewer 的评价 JSON 预期格式：
# {
#   "dimensions": { "visual_design": 72, ... },
#   "deduction_reasons": { "visual_design": ["原因1", "原因2"] },
#   "summary": "..."
# }
review_dimensions="{}"
review_deductions="{}"
review_summary="no review evidence available"
review_findings="[]"
review_security_findings="[]"

if ${has_review}; then
  review_dimensions="$(jq -c '.dimensions // {}' "${REVIEW_EVIDENCE}" 2>/dev/null || echo '{}')"
  review_deductions="$(jq -c '.deduction_reasons // {}' "${REVIEW_EVIDENCE}" 2>/dev/null || echo '{}')"
  review_summary="$(json_read "${REVIEW_EVIDENCE}" '.summary' 'review evidence loaded')"
  review_findings="$(jq -c '.findings // []' "${REVIEW_EVIDENCE}" 2>/dev/null || echo '[]')"
  review_security_findings="$(jq -c '.security_findings // []' "${REVIEW_EVIDENCE}" 2>/dev/null || echo '[]')"
fi

# ─── 按 Gate 类型聚合分数 ──────────────────────────────

# 每个 Gate 的维度列表来自 score-policy.json，但聚合权重是这里定义的
# 原则：确定性检查有结果时优先用确定性分数；无证据时降级到 reviewer 评价；全无证据给 0 分

aggregate_dimension() {
  local dim="$1"
  local det_score="$2"      # 确定性分数（-1 = 无确定性数据）
  local det_weight="$3"     # 确定性权重 (0.0 - 1.0)

  local review_score
  review_score="$(echo "${review_dimensions}" | jq -r ".${dim} // -1" 2>/dev/null || echo "-1")"

  if [[ "${det_score}" != "-1" && "${review_score}" != "-1" ]]; then
    # 两方都有数据 → 加权
    local llm_weight
    llm_weight="$(echo "scale=2; 1 - ${det_weight}" | bc)"
    local result
    result="$(echo "scale=0; ${det_score} * ${det_weight} + ${review_score} * ${llm_weight}" | bc 2>/dev/null || echo "0")"
    clamp_score "${result}"
  elif [[ "${det_score}" != "-1" ]]; then
    # 只有确定性数据
    clamp_score "${det_score}"
  elif [[ "${review_score}" != "-1" ]]; then
    # 只有 reviewer 评价
    clamp_score "${review_score}"
  else
    # 无任何证据 → 不评分（给 0 让门禁拦截）
    echo "0"
  fi
}

# ─── 生成各 Gate 的 scorecard ─────────────────────────

generate_scorecard() {
  local gate="$1"
  local dims_json="{}"
  local deductions_json="${review_deductions}"
  local evidence_list="[]"
  local findings="${review_findings}"
  local sec_findings="${review_security_findings}"
  local det_sources="[]"

  case "${gate}" in
    requirements)
      # G0: 100% reviewer 评价（需求质量无确定性检查）
      local gc; gc="$(aggregate_dimension "goal_clarity" "-1" "0")"
      local sb; sb="$(aggregate_dimension "scope_boundary" "-1" "0")"
      local ac; ac="$(aggregate_dimension "acceptance_criteria" "-1" "0")"
      local cc; cc="$(aggregate_dimension "constraints_coverage" "-1" "0")"
      local ra; ra="$(aggregate_dimension "risk_analysis" "-1" "0")"
      dims_json="$(printf '{"goal_clarity":%s,"scope_boundary":%s,"acceptance_criteria":%s,"constraints_coverage":%s,"risk_analysis":%s}' "${gc}" "${sb}" "${ac}" "${cc}" "${ra}")"
      ;;
    solution)
      # G1: 100% reviewer 评价
      local fp; fp="$(aggregate_dimension "fit_for_problem" "-1" "0")"
      local fe; fe="$(aggregate_dimension "feasibility" "-1" "0")"
      local cx; cx="$(aggregate_dimension "complexity_control" "-1" "0")"
      local ae; ae="$(aggregate_dimension "alternatives_evaluation" "-1" "0")"
      local rm; rm="$(aggregate_dimension "risk_mitigation" "-1" "0")"
      dims_json="$(printf '{"fit_for_problem":%s,"feasibility":%s,"complexity_control":%s,"alternatives_evaluation":%s,"risk_mitigation":%s}' "${fp}" "${fe}" "${cx}" "${ae}" "${rm}")"
      ;;
    frontend)
      # G2: 确定性(lint/build) 40% + reviewer 60%
      local vd; vd="$(aggregate_dimension "visual_design" "-1" "0")"
      local ia; ia="$(aggregate_dimension "information_architecture" "-1" "0")"
      local iq; iq="$(aggregate_dimension "interaction_quality" "-1" "0")"
      local ra_fe; ra_fe="$(aggregate_dimension "responsive_accessibility" "-1" "0")"
      local cs
      if ${has_lint}; then
        cs="$(aggregate_dimension "code_structure" "${lint_score}" "0.4")"
      else
        cs="$(aggregate_dimension "code_structure" "-1" "0")"
      fi
      dims_json="$(printf '{"visual_design":%s,"information_architecture":%s,"interaction_quality":%s,"responsive_accessibility":%s,"code_structure":%s}' "${vd}" "${ia}" "${iq}" "${ra_fe}" "${cs}")"
      ;;
    backend)
      # G3: 确定性(typecheck/test) 40% + reviewer 60%
      local ad; ad="$(aggregate_dimension "architecture_design" "-1" "0")"
      local acq
      if ${has_typecheck} && ${typecheck_pass}; then
        acq="$(aggregate_dimension "api_contract_quality" "95" "0.3")"
      else
        acq="$(aggregate_dimension "api_contract_quality" "-1" "0")"
      fi
      local df; df="$(aggregate_dimension "data_flow_integrity" "-1" "0")"
      local ma; ma="$(aggregate_dimension "maintainability" "-1" "0")"
      local sc; sc="$(aggregate_dimension "scalability" "-1" "0")"
      dims_json="$(printf '{"architecture_design":%s,"api_contract_quality":%s,"data_flow_integrity":%s,"maintainability":%s,"scalability":%s}' "${ad}" "${acq}" "${df}" "${ma}" "${sc}")"
      ;;
    refine)
      # G3.5: reviewer 评价为主
      local eda; eda="$(aggregate_dimension "error_diagnosis_accuracy" "-1" "0")"
      local feff; feff="$(aggregate_dimension "fix_effectiveness" "-1" "0")"
      local rp; rp="$(aggregate_dimension "regression_prevention" "-1" "0")"
      local ec; ec="$(aggregate_dimension "experience_capture" "-1" "0")"
      local re; re="$(aggregate_dimension "retry_efficiency" "-1" "0")"
      dims_json="$(printf '{"error_diagnosis_accuracy":%s,"fix_effectiveness":%s,"regression_prevention":%s,"experience_capture":%s,"retry_efficiency":%s}' "${eda}" "${feff}" "${rp}" "${ec}" "${re}")"
      ;;
    security)
      # G4: 确定性扫描 + reviewer + veto
      local aa; aa="$(aggregate_dimension "authn_authz" "-1" "0")"
      local iv; iv="$(aggregate_dimension "input_validation" "-1" "0")"
      local sp; sp="$(aggregate_dimension "secrets_protection" "-1" "0")"
      local ds
      if ${has_security}; then
        local dep_vuln
        dep_vuln="$(json_read "${SECURITY_SCAN}" '.vulnerabilities // .total_vulnerabilities' '0')"
        local dep_score=$((95 - dep_vuln * 3))
        if (( dep_score < 30 )); then dep_score=30; fi
        ds="$(aggregate_dimension "dependency_security" "${dep_score}" "0.5")"
        # 从安全扫描中提取 findings
        local scan_findings
        scan_findings="$(jq -c '.findings // []' "${SECURITY_SCAN}" 2>/dev/null || echo '[]')"
        if [[ "${scan_findings}" != "[]" ]]; then
          sec_findings="${scan_findings}"
        fi
      else
        ds="$(aggregate_dimension "dependency_security" "-1" "0")"
      fi
      local au; au="$(aggregate_dimension "auditability" "-1" "0")"
      local pac; pac="$(aggregate_dimension "privileged_access_control" "-1" "0")"
      dims_json="$(printf '{"authn_authz":%s,"input_validation":%s,"secrets_protection":%s,"dependency_security":%s,"auditability":%s,"privileged_access_control":%s}' "${aa}" "${iv}" "${sp}" "${ds}" "${au}" "${pac}")"
      ;;
    release)
      # G5: 确定性(test/coverage) 70% + reviewer 30%
      local tc
      if ${has_coverage}; then
        tc="$(aggregate_dimension "test_coverage" "${coverage_score}" "0.7")"
      elif ${has_test}; then
        tc="$(aggregate_dimension "test_coverage" "${test_score}" "0.5")"
      else
        tc="$(aggregate_dimension "test_coverage" "-1" "0")"
      fi
      local rr
      if ${has_test}; then
        rr="$(aggregate_dimension "regression_result" "${test_score}" "0.7")"
      else
        rr="$(aggregate_dimension "regression_result" "-1" "0")"
      fi
      local dr; dr="$(aggregate_dimension "deployment_reliability" "-1" "0")"
      local rl; rl="$(aggregate_dimension "rollback_readiness" "-1" "0")"
      local ob; ob="$(aggregate_dimension "observability" "-1" "0")"
      dims_json="$(printf '{"test_coverage":%s,"regression_result":%s,"deployment_reliability":%s,"rollback_readiness":%s,"observability":%s}' "${tc}" "${rr}" "${dr}" "${rl}" "${ob}")"
      ;;
    final)
      # G6: 确定性 30% + reviewer 70%
      local crq; crq="$(aggregate_dimension "code_review_quality" "-1" "0")"
      local ps
      if ${has_test}; then
        ps="$(aggregate_dimension "production_smoke" "${test_score}" "0.3")"
      else
        ps="$(aggregate_dimension "production_smoke" "-1" "0")"
      fi
      local ms; ms="$(aggregate_dimension "metric_stability" "-1" "0")"
      local dc; dc="$(aggregate_dimension "documentation_completeness" "-1" "0")"
      local dcon; dcon="$(aggregate_dimension "deliverable_consistency" "-1" "0")"
      dims_json="$(printf '{"code_review_quality":%s,"production_smoke":%s,"metric_stability":%s,"documentation_completeness":%s,"deliverable_consistency":%s}' "${crq}" "${ps}" "${ms}" "${dc}" "${dcon}")"
      ;;
  esac

  # 计算 overall = 各维度平均分
  local overall
  overall="$(echo "${dims_json}" | jq '[to_entries[].value] | add / length | floor' 2>/dev/null || echo "0")"

  # 收集证据来源列表
  local sources=()
  ${has_lint} && sources+=("${LINT_REPORT}")
  ${has_test} && sources+=("${TEST_RESULTS}")
  ${has_coverage} && sources+=("${COVERAGE_REPORT}")
  ${has_build} && sources+=("${BUILD_RESULT}")
  ${has_typecheck} && sources+=("${TYPECHECK_LOG}")
  ${has_security} && sources+=("${SECURITY_SCAN}")
  ${has_review} && sources+=("${REVIEW_EVIDENCE}")

  evidence_list="$(printf '%s\n' "${sources[@]}" | jq -R . | jq -sc '.' 2>/dev/null || echo '[]')"

  # 确定性检查摘要
  det_sources="$(cat <<DETSRC
{
  "lint_pass": ${has_lint},
  "lint_score": ${lint_score},
  "lint_detail": "${lint_detail}",
  "test_score": ${test_score},
  "test_detail": "${test_detail}",
  "coverage_score": ${coverage_score},
  "coverage_detail": "${coverage_detail}",
  "build_pass": ${build_pass},
  "typecheck_pass": ${typecheck_pass}
}
DETSRC
)"

  # 输出最终 scorecard
  cat > "${SCORECARD_FILE}" <<SCORECARD
{
  "gate": "${gate}",
  "overall": ${overall},
  "reviewer": "${REVIEWER}",
  "summary": "${review_summary}",
  "dimensions": ${dims_json},
  "deduction_reasons": ${deductions_json},
  "evidence_sources": {
    "deterministic": ${det_sources},
    "llm_evaluation": {
      "evaluator_agent": "${REVIEWER}",
      "source_file": "${REVIEW_EVIDENCE}"
    }
  },
  "evidence": ${evidence_list},
  "findings": ${findings},
  "security_findings": ${sec_findings},
  "generated_at": "${TS}"
}
SCORECARD

  echo "[score-aggregator] scorecard written: ${SCORECARD_FILE} (gate=${gate}, overall=${overall})"
}

generate_scorecard "${GATE}"
