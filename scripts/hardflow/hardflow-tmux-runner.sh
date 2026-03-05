#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
WORKFLOW_DIR="${ROOT_DIR}/.workflow"
TMUX_LOG_DIR="${WORKFLOW_DIR}/tmux"
SESSION_NAME="${HARD_FLOW_TMUX_SESSION:-hardflow-main}"
RUN_MODE="${HARD_FLOW_RUN_MODE:-direct}" # direct | lobster
TASK="${HARD_FLOW_TASK:-manual-task}"
MAX_RETRIES="${MAX_RETRIES:-3}"
ALERT_CMD="${ALERT_CMD:-}"
LOBSTER_RUN_CMD="${LOBSTER_RUN_CMD:-}"
UTF8_MODE="${HARD_FLOW_UTF8_MODE:-1}" # 1 | 0
UTF8_LANG="${HARD_FLOW_LANG:-C.UTF-8}"
UTF8_LC_ALL="${HARD_FLOW_LC_ALL:-${UTF8_LANG}}"
UTF8_LC_CTYPE="${HARD_FLOW_LC_CTYPE:-${UTF8_LANG}}"

usage() {
  cat <<'EOF'
Usage:
  hardflow-tmux-runner.sh start --task "task text" [--session NAME] [--mode direct|lobster]
  hardflow-tmux-runner.sh status [--session NAME]
  hardflow-tmux-runner.sh attach [--session NAME]
  hardflow-tmux-runner.sh stop [--session NAME]
  hardflow-tmux-runner.sh logs [--session NAME] [--lines N]

Env:
  HARD_FLOW_TMUX_SESSION
  HARD_FLOW_RUN_MODE          # direct | lobster
  HARD_FLOW_TASK
  MAX_RETRIES
  ALERT_CMD                   # optional command when workflow exits non-zero
  LOBSTER_RUN_CMD             # required when --mode lobster
  HARD_FLOW_UTF8_MODE         # 1 | 0, default 1
  HARD_FLOW_LANG              # default C.UTF-8
  HARD_FLOW_LC_ALL            # default follows HARD_FLOW_LANG
  HARD_FLOW_LC_CTYPE          # default follows HARD_FLOW_LANG
EOF
}

require_tmux() {
  if ! command -v tmux >/dev/null 2>&1; then
    echo "[hardflow-tmux] tmux is required"
    exit 1
  fi
}

session_exists() {
  tmux has-session -t "$1" >/dev/null 2>&1
}

subcmd="${1:-}"
if [[ -z "${subcmd}" ]]; then
  usage
  exit 1
fi
shift || true

lines=80
while [[ $# -gt 0 ]]; do
  case "$1" in
    --task)
      TASK="${2:-${TASK}}"
      shift 2
      ;;
    --session)
      SESSION_NAME="${2:-${SESSION_NAME}}"
      shift 2
      ;;
    --mode)
      RUN_MODE="${2:-${RUN_MODE}}"
      shift 2
      ;;
    --lines)
      lines="${2:-80}"
      shift 2
      ;;
    *)
      shift
      ;;
  esac
done

mkdir -p "${TMUX_LOG_DIR}"
ENTRY_SCRIPT="${TMUX_LOG_DIR}/${SESSION_NAME}.entry.sh"
SESSION_LOG="${TMUX_LOG_DIR}/${SESSION_NAME}.log"

case "${subcmd}" in
  start)
    require_tmux
    if session_exists "${SESSION_NAME}"; then
      echo "[hardflow-tmux] session already exists: ${SESSION_NAME}"
      exit 0
    fi

    if [[ "${RUN_MODE}" == "lobster" ]]; then
      if [[ -z "${LOBSTER_RUN_CMD}" ]]; then
        echo "[hardflow-tmux] LOBSTER_RUN_CMD is required when mode=lobster"
        exit 1
      fi
      RUN_CMD="${LOBSTER_RUN_CMD}"
    else
      RUN_CMD="bash scripts/hardflow/hardflow-run.sh classify --task \"${TASK}\" && bash scripts/hardflow/hardflow-run.sh score-gate --gate requirements --max-retries ${MAX_RETRIES} && bash scripts/hardflow/hardflow-run.sh dispatch && bash scripts/hardflow/hardflow-run.sh score-gate --gate solution --max-retries ${MAX_RETRIES} && bash scripts/hardflow/hardflow-run.sh implement && bash scripts/hardflow/hardflow-run.sh test-loop --max-retries ${MAX_RETRIES} && bash scripts/hardflow/hardflow-run.sh review && bash scripts/hardflow/hardflow-run.sh score-gate --gate frontend --max-retries ${MAX_RETRIES} && bash scripts/hardflow/hardflow-run.sh score-gate --gate backend --max-retries ${MAX_RETRIES} && bash scripts/hardflow/hardflow-run.sh score-gate --gate security --max-retries ${MAX_RETRIES} && bash scripts/hardflow/check-api-doc-gate.sh && bash scripts/hardflow/check-review-test-gate.sh --stage predeploy && bash scripts/hardflow/preview-action.sh deploy && bash scripts/hardflow/hardflow-run.sh deploy && (bash scripts/hardflow/hardflow-run.sh post-test || true) && bash scripts/hardflow/hardflow-run.sh score-gate --gate release --max-retries ${MAX_RETRIES} && bash scripts/hardflow/hardflow-run.sh score-gate --gate final --max-retries ${MAX_RETRIES} && bash scripts/hardflow/check-review-test-gate.sh --stage postdeploy && bash scripts/hardflow/preview-action.sh git-push && bash scripts/hardflow/hardflow-run.sh git-push && bash scripts/hardflow/hardflow-run.sh score-report --format text"
    fi

    cat > "${ENTRY_SCRIPT}" <<EOF
#!/usr/bin/env bash
set -euo pipefail
cd "${ROOT_DIR}"
if [[ "${UTF8_MODE}" == "1" ]]; then
  export LANG="${UTF8_LANG}"
  export LC_ALL="${UTF8_LC_ALL}"
  export LC_CTYPE="${UTF8_LC_CTYPE}"
  export PYTHONUTF8=1
  export PYTHONIOENCODING="\${PYTHONIOENCODING:-utf-8}"
  export LESSCHARSET="\${LESSCHARSET:-utf-8}"
fi
{
  echo "[hardflow-tmux] start: \\$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "[hardflow-tmux] mode=${RUN_MODE}, task=${TASK}, session=${SESSION_NAME}, utf8=${UTF8_MODE}"
  ${RUN_CMD}
  echo "[hardflow-tmux] done: \\$(date -u +%Y-%m-%dT%H:%M:%SZ)"
} >> "${SESSION_LOG}" 2>&1 || {
  rc=\\$?
  echo "[hardflow-tmux] failed rc=\\${rc}: \\$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "${SESSION_LOG}" 2>&1
  if [[ -n "${ALERT_CMD}" ]]; then
    bash -lc "${ALERT_CMD}" >> "${SESSION_LOG}" 2>&1 || true
  fi
  exit \\${rc}
}
EOF
    chmod +x "${ENTRY_SCRIPT}"

    tmux new-session -d -s "${SESSION_NAME}" "bash '${ENTRY_SCRIPT}'"
    echo "[hardflow-tmux] started session: ${SESSION_NAME}"
    echo "[hardflow-tmux] log: ${SESSION_LOG}"
    ;;

  status)
    require_tmux
    if session_exists "${SESSION_NAME}"; then
      echo "[hardflow-tmux] running: ${SESSION_NAME}"
      exit 0
    fi
    echo "[hardflow-tmux] not running: ${SESSION_NAME}"
    exit 1
    ;;

  attach)
    require_tmux
    tmux attach -t "${SESSION_NAME}"
    ;;

  stop)
    require_tmux
    if session_exists "${SESSION_NAME}"; then
      tmux kill-session -t "${SESSION_NAME}"
      echo "[hardflow-tmux] stopped: ${SESSION_NAME}"
      exit 0
    fi
    echo "[hardflow-tmux] session not found: ${SESSION_NAME}"
    exit 1
    ;;

  logs)
    if [[ -f "${SESSION_LOG}" ]]; then
      tail -n "${lines}" "${SESSION_LOG}"
      exit 0
    fi
    echo "[hardflow-tmux] log not found: ${SESSION_LOG}"
    exit 1
    ;;

  *)
    usage
    exit 1
    ;;
esac
