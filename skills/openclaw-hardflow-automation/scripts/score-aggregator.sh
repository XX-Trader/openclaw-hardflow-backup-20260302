#!/usr/bin/env bash
# score-aggregator.sh — 确定性评分聚合器（无 LLM）
#
# 功能：扫描 evidence 目录下的 scorecard JSON，逐一调用 check-score-gate.mjs 校验
# 用法：score-aggregator.sh <run_dir>
# 示例：score-aggregator.sh .workflow/runs/20260401_120000
#
# 产出：
#   <run_dir>/gate-results/<gate>.json  — 每个 Gate 的判定结果
#   <run_dir>/aggregate-result.json     — 聚合总览
#   .workflow/audit/gate-audit.ndjson   — 审计日志追加
#
# 退出码：0=全部通过，1=有 Gate 失败，2=参数/环境错误
set -euo pipefail

RUN_DIR="${1:-}"
if [[ -z "${RUN_DIR}" ]]; then
  echo "usage: score-aggregator.sh <run_dir>" >&2
  echo "  run_dir: e.g. .workflow/runs/20260401_120000" >&2
  exit 2
fi

# 定位脚本目录（与此脚本同目录的 check-score-gate.mjs 和 score-policy.json）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHECKER="${SCRIPT_DIR}/check-score-gate.mjs"
POLICY="${SCRIPT_DIR}/score-policy.json"

if [[ ! -f "${CHECKER}" ]]; then
  echo "[aggregator] ERROR: check-score-gate.mjs not found at: ${CHECKER}" >&2
  exit 2
fi
if [[ ! -f "${POLICY}" ]]; then
  echo "[aggregator] ERROR: score-policy.json not found at: ${POLICY}" >&2
  exit 2
fi

SCORECARD_DIR="${RUN_DIR}/scorecards"
RESULT_DIR="${RUN_DIR}/gate-results"
AUDIT_LOG=".workflow/audit/gate-audit.ndjson"
RUN_ID="$(basename "${RUN_DIR}")"

mkdir -p "${RESULT_DIR}"
mkdir -p "$(dirname "${AUDIT_LOG}")"

# 可能的 Gate 名称列表（按执行顺序）
GATES=("requirements" "solution" "frontend" "backend" "refine" "security" "release" "final")

TOTAL=0
PASSED=0
FAILED=0
SKIPPED=0
FAILED_GATES=()

echo "[aggregator] run_id=${RUN_ID}"
echo "[aggregator] scorecard_dir=${SCORECARD_DIR}"
echo "[aggregator] policy=${POLICY}"
echo ""

for GATE in "${GATES[@]}"; do
  SCORECARD="${SCORECARD_DIR}/${GATE}.json"
  OUTPUT="${RESULT_DIR}/${GATE}.json"

  if [[ ! -f "${SCORECARD}" ]]; then
    echo "[aggregator] ${GATE}: SKIPPED (no scorecard)"
    SKIPPED=$((SKIPPED + 1))
    continue
  fi

  TOTAL=$((TOTAL + 1))

  # 调用确定性校验引擎
  set +e
  node "${CHECKER}" \
    --gate "${GATE}" \
    --scorecard "${SCORECARD}" \
    --policy "${POLICY}" \
    --output "${OUTPUT}" \
    --run-id "${RUN_ID}" \
    --audit-log "${AUDIT_LOG}"
  EXIT_CODE=$?
  set -e

  case ${EXIT_CODE} in
    0)
      echo "[aggregator] ${GATE}: PASS"
      PASSED=$((PASSED + 1))
      ;;
    1)
      echo "[aggregator] ${GATE}: FAIL"
      FAILED=$((FAILED + 1))
      FAILED_GATES+=("${GATE}")
      ;;
    *)
      echo "[aggregator] ${GATE}: ERROR (exit=${EXIT_CODE})"
      FAILED=$((FAILED + 1))
      FAILED_GATES+=("${GATE}")
      ;;
  esac
done

echo ""
echo "=========================================="
echo "[aggregator] SUMMARY"
echo "  total:   ${TOTAL}"
echo "  passed:  ${PASSED}"
echo "  failed:  ${FAILED}"
echo "  skipped: ${SKIPPED}"
if [[ ${FAILED} -gt 0 ]]; then
  echo "  failed_gates: ${FAILED_GATES[*]}"
fi
echo "=========================================="

# 写入聚合总览 JSON
TS="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
FAILED_GATES_JSON="[]"
if [[ ${FAILED} -gt 0 ]]; then
  FAILED_GATES_JSON=$(printf '"%s",' "${FAILED_GATES[@]}" | sed 's/,$//')
  FAILED_GATES_JSON="[${FAILED_GATES_JSON}]"
fi

cat > "${RUN_DIR}/aggregate-result.json" <<JSON
{
  "run_id": "${RUN_ID}",
  "aggregated_at": "${TS}",
  "total_gates": ${TOTAL},
  "passed": ${PASSED},
  "failed": ${FAILED},
  "skipped": ${SKIPPED},
  "failed_gates": ${FAILED_GATES_JSON},
  "all_passed": $([ ${FAILED} -eq 0 ] && echo "true" || echo "false"),
  "policy_file": "${POLICY}",
  "scorecard_dir": "${SCORECARD_DIR}"
}
JSON

echo "[aggregator] aggregate-result written: ${RUN_DIR}/aggregate-result.json"

if [[ ${FAILED} -gt 0 ]]; then
  exit 1
fi
exit 0
