import importlib.util
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]


def load_module(name: str, rel_path: str):
    path = ROOT / rel_path
    sys.path.insert(0, str(path.parent))
    try:
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.modules.pop(name, None)
        sys.path.pop(0)


class RecordingTaskCenter:
    instances: list["RecordingTaskCenter"] = []

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        self.created_tasks: list[dict[str, Any]] = []
        self.events: list[dict[str, Any]] = []
        RecordingTaskCenter.instances.append(self)

    def init_schema(self) -> None:
        return None

    def close(self) -> None:
        return None

    def create_task(self, payload: dict[str, Any], actor: str) -> dict[str, Any]:
        task = dict(payload)
        task["actor"] = actor
        self.created_tasks.append(task)
        return task

    def add_event(self, **payload: Any) -> None:
        self.events.append(dict(payload))


class DirectTaskConstraintBackfillTests(unittest.TestCase):
    def setUp(self) -> None:
        RecordingTaskCenter.instances = []
        self.fixed_now = datetime(2026, 3, 14, 8, 0, 0, tzinfo=timezone.utc)

    def test_self_evolution_todo_tasks_include_capability_constraints(self):
        module = load_module(
            "self_evolution_todo",
            "scripts/openclaw-ops/self_evolution_todo.py",
        )
        task_center = RecordingTaskCenter()
        original_collect = module.collect_open_fingerprints
        original_base = module.infer_next_schedule_base
        original_now = module.now
        try:
            module.collect_open_fingerprints = lambda _tc: set()
            module.infer_next_schedule_base = lambda _tc: self.fixed_now
            module.now = lambda: self.fixed_now
            created, skipped = module.create_todo_tasks(
                task_center,
                candidates=[
                    {
                        "title": "周度经验沉淀建议包",
                        "reason": "自我进化常规复盘",
                        "requirement": "总结经验并下发任务。",
                        "assignee": "coordinator",
                    }
                ],
                max_tasks_per_run=1,
                schedule_gap_minutes=30,
            )
        finally:
            module.collect_open_fingerprints = original_collect
            module.infer_next_schedule_base = original_base
            module.now = original_now

        self.assertEqual(len(created), 1)
        self.assertEqual(skipped, [])
        payload = task_center.created_tasks[0]
        self.assertEqual(payload["required_capabilities"], ["skill_backed"])
        self.assertEqual(payload["required_skills"], ["requirements-clarity", "task-decomposer"])
        self.assertEqual(payload["allowed_agents"], ["coordinator"])

    def test_governance_context_preflight_task_include_capability_constraints(self):
        module = load_module(
            "governance_evolution_runner",
            "scripts/openclaw-ops/governance_evolution_runner.py",
        )
        task_center = RecordingTaskCenter()

        module.create_context_preflight_task(
            tc=task_center,
            repo_path=Path("/repo/openclaw"),
            fingerprint="abcdef1234567890",
            scan_head="head123",
            diff_base="base456",
            change_lines=["M scripts/openclaw-ops/policy/task_executor_runner.py"],
            assignee="project-agent",
            base_time=self.fixed_now,
        )

        payload = task_center.created_tasks[0]
        self.assertEqual(payload["required_capabilities"], ["role_only"])
        self.assertEqual(payload["required_skills"], [])
        self.assertEqual(payload["allowed_agents"], ["project-agent"])

    def test_governance_generated_tasks_include_capability_constraints(self):
        module = load_module(
            "governance_evolution_runner",
            "scripts/openclaw-ops/governance_evolution_runner.py",
        )
        original_task_center = module.TaskCenter
        original_collect = module.collect_open_fingerprints
        original_now = module.now
        try:
            module.TaskCenter = RecordingTaskCenter
            module.collect_open_fingerprints = lambda _tc: set()
            module.now = lambda: self.fixed_now
            result = module.create_task_packages(
                db_file=Path("/tmp/task_center.db"),
                repo_path=Path("/repo/openclaw"),
                fingerprint="abcdef1234567890",
                scan_head="head123",
                diff_base="base456",
                changes=[
                    {
                        "status": "M",
                        "path": "scripts/openclaw-ops/policy/task_executor_runner.py",
                    }
                ],
                create_review_task=True,
                require_project_context=False,
                project_context_assignee="project-agent",
            )
        finally:
            module.TaskCenter = original_task_center
            module.collect_open_fingerprints = original_collect
            module.now = original_now

        self.assertEqual(len(result["created"]), 2)
        task_center = RecordingTaskCenter.instances[-1]
        optimize_payload = task_center.created_tasks[0]
        review_payload = task_center.created_tasks[1]
        self.assertEqual(optimize_payload["required_capabilities"], ["role_only"])
        self.assertEqual(optimize_payload["required_skills"], [])
        self.assertEqual(optimize_payload["allowed_agents"], ["optimization-agent"])
        self.assertEqual(review_payload["required_capabilities"], ["skill_backed"])
        self.assertEqual(review_payload["required_skills"], ["requesting-code-review"])
        self.assertEqual(review_payload["allowed_agents"], ["reviewer"])

    def test_github_web_evolution_todo_task_include_capability_constraints(self):
        module = load_module(
            "github_web_evolution_runner",
            "scripts/openclaw-ops/github_web_evolution_runner.py",
        )
        task_center = RecordingTaskCenter()
        original_open = module.collect_open_markers
        original_recent = module.collect_recent_marker
        original_base = module.infer_next_schedule_base
        original_now = module.now
        try:
            module.collect_open_markers = lambda _tc, marker="fingerprint": set()
            module.collect_recent_marker = lambda _tc, marker="dedupe_key", recent_days=7: set()
            module.infer_next_schedule_base = lambda _tc: self.fixed_now
            module.now = lambda: self.fixed_now
            task = module.create_todo_task(
                tc=task_center,
                fingerprint="abcdef1234567890",
                dedupe_key="repo:openclaw",
                assignee="optimization-agent",
                schedule_gap_minutes=45,
                report_file=Path("/tmp/reports/github_web_evolution.json"),
                catalog_file=Path("/tmp/reports/github_web_catalog.json"),
                changes=[
                    {
                        "entity_type": "repo",
                        "change_type": "updated",
                        "full_name": "D4Vinci/Scrapling",
                        "quality_score": 88,
                        "stargazers_count": 1000,
                        "html_url": "https://github.com/D4Vinci/Scrapling",
                    }
                ],
                query_list=["openclaw hooks plugins skills archived:false"],
                recent_dedupe_days=7,
            )
        finally:
            module.collect_open_markers = original_open
            module.collect_recent_marker = original_recent
            module.infer_next_schedule_base = original_base
            module.now = original_now

        self.assertIsNotNone(task)
        payload = task_center.created_tasks[0]
        self.assertEqual(payload["required_capabilities"], ["role_only"])
        self.assertEqual(payload["required_skills"], [])
        self.assertEqual(payload["allowed_agents"], ["optimization-agent"])

    def test_conversation_evolution_todo_task_include_capability_constraints(self):
        module = load_module(
            "conversation_evolution_runner",
            "scripts/openclaw-ops/conversation_evolution_runner.py",
        )
        task_center = RecordingTaskCenter()
        original_collect = module.collect_open_fingerprints
        original_recent = module.collect_recent_dedupe_keys
        original_base = module.infer_next_schedule_base
        original_now = module.now
        try:
            module.collect_open_fingerprints = lambda _tc: set()
            module.collect_recent_dedupe_keys = lambda _tc, recent_days=7: set()
            module.infer_next_schedule_base = lambda _tc: self.fixed_now
            module.now = lambda: self.fixed_now
            created, skipped = module.create_todo_tasks(
                task_center,
                candidates=[
                    {
                        "title": "对话审查建议包",
                        "reason": "近期 reviewer 反馈需要二次审查",
                        "requirement": "补充审查建议与验证步骤。",
                        "dedupe_key": "conversation:reviewer",
                        "quality": {"score": 85},
                    }
                ],
                assignee="reviewer",
                max_tasks_per_run=1,
                schedule_gap_minutes=30,
                recent_dedupe_days=7,
            )
        finally:
            module.collect_open_fingerprints = original_collect
            module.collect_recent_dedupe_keys = original_recent
            module.infer_next_schedule_base = original_base
            module.now = original_now

        self.assertEqual(len(created), 1)
        self.assertEqual(skipped, [])
        payload = task_center.created_tasks[0]
        self.assertEqual(payload["required_capabilities"], ["skill_backed"])
        self.assertEqual(payload["required_skills"], ["requesting-code-review"])
        self.assertEqual(payload["allowed_agents"], ["reviewer"])

    def test_reviewer_techdebt_task_include_capability_constraints(self):
        module = load_module(
            "reviewer_cron_runner",
            "scripts/openclaw-ops/reviewer_cron_runner.py",
        )
        original_task_center = module.TaskCenter
        original_sync = module.sync_resolved_techdebt_tasks
        original_list_open = module.list_open_debt_tasks_for_issue
        original_query_latest = module.query_latest_debt_task
        try:
            module.TaskCenter = RecordingTaskCenter
            module.sync_resolved_techdebt_tasks = lambda **_kwargs: {"closed": 0, "errors": [], "task_ids": []}
            module.list_open_debt_tasks_for_issue = lambda _tc, _issue_id: []
            module.query_latest_debt_task = lambda _tc, _issue_id: None
            with tempfile.TemporaryDirectory() as tmpdir:
                db_path = Path(tmpdir) / "task_center.db"
                db_path.write_text("", encoding="utf-8")
                result = module.create_or_reopen_techdebt_tasks(
                    args=type(
                        "Args",
                        (),
                        {
                            "create_techdebt_task": True,
                            "project_context_db": str(db_path),
                            "techdebt_max_tasks_per_run": 1,
                            "techdebt_min_severity": "medium",
                            "techdebt_assignee": "",
                        },
                    )(),
                    findings=[
                        {
                            "key": "duplication:frontend:001",
                            "severity": "high",
                            "path": "src/components/App.tsx",
                            "category": "duplication",
                            "title": "Frontend duplication issue",
                            "detail": "duplicate component logic",
                            "repo": "repo-a",
                            "repo_head": "head123",
                        }
                    ],
                    state={},
                    mode="daily_incremental",
                    run_id="run-techdebt-1",
                )
        finally:
            module.TaskCenter = original_task_center
            module.sync_resolved_techdebt_tasks = original_sync
            module.list_open_debt_tasks_for_issue = original_list_open
            module.query_latest_debt_task = original_query_latest

        self.assertEqual(result["created"], 1)
        task_center = RecordingTaskCenter.instances[-1]
        payload = task_center.created_tasks[0]
        self.assertEqual(payload["assignee"], "frontend-dev")
        self.assertEqual(payload["required_capabilities"], ["skill_backed"])
        self.assertEqual(payload["required_skills"], ["frontend-design", "feature-development"])
        self.assertEqual(payload["allowed_agents"], ["frontend-dev"])


if __name__ == "__main__":
    unittest.main()
