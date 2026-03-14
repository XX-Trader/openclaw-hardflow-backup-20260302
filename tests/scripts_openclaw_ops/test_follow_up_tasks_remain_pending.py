import json
import os
import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
POLICY_CLI = ROOT / "scripts/openclaw-ops/policy/policy_enforcer.py"
SELF_EVOLUTION_RUNNER = ROOT / "scripts/openclaw-ops/self_evolution_todo.py"
GOVERNANCE_RUNNER = ROOT / "scripts/openclaw-ops/governance_evolution_runner.py"


def decode_output(data: bytes) -> str:
    for encoding in ("utf-8", "gbk", "cp936"):
        try:
            return (data or b"").decode(encoding)
        except Exception:
            continue
    return (data or b"").decode("utf-8", errors="replace")


def parse_json_text(raw: str) -> dict:
    text = str(raw or "").strip()
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for candidate in reversed(lines):
        try:
            parsed = json.loads(candidate)
        except Exception:
            continue
        if isinstance(parsed, dict):
            return parsed
    parsed = json.loads(text)
    assert isinstance(parsed, dict)
    return parsed


class FollowUpTasksRemainPendingTests(unittest.TestCase):
    def run_command(self, cmd: list[str], *, cwd: Path, env: dict[str, str]) -> tuple[int, str, str]:
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        return proc.returncode, decode_output(proc.stdout), decode_output(proc.stderr)

    def init_runtime(self, root: Path, env: dict[str, str]) -> tuple[Path, Path, Path, Path]:
        db = root / "task_center.db"
        policy = root / "policy-config.json"
        routing = root / "routing-rules.json"
        pricing = root / "token-pricing.json"
        rc, out, err = self.run_command(
            [
                "python",
                str(POLICY_CLI),
                "--db",
                str(db),
                "--policy-file",
                str(policy),
                "--routing-file",
                str(routing),
                "--pricing-file",
                str(pricing),
                "init",
            ],
            cwd=ROOT,
            env=env,
        )
        self.assertEqual(rc, 0, msg=err or out)
        return db, policy, routing, pricing

    def fetch_task_row(self, db: Path, task_id: str) -> dict:
        conn = sqlite3.connect(str(db))
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT task_id, task_type, status, action, assignee FROM tasks WHERE task_id = ?",
                (task_id,),
            ).fetchone()
        finally:
            conn.close()
        self.assertIsNotNone(row)
        return dict(row)

    def test_self_evolution_created_follow_up_task_stays_pending(self):
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db, _policy, _routing, _pricing = self.init_runtime(root, env)
            state = root / "state.json"
            reports = root / "reports"
            reports.mkdir(parents=True, exist_ok=True)

            rc, out, err = self.run_command(
                [
                    "python",
                    str(SELF_EVOLUTION_RUNNER),
                    "--db",
                    str(db),
                    "--state-file",
                    str(state),
                    "--report-dir",
                    str(reports),
                    "--force",
                    "--emit-json",
                ],
                cwd=ROOT,
                env=env,
            )
            self.assertEqual(rc, 0, msg=err or out)
            payload = parse_json_text(out)
            report = json.loads(Path(payload["report"]).read_text(encoding="utf-8"))
            self.assertGreaterEqual(int(report.get("created_count", 0) or 0), 1)

            task_id = str(report["created"][0]["task_id"])
            row = self.fetch_task_row(db, task_id)

        self.assertEqual(row["task_type"], "self_evolution")
        self.assertEqual(row["status"], "pending")
        self.assertIn(row["action"], {"", None})

    def test_governance_created_follow_up_task_stays_pending(self):
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db, _policy, _routing, _pricing = self.init_runtime(root, env)
            state = root / "state.json"
            reports = root / "reports"
            reports.mkdir(parents=True, exist_ok=True)
            repo_dir = root / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)

            for cmd in (
                ["git", "init"],
                ["git", "config", "user.email", "verify@example.com"],
                ["git", "config", "user.name", "Verifier"],
            ):
                rc, out, err = self.run_command(cmd, cwd=repo_dir, env=env)
                self.assertEqual(rc, 0, msg=err or out)

            watched_dir = repo_dir / "scripts" / "openclaw-ops"
            watched_dir.mkdir(parents=True, exist_ok=True)
            target = watched_dir / "sample.py"
            target.write_text("print(1)\n", encoding="utf-8")

            for cmd in (
                ["git", "add", "."],
                ["git", "commit", "-m", "init"],
            ):
                rc, out, err = self.run_command(cmd, cwd=repo_dir, env=env)
                self.assertEqual(rc, 0, msg=err or out)

            target.write_text("print(2)\n", encoding="utf-8")
            for cmd in (
                ["git", "add", "."],
                ["git", "commit", "-m", "change"],
            ):
                rc, out, err = self.run_command(cmd, cwd=repo_dir, env=env)
                self.assertEqual(rc, 0, msg=err or out)

            rc, out, err = self.run_command(
                [
                    "python",
                    str(GOVERNANCE_RUNNER),
                    "--repo-path",
                    str(repo_dir),
                    "--db",
                    str(db),
                    "--state-file",
                    str(state),
                    "--report-dir",
                    str(reports),
                    "--force",
                    "--no-auto-git-update",
                    "--task-clarity",
                    "clear",
                    "--no-project-context-gate",
                    "--emit-json",
                ],
                cwd=ROOT,
                env=env,
            )
            self.assertEqual(rc, 0, msg=err or out)
            payload = parse_json_text(out)
            report = json.loads(Path(payload["report"]).read_text(encoding="utf-8"))
            created = report.get("task_packaging", {}).get("created", [])
            self.assertGreaterEqual(len(created), 1)

            task_id = str(created[0]["task_id"])
            row = self.fetch_task_row(db, task_id)

        self.assertEqual(row["task_type"], "governance_evolution_optimize")
        self.assertEqual(row["status"], "pending")
        self.assertIn(row["action"], {"", None})


if __name__ == "__main__":
    unittest.main()
