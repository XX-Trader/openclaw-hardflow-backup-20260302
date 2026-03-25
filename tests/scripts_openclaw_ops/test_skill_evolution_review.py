import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


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


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class SkillEvolutionReviewTests(unittest.TestCase):
    def test_build_skill_evolution_review_marks_skill_gap_and_renders_markdown(self):
        module = load_module(
            "skill_evolution_review",
            "scripts/openclaw-ops/skill_evolution_review.py",
        )

        baseline_payload = {
            "run_id": "exec-skill-baseline-1",
            "tasks_selected": 3,
            "tasks_executed": 3,
            "tasks_skipped": 0,
            "tasks_failed": 2,
            "preflight_warning_tasks": 0,
            "preflight_blocked_tasks": 0,
            "results": [
                {
                    "task_id": "todo-1",
                    "task_type": "governance_evolution_optimize",
                    "assignee": "optimization-agent",
                    "status": "executed",
                    "task_status_after": "partial",
                    "report_status": "partial",
                    "reason": "partial",
                    "quality_score": 54,
                    "solved": False,
                    "resolution_summary": "缺少验证证据",
                    "duration_ms": 8600,
                },
                {
                    "task_id": "todo-2",
                    "task_type": "governance_evolution_optimize",
                    "assignee": "optimization-agent",
                    "status": "executed",
                    "task_status_after": "failed",
                    "report_status": "failed",
                    "reason": "failed",
                    "quality_score": 50,
                    "solved": False,
                    "resolution_summary": "输出不完整",
                    "duration_ms": 7900,
                },
                {
                    "task_id": "todo-3",
                    "task_type": "governance_evolution_optimize",
                    "assignee": "optimization-agent",
                    "status": "executed",
                    "task_status_after": "partial",
                    "report_status": "partial",
                    "reason": "partial",
                    "quality_score": 57,
                    "solved": False,
                    "resolution_summary": "边界说明不足",
                    "duration_ms": 9100,
                },
            ],
        }
        candidate_payload = {
            "run_id": "exec-skill-candidate-1",
            "tasks_selected": 3,
            "tasks_executed": 3,
            "tasks_skipped": 0,
            "tasks_failed": 0,
            "preflight_warning_tasks": 0,
            "preflight_blocked_tasks": 0,
            "results": [
                {
                    "task_id": "todo-1",
                    "task_type": "governance_evolution_optimize",
                    "assignee": "optimization-agent",
                    "status": "executed",
                    "task_status_after": "passed",
                    "report_status": "passed",
                    "reason": "solved",
                    "quality_score": 90,
                    "solved": True,
                    "resolution_summary": "已补验证证据",
                    "duration_ms": 6400,
                },
                {
                    "task_id": "todo-2",
                    "task_type": "governance_evolution_optimize",
                    "assignee": "optimization-agent",
                    "status": "executed",
                    "task_status_after": "passed",
                    "report_status": "passed",
                    "reason": "solved",
                    "quality_score": 88,
                    "solved": True,
                    "resolution_summary": "结构化输出稳定",
                    "duration_ms": 6100,
                },
                {
                    "task_id": "todo-3",
                    "task_type": "governance_evolution_optimize",
                    "assignee": "optimization-agent",
                    "status": "executed",
                    "task_status_after": "passed",
                    "report_status": "passed",
                    "reason": "solved",
                    "quality_score": 91,
                    "solved": True,
                    "resolution_summary": "边界控制稳定",
                    "duration_ms": 6000,
                },
            ],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            baseline_file = tmp / "baseline.json"
            candidate_file = tmp / "candidate.json"
            write_json(baseline_file, baseline_payload)
            write_json(candidate_file, candidate_payload)

            review = module.build_skill_evolution_review(
                baseline_inputs=[baseline_file],
                candidate_inputs=[candidate_file],
                skill_name="openclaw-evolution-upgrader",
                assignee="optimization-agent",
            )

        self.assertEqual(review["classification"]["root_cause_type"], "skill_gap")
        self.assertGreater(review["delta"]["instruction_clarity"], 0)
        self.assertGreater(review["delta"]["verification_discipline"], 0)
        self.assertIn("补强验证动作", "\n".join(review["recommended_updates"]))
        self.assertIn("openclaw-evolution-upgrader", review["markdown"])
        self.assertIn("问题分类：`skill_gap`", review["markdown"])
        self.assertIn("是否晋升为新基线：是", review["markdown"])


if __name__ == "__main__":
    unittest.main()
