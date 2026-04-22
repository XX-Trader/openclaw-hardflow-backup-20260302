#!/usr/bin/env python3
"""
项目交付优先工作流 — 端到端集成测试。
模拟一个简单任务，验证整条流水线各节点是否正常工作。
"""

from __future__ import annotations

import io
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

# Windows 控制台 UTF-8 编码修复
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def run(cmd: list[str], cwd: Path | None = None, check: bool = False) -> subprocess.CompletedProcess:
    """运行命令并返回结果。"""
    return subprocess.run(
        cmd,
        cwd=cwd or REPO_ROOT,
        capture_output=True,
        text=True,
        check=check,
    )


def check_step(name: str, proc: subprocess.CompletedProcess, expect_code: int = 0) -> bool:
    """检查命令执行结果。"""
    passed = proc.returncode == expect_code
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"  [{status}] {name} (exit={proc.returncode})")
    if not passed and proc.stderr:
        print(f"       stderr: {proc.stderr[:200]}")
    return passed


def test_failure_tracker() -> bool:
    """测试失败追踪器。"""
    print("\n📦 Step 1: failure_tracker")

    # 记录一次失败
    r1 = run([
        sys.executable, "scripts/openclaw-ops/failure_tracker.py",
        "record",
        "--task-id", "test-task-001",
        "--task-type", "solution-review",
        "--model", "gpt-5.4",
        "--failure-reason", "测试失败记录",
    ])
    ok1 = check_step("record failure", r1)

    # 查询
    r2 = run([
        sys.executable, "scripts/openclaw-ops/failure_tracker.py",
        "query", "--task-type", "solution-review", "--limit", "5",
    ])
    ok2 = check_step("query history", r2)

    # 检查触发
    r3 = run([
        sys.executable, "scripts/openclaw-ops/failure_tracker.py",
        "check", "--task-type", "solution-review",
    ])
    ok3 = check_step("check trigger", r3)
    if ok3:
        try:
            data = json.loads(r3.stdout)
            print(f"       triggered={data.get('triggered')}, consecutive={data.get('consecutive_failures')}")
        except json.JSONDecodeError:
            pass

    return ok1 and ok2 and ok3


def test_project_memory() -> bool:
    """测试项目记忆写入和注入。"""
    print("\n📦 Step 2: project_memory_writer + injector")

    test_key = "integration-test-project"

    # 写入项目画像
    r1 = run([
        sys.executable, "scripts/openclaw-ops/project_memory_writer.py",
        "--project-key", test_key,
        "--artifact-type", "profile",
        "--content", "# 测试项目\n\n这是一个集成测试项目。\n",
        "--source", "integration_test",
    ])
    ok1 = check_step("write project profile", r1)

    # 写入决策
    r2 = run([
        sys.executable, "scripts/openclaw-ops/project_memory_writer.py",
        "--project-key", test_key,
        "--artifact-type", "decision",
        "--content", "使用策略模式替代 if-else",
        "--source", "integration_test",
    ])
    ok2 = check_step("write decision", r2)

    # 注入记忆
    r3 = run([
        sys.executable, "scripts/openclaw-ops/project_memory_injector.py",
        "--project-key", test_key,
        "--session-id", "test-session-001",
        "--inject-level", "summary",
        "--output-format", "json",
    ])
    ok3 = check_step("inject memory", r3)
    if ok3:
        try:
            data = json.loads(r3.stdout)
            print(f"       status={data.get('status')}, files={data.get('injected_files')}")
        except json.JSONDecodeError:
            pass

    # 列出项目
    r4 = run([
        sys.executable, "scripts/openclaw-ops/project_memory_injector.py",
        "--list",
    ])
    ok4 = check_step("list projects", r4)

    return ok1 and ok2 and ok3 and ok4


def test_source_registry() -> bool:
    """测试来源注册表监控。"""
    print("\n📦 Step 3: source_registry_watcher")

    test_key = "integration-test-project"

    # 先写入一个 SOURCE_REGISTRY
    registry = {
        "project_key": test_key,
        "version": "1.0.0",
        "sources": [
            {
                "source_id": "test-docs",
                "provider_id": "test",
                "urls": {
                    "docs": "https://example.com/docs",
                    "changelog": "",
                    "repo": "",
                    "sdk": "",
                },
                "current_version": "1.0.0",
                "last_checked": "",
                "check_frequency": "weekly",
                "change_policy": "notify_only",
            }
        ],
    }
    reg_path = REPO_ROOT / ".workflow/project-memory" / test_key / "SOURCE_REGISTRY.json"
    reg_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8")

    # 运行 watcher
    r1 = run([
        sys.executable, "scripts/openclaw-ops/source_registry_watcher.py",
        "--project-key", test_key,
    ])
    ok1 = check_step("check source registry", r1)
    if ok1:
        try:
            data = json.loads(r1.stdout)
            print(f"       total={data.get('total_sources')}, changed={data.get('changed')}")
        except json.JSONDecodeError:
            pass

    return ok1


def test_review_gate() -> bool:
    """测试审查门禁。"""
    print("\n📦 Step 4: review_gate_enforcer")

    reviews_dir = REPO_ROOT / ".workflow/reviews" / "test-task-001"
    reviews_dir.mkdir(parents=True, exist_ok=True)

    # 测试放行
    consensus_pass = """## 联合结论

### 最终裁决
- 裁决：ready_for_implement
- 置信度：high

### 分歧标记
- 是否存在分歧：否
"""
    (reviews_dir / "consensus.md").write_text(consensus_pass, encoding="utf-8")

    r1 = run([
        sys.executable, "scripts/openclaw-ops/policy/review_gate_enforcer.py",
        "--task-id", "test-task-001",
        "--review-type", "solution",
        "--review-path", str(reviews_dir / "consensus.md"),
        "--expected-verdict", "ready_for_implement",
    ])
    ok1 = check_step("gate allow (pass)", r1, expect_code=0)

    # 测试阻断
    consensus_block = """## 联合结论

### 最终裁决
- 裁决：requires_revision
- 置信度：medium

### 分歧标记
- 是否存在分歧：是
- 分歧点：A 认为可以通过，B 认为需要补充性能估算
"""
    (reviews_dir / "consensus.md").write_text(consensus_block, encoding="utf-8")

    r2 = run([
        sys.executable, "scripts/openclaw-ops/policy/review_gate_enforcer.py",
        "--task-id", "test-task-001",
        "--review-type", "solution",
        "--review-path", str(reviews_dir / "consensus.md"),
    ])
    ok2 = check_step("gate block (requires_revision)", r2, expect_code=1)
    if ok2:
        try:
            data = json.loads(r2.stdout)
            print(f"       error_code={data.get('error_code')}, next_action={data.get('next_action')}")
        except json.JSONDecodeError:
            pass

    # 测试缺少文件
    r3 = run([
        sys.executable, "scripts/openclaw-ops/policy/review_gate_enforcer.py",
        "--task-id", "test-task-002",
        "--review-type", "requirements",
        "--review-path", ".workflow/reviews/test-task-002/consensus.md",
    ])
    ok3 = check_step("gate block (missing review)", r3, expect_code=1)

    return ok1 and ok2 and ok3


def test_dual_ai_review_templates() -> bool:
    """测试审查模板文件是否存在。"""
    print("\n📦 Step 5: dual-ai-review templates")

    templates = [
        "skills/library/dual-ai-review/SKILL.md",
        "skills/library/dual-ai-review/templates/requirements_review.md",
        "skills/library/dual-ai-review/templates/solution_review.md",
        "skills/library/dual-ai-review/templates/code_review.md",
        "skills/library/dual-ai-review/references/review-gate-contract.md",
        "skills/library/dual-ai-review/references/consensus-rules.md",
    ]

    all_ok = True
    for tmpl in templates:
        path = REPO_ROOT / tmpl
        ok = path.exists()
        status = "✅ PASS" if ok else "❌ FAIL"
        print(f"  [{status}] {tmpl}")
        if not ok:
            all_ok = False

    return all_ok


def test_project_delivery_skills() -> bool:
    """测试项目交付相关 Skill 文件。"""
    print("\n📦 Step 6: project delivery skills")

    skills = [
        "skills/library/failure-learning/SKILL.md",
        "skills/library/project-profile-manager/SKILL.md",
        "skills/library/project-profile-manager/templates/PROJECT_PROFILE.md",
        "skills/library/api-registry-manager/SKILL.md",
        "skills/library/api-registry-manager/templates/API_REGISTRY.json",
        "skills/library/api-registry-manager/templates/SOURCE_REGISTRY.json",
    ]

    all_ok = True
    for skill in skills:
        path = REPO_ROOT / skill
        ok = path.exists()
        status = "✅ PASS" if ok else "❌ FAIL"
        print(f"  [{status}] {skill}")
        if not ok:
            all_ok = False

    return all_ok


def test_cron_jobs() -> bool:
    """测试 cron jobs.json 是否移除了自进化 job。"""
    print("\n📦 Step 7: cron jobs.json")

    jobs_path = REPO_ROOT / "cron/jobs.json"
    content = jobs_path.read_text(encoding="utf-8")
    jobs = json.loads(content)

    removed_jobs = [
        "ops_governance_evolution_incremental",
        "ops_self_evolution_weekly_todo",
        "optimize 自我进化总结",
        "upgrade_feedback_daily",
        "algo_micro_optimizer_daily",
        "agent_self_evolution",
        "auto_update_daily",
        "web_intel_collect_daily",
        "github_web_evolution_daily",
        "advisor_todo_daily",
    ]

    all_ok = True
    job_names = {j.get("name", "") for j in jobs.get("jobs", [])}

    for name in removed_jobs:
        removed = name not in job_names
        status = "✅ PASS" if removed else "❌ FAIL"
        print(f"  [{status}] removed: {name}")
        if not removed:
            all_ok = False

    # 检查新增的 API watch
    has_watcher = "source_registry_watcher" in str(jobs)
    status = "✅ PASS" if has_watcher else "❌ FAIL"
    print(f"  [{status}] added: source_registry_watcher")
    if not has_watcher:
        all_ok = False

    # 统计 job 数量
    job_count = len(jobs.get("jobs", []))
    print(f"       total jobs: {job_count}")

    return all_ok


def main() -> int:
    print("=" * 60)
    print(" 项目交付优先工作流 — 端到端集成测试")
    print(f" 时间: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 60)

    results: list[tuple[str, bool]] = []

    results.append(("failure_tracker", test_failure_tracker()))
    results.append(("project_memory", test_project_memory()))
    results.append(("source_registry", test_source_registry()))
    results.append(("review_gate", test_review_gate()))
    results.append(("dual_ai_templates", test_dual_ai_review_templates()))
    results.append(("project_delivery_skills", test_project_delivery_skills()))
    results.append(("cron_jobs", test_cron_jobs()))

    print("\n" + "=" * 60)
    print(" 测试结果汇总")
    print("=" * 60)

    passed = 0
    failed = 0
    for name, ok in results:
        status = "✅ PASS" if ok else "❌ FAIL"
        print(f"  [{status}] {name}")
        if ok:
            passed += 1
        else:
            failed += 1

    print(f"\n 总计: {passed} 通过, {failed} 失败 / {len(results)} 项")

    if failed == 0:
        print("\n🎉 所有测试通过！流水线基本可用。")
        print("\n下一步建议:")
        print("  1. 选一个真实的小任务做端到端 dry-run")
        print("  2. 验证 coordinator 按新链路调度")
        print("  3. 远端服务器同步 cron/jobs.json")
        return 0
    else:
        print(f"\n⚠️ {failed} 项测试失败，请修复后再验证。")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
