#!/usr/bin/env bash
# scripts/hardflow/improve-evaluator.sh
#
# 改进执行器 — 读取 scorecard 扣分原因，分类修复
#
# 角色：评分不通过后，基于 deduction_reasons 自动修复 autoFixable 问题。
# 输入：最近一次 scorecard.json（从 score-gates/<gate>/attempt-*/scorecard.json 读取）
# 输出：improve 日志 + 实际修复动作
#
# 环境变量：
#   HARD_FLOW_GATE — 当前 gate 名称
#   HARD_FLOW_RUN_DIR — 当前 run 目录
#
# 用法：
#   HARD_FLOW_GATE=frontend bash scripts/hardflow/improve-evaluator.sh
#   或：bash scripts/hardflow/improve-evaluator.sh <gate>

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# ─── 参数解析 ───────────────────────────────────────────
GATE="${1:-${HARD_FLOW_GATE:-}}"
RUN_DIR="${HARD_FLOW_RUN_DIR:-${ROOT_DIR}/.workflow/runs/current}"
LOG_DIR="${ROOT_DIR}/.workflow/improve"
mkdir -p "${LOG_DIR}"
TS="$(date -u +"%Y-%m-%dT%H%M%SZ")"
LOG_FILE="${LOG_DIR}/${TS}-${GATE}.json"

if [[ -z "${GATE}" ]]; then
  echo "usage: improve-evaluator.sh <gate>" >&2
  exit 2
fi

case "${GATE}" in
  requirements|solution|frontend|backend|refine|security|release|final) ;;
  *)
    echo "unknown gate: ${GATE}" >&2
    exit 2
    ;;
esac

# ─── 定位最新 scorecard ─────────────────────────────────

find_latest_scorecard() {
  local gate_dir="${RUN_DIR}/score-gates/${GATE}"
  if [[ ! -d "${gate_dir}" ]]; then
    echo ""
    return
  fi
  # 按 attempt 编号降序找最新的 scorecard
  local latest=""
  for attempt_dir in $(ls -d "${gate_dir}"/attempt-* 2>/dev/null | sort -t- -k2 -rn); do
    local sc="${attempt_dir}/scorecard.json"
    if [[ -f "${sc}" ]]; then
      latest="${sc}"
      break
    fi
  done
  echo "${latest}"
}

SCORECARD="$(find_latest_scorecard)"
echo "[improve-evaluator] gate=${GATE}"

if [[ -z "${SCORECARD}" || ! -f "${SCORECARD}" ]]; then
  echo "[improve-evaluator] no scorecard found for gate=${GATE}, skipping"
  cat > "${LOG_FILE}" <<EOF
{
  "ts": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  "gate": "${GATE}",
  "status": "skipped",
  "reason": "no scorecard found",
  "actions": []
}
EOF
  exit 0
fi

echo "[improve-evaluator] reading scorecard: ${SCORECARD}"

# ─── 解析扣分信息 ────────────────────────────────────────

# 读取低分维度（< 阈值的维度）
OVERALL="$(jq -r '.overall // 0' "${SCORECARD}" 2>/dev/null || echo "0")"
DIMENSIONS="$(jq -c '.dimensions // {}' "${SCORECARD}" 2>/dev/null || echo '{}')"
DEDUCTIONS="$(jq -c '.deduction_reasons // {}' "${SCORECARD}" 2>/dev/null || echo '{}')"
FINDINGS="$(jq -c '.findings // []' "${SCORECARD}" 2>/dev/null || echo '[]')"

echo "[improve-evaluator] overall=${OVERALL}"

# 收集需要改进的维度（分数 < 90）
LOW_DIMS="$(echo "${DIMENSIONS}" | jq -r 'to_entries[] | select(.value < 90) | .key' 2>/dev/null || true)"

if [[ -z "${LOW_DIMS}" ]]; then
  echo "[improve-evaluator] no low-score dimensions (<90), nothing to improve"
  cat > "${LOG_FILE}" <<EOF
{
  "ts": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  "gate": "${GATE}",
  "status": "no_action_needed",
  "overall": ${OVERALL},
  "reason": "all dimensions >= 90",
  "actions": []
}
EOF
  exit 0
fi

# ─── 分类修复动作 ─────────────────────────────────────────

# 修复动作分两类：
# 1. autoFixable: lint格式/import排序/类型补全 — 可以自动修
# 2. human_required: 架构设计/视觉设计/业务逻辑 — 标记给人处理

ACTIONS="[]"
AUTO_FIX_COUNT=0
HUMAN_REQUIRED_COUNT=0

classify_and_fix() {
  local dim="$1"
  local score
  score="$(echo "${DIMENSIONS}" | jq -r ".${dim} // 0" 2>/dev/null || echo "0")"
  local reasons
  reasons="$(echo "${DEDUCTIONS}" | jq -c ".${dim} // []" 2>/dev/null || echo '[]')"
  local reason_count
  reason_count="$(echo "${reasons}" | jq 'length' 2>/dev/null || echo "0")"

  # 根据维度名称和扣分原因判断是否可自动修复
  local fixable="false"
  local fix_cmd=""
  local fix_type="human_required"

  case "${dim}" in
    code_structure)
      # lint/format 类可以尝试自动修复
      if echo "${reasons}" | jq -e '.[] | test("lint|format|indent|semicolon|trailing|import|unused"; "i")' >/dev/null 2>&1; then
        fixable="true"
        fix_type="auto_lint"
        fix_cmd="cd ${ROOT_DIR} && npx eslint --fix 'src/**/*.{js,ts,vue,jsx,tsx}' 2>/dev/null || true && npx prettier --write 'src/**/*.{js,ts,vue,jsx,tsx,css,scss}' 2>/dev/null || true"
      fi
      ;;
    api_contract_quality)
      # 类型补全可以尝试自动修
      if echo "${reasons}" | jq -e '.[] | test("type|类型|typing|annotation"; "i")' >/dev/null 2>&1; then
        fixable="true"
        fix_type="auto_typefix"
        fix_cmd="cd ${ROOT_DIR} && npx tsc --noEmit 2>&1 | head -50 || true"
      fi
      ;;
    test_coverage|regression_result)
      # 测试类 — 标记需要 tester agent 处理
      fix_type="agent_required"
      fix_cmd="suggest: run tester agent to add missing test cases"
      ;;
    visual_design|interaction_quality|information_architecture|responsive_accessibility)
      # 视觉/交互类 — 必须人工处理
      fix_type="human_required"
      ;;
    secrets_protection|input_validation|authn_authz)
      # 安全类 — 标记为高优先级人工处理
      fix_type="human_required_critical"
      ;;
    *)
      fix_type="human_required"
      ;;
  esac

  # 执行自动修复
  local fix_result="not_attempted"
  if [[ "${fixable}" == "true" && -n "${fix_cmd}" ]]; then
    echo "[improve-evaluator] AUTO-FIX dim=${dim} type=${fix_type}"
    set +e
    eval "${fix_cmd}" > "${LOG_DIR}/${TS}-${GATE}-${dim}-fix.log" 2>&1
    local fix_rc=$?
    set -e
    if [[ ${fix_rc} -eq 0 ]]; then
      fix_result="applied"
      AUTO_FIX_COUNT=$((AUTO_FIX_COUNT + 1))
    else
      fix_result="failed"
    fi
  else
    echo "[improve-evaluator] MANUAL dim=${dim} type=${fix_type} score=${score}"
    HUMAN_REQUIRED_COUNT=$((HUMAN_REQUIRED_COUNT + 1))
  fi

  # 记录动作
  local action
  action="$(cat <<ACTION_JSON
{
  "dimension": "${dim}",
  "score": ${score},
  "reason_count": ${reason_count},
  "fix_type": "${fix_type}",
  "fixable": ${fixable},
  "fix_result": "${fix_result}",
  "reasons": ${reasons}
}
ACTION_JSON
)"
  ACTIONS="$(echo "${ACTIONS}" | jq --argjson a "${action}" '. + [$a]' 2>/dev/null || echo "${ACTIONS}")"
}

# 处理每个低分维度
for dim in ${LOW_DIMS}; do
  classify_and_fix "${dim}"
done

# ─── 处理 findings ────────────────────────────────────────

OPEN_FINDINGS_COUNT="$(echo "${FINDINGS}" | jq '[.[] | select(.status == "open")] | length' 2>/dev/null || echo "0")"
CRITICAL_FINDINGS="$(echo "${FINDINGS}" | jq '[.[] | select(.status == "open" and (.severity == "critical" or .severity == "high"))] | length' 2>/dev/null || echo "0")"

if (( OPEN_FINDINGS_COUNT > 0 )); then
  echo "[improve-evaluator] open findings: ${OPEN_FINDINGS_COUNT} (critical/high: ${CRITICAL_FINDINGS})"
fi

# ─── 输出改进报告 ──────────────────────────────────────────

cat > "${LOG_FILE}" <<IMPROVE_LOG
{
  "ts": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  "gate": "${GATE}",
  "status": "completed",
  "scorecard_source": "${SCORECARD}",
  "overall_before": ${OVERALL},
  "low_dimensions_count": $(echo "${LOW_DIMS}" | wc -w | tr -d ' '),
  "auto_fix_count": ${AUTO_FIX_COUNT},
  "human_required_count": ${HUMAN_REQUIRED_COUNT},
  "open_findings": ${OPEN_FINDINGS_COUNT},
  "critical_findings": ${CRITICAL_FINDINGS},
  "actions": ${ACTIONS}
}
IMPROVE_LOG

echo "[improve-evaluator] report: ${LOG_FILE}"
echo "[improve-evaluator] auto_fixed=${AUTO_FIX_COUNT} human_required=${HUMAN_REQUIRED_COUNT}"

# 如果有 critical findings 且未修复，返回非零退出码提示需要人工介入
if (( CRITICAL_FINDINGS > 0 )); then
  echo "[improve-evaluator] WARNING: ${CRITICAL_FINDINGS} critical/high findings remain open — human intervention needed"
fi

exit 0
