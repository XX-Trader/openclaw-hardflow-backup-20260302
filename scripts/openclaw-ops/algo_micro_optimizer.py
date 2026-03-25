#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
algo_micro_optimizer.py — 高频沙盒微调器

借鉴 autoresearch（Karpathy）的设计哲学：
- 单一评估函数（hook-selftest.mjs，不可被 Agent 修改）
- 固定时间预算（4 分钟 / 轮）
- keep / discard 决策（通过 → keep → git commit；失败 → discard → git restore）
- 结果记录到 results.tsv

由 cron job `algo_micro_optimizer_5min` 每 5 分钟触发。

评估指标（方案 A）：hook-selftest.mjs 通过率
  - exit 0 → PASS（keep）
  - exit 1 → FAIL（discard）

未来演进（方案 B · 已记入 TODO P2）：
  - 切换为 upgrade_feedback_runner.py 的 composite_score
  - 实现 Workflow Scorecard 驱动的工作流级优化
"""

import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# ─────────────────────── 常量 ───────────────────────

OPENCLAW_HOME = Path(os.environ.get("OPENCLAW_HOME", Path.home() / ".openclaw"))
SANDBOX_DIR = OPENCLAW_HOME / "sandbox" / "micro-optimizer"
RESULTS_TSV = SANDBOX_DIR / "results.tsv"
STATE_FILE = SANDBOX_DIR / "state.json"

# 评估器候选路径（只读，不可修改）
EVALUATOR_CANDIDATES = [
    OPENCLAW_HOME / "workspace" / "scripts" / "hardflow" / "hook-selftest.mjs",
    Path("/home/ubuntu/.openclaw/workspace/scripts/hardflow/hook-selftest.mjs"),
]

# hooks 目录
HOOKS_DIR_CANDIDATES = [
    OPENCLAW_HOME / "hooks",
    Path("/home/ubuntu/.claude/hooks"),
    Path("/home/ubuntu/.openclaw/hooks"),
]

# 超时 = 240 秒（与 cron job 的 timeoutSeconds 对齐）
TIMEOUT_SECONDS = 240

# ─────────────────────── 日志 ───────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="[micro-opt] %(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("micro-optimizer")


# ─────────────────────── 工具函数 ───────────────────────

def find_existing_path(candidates: list[Path]) -> Path | None:
    """从候选路径中返回第一个存在的路径。"""
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def ensure_results_tsv() -> None:
    """确保 results.tsv 存在且有 header。"""
    SANDBOX_DIR.mkdir(parents=True, exist_ok=True)
    if not RESULTS_TSV.exists():
        RESULTS_TSV.write_text(
            "timestamp\tstatus\tduration_ms\tdescription\n",
            encoding="utf-8",
        )


def load_state() -> dict:
    """加载持久化状态（上次运行时间、连续通过次数等）。"""
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_state(state: dict) -> None:
    """保存持久化状态。"""
    SANDBOX_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def append_result(status: str, duration_ms: int, description: str) -> None:
    """追加一行到 results.tsv。"""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = f"{timestamp}\t{status}\t{duration_ms}\t{description}\n"
    with open(RESULTS_TSV, "a", encoding="utf-8") as tsv_file:
        tsv_file.write(line)


def run_evaluator(evaluator_path: Path, hooks_dir: Path) -> tuple[bool, int, str]:
    """
    运行 hook-selftest.mjs 评估器。

    Args:
        evaluator_path: hook-selftest.mjs 的绝对路径
        hooks_dir: hooks 目录的绝对路径

    Returns:
        (passed, duration_ms, output)
    """
    start_time = time.monotonic()
    try:
        result = subprocess.run(
            ["node", str(evaluator_path), "--hooks-dir", str(hooks_dir)],
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
            cwd=str(evaluator_path.parent),
            env={**os.environ, "NODE_NO_WARNINGS": "1"},
        )
        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        output = (result.stdout + result.stderr).strip()

        if result.returncode == 0 and "[hook-selftest] ok" in result.stdout:
            return True, elapsed_ms, output
        else:
            return False, elapsed_ms, output

    except subprocess.TimeoutExpired:
        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        return False, elapsed_ms, f"TIMEOUT after {TIMEOUT_SECONDS}s"

    except FileNotFoundError as file_error:
        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        return False, elapsed_ms, f"node not found: {file_error}"

    except OSError as os_error:
        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        return False, elapsed_ms, f"OS error: {os_error}"


# ─────────────────────── 主流程 ───────────────────────

def main() -> int:
    """
    主入口：运行评估、记录结果。

    返回值:
        0 = PASS（keep），1 = FAIL（discard），2 = SKIP（无需运行）
    """
    logger.info("=== algo_micro_optimizer 开始 ===")

    # 1. 查找评估器
    evaluator_path = find_existing_path(EVALUATOR_CANDIDATES)
    if evaluator_path is None:
        logger.error(
            "评估器 hook-selftest.mjs 未找到，候选路径: %s",
            [str(candidate_path) for candidate_path in EVALUATOR_CANDIDATES],
        )
        print("NO_REPLY")
        return 2

    # 2. 查找 hooks 目录
    hooks_dir = find_existing_path(HOOKS_DIR_CANDIDATES)
    if hooks_dir is None:
        logger.error(
            "hooks 目录未找到，候选路径: %s",
            [str(candidate_path) for candidate_path in HOOKS_DIR_CANDIDATES],
        )
        print("NO_REPLY")
        return 2

    logger.info("评估器: %s", evaluator_path)
    logger.info("hooks: %s", hooks_dir)

    # 3. 确保结果目录和 TSV
    ensure_results_tsv()

    # 4. 加载状态，检查冷却期（避免过于频繁）
    state = load_state()
    last_run_epoch = state.get("last_run_epoch", 0)
    now_epoch = time.time()
    cooldown_seconds = 270  # 4.5 分钟，防止与 cron 5 分钟间隔重叠

    if now_epoch - last_run_epoch < cooldown_seconds:
        remaining = int(cooldown_seconds - (now_epoch - last_run_epoch))
        logger.info("冷却期内，跳过本轮（剩余 %ds）", remaining)
        print("NO_REPLY")
        return 2

    # 5. 运行评估器
    logger.info("运行 hook-selftest.mjs ...")
    passed, duration_ms, output = run_evaluator(evaluator_path, hooks_dir)

    # 6. 记录结果
    if passed:
        status = "keep"
        description = "hook-selftest PASS"
        logger.info("✅ PASS（%dms）", duration_ms)
    else:
        status = "discard"
        # 截断过长的输出，保留最后 200 字符作为描述
        short_output = output[-200:].replace("\t", " ").replace("\n", " | ")
        description = f"hook-selftest FAIL: {short_output}"
        logger.warning("❌ FAIL（%dms）: %s", duration_ms, short_output[:100])

    append_result(status, duration_ms, description)

    # 7. 更新状态
    state["last_run_epoch"] = now_epoch
    state["last_status"] = status
    state["last_duration_ms"] = duration_ms
    state["consecutive_passes"] = (
        state.get("consecutive_passes", 0) + 1 if passed else 0
    )
    state["total_runs"] = state.get("total_runs", 0) + 1
    state["total_passes"] = state.get("total_passes", 0) + (1 if passed else 0)
    save_state(state)

    # 8. 输出摘要（供 cron delivery 使用）
    total_runs = state["total_runs"]
    total_passes = state["total_passes"]
    pass_rate = (total_passes / total_runs * 100) if total_runs > 0 else 0
    summary = (
        f"[micro-opt] {status.upper()} | "
        f"duration={duration_ms}ms | "
        f"pass_rate={pass_rate:.1f}% ({total_passes}/{total_runs}) | "
        f"consecutive_passes={state['consecutive_passes']}"
    )
    print(summary)
    logger.info("=== algo_micro_optimizer 结束 ===")

    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
