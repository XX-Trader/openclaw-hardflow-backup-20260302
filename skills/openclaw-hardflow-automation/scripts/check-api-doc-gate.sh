#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="${HARDFLOW_REPO_ROOT:-}"
if [[ -z "${ROOT_DIR}" ]]; then
  ROOT_DIR="$(git -C "${SCRIPT_DIR}" rev-parse --show-toplevel 2>/dev/null || true)"
fi
if [[ -z "${ROOT_DIR}" ]]; then
  ROOT_DIR="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
fi
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

run_dir() {
  printf '%s/runs/%s\n' "${WORKFLOW_DIR}" "$(run_id)"
}

write_gate() {
  local passed="$1"
  local reason="$2"
  local safe_reason
  safe_reason="${reason//\"/\'}"
  cat > "${GATE_DIR}/api_doc.json" <<EOF
{"passed":${passed},"updated_at":"$(timestamp)","run_id":"$(run_id)","reason":"${safe_reason}"}
EOF
}

if ! git -C "${ROOT_DIR}" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "[api-doc-gate] current directory is not a git repository"
  write_gate "false" "not a git repository"
  exit 1
fi

BASE_REF="${BASE_REF:-}"

declare -a changed_files=()
mapfile -t changed_files < <(
  {
    git -C "${ROOT_DIR}" diff --name-only --cached 2>/dev/null || true
    git -C "${ROOT_DIR}" diff --name-only 2>/dev/null || true
  } | sed '/^[[:space:]]*$/d' | sort -u
)

if [[ ${#changed_files[@]} -eq 0 && -n "${BASE_REF}" ]]; then
  mapfile -t changed_files < <(git -C "${ROOT_DIR}" diff --name-only "${BASE_REF}...HEAD" 2>/dev/null || true)
fi

BASELINE_FILE="$(run_dir)/baseline_dirty_files.txt"
if [[ -f "${BASELINE_FILE}" && ${#changed_files[@]} -gt 0 ]]; then
  mapfile -t changed_files < <(
    printf '%s\n' "${changed_files[@]}" | sed '/^[[:space:]]*$/d' | grep -Fvx -f "${BASELINE_FILE}" || true
  )
fi

if [[ ${#changed_files[@]} -eq 0 ]]; then
  echo "[api-doc-gate] no changed files, gate passed"
  write_gate "true" "no file changed"
  exit 0
fi

api_changed=0
doc_changed=0
API_CODE_PATH_REGEX="${API_CODE_PATH_REGEX:-(^|/)(api|apis)(/.*|[._-].*\.(py|js|jsx|ts|tsx|go|rs|java|kt|rb|php|cs))$|(^|/)(backend|server|service|services)/(routes?|routers?|controllers?|views?|serializers?|handlers?)(/.*|[._-].*\.(py|js|jsx|ts|tsx|go|rs|java|kt|rb|php|cs))$}"
API_DOC_PATH_REGEX="${API_DOC_PATH_REGEX:-(^|/)docs/(api|openapi)(/|[._-])|(^|/)(openapi|swagger)\.(yaml|yml|json)$}"

for file in "${changed_files[@]}"; do
  if [[ "${file}" =~ ${API_CODE_PATH_REGEX} ]]; then
    api_changed=1
  fi
  if [[ "${file}" =~ ${API_DOC_PATH_REGEX} ]]; then
    doc_changed=1
  fi
done

if [[ "${ALLOW_API_DOC_SKIP:-0}" == "1" ]]; then
  echo "[api-doc-gate] ALLOW_API_DOC_SKIP=1, gate skipped"
  write_gate "true" "skipped by ALLOW_API_DOC_SKIP"
  exit 0
fi

if [[ "${api_changed}" -eq 1 && "${doc_changed}" -eq 0 ]]; then
  echo "[api-doc-gate] blocked: api-related code changed without api docs update"
  write_gate "false" "api changed without docs update"
  exit 1
fi

echo "[api-doc-gate] passed: api_changed=${api_changed}, doc_changed=${doc_changed}"
write_gate "true" "gate passed"
