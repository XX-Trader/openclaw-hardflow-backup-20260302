import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ACTIVE_WORKFLOW_OWNERS = {
    "coordinator",
    "project-agent",
    "web-agent",
    "reviewer",
    "backend-dev",
    "frontend-dev",
    "tester",
    "deployer",
    "doc-writer",
}
RETIRED_AGENT_IDS = {"ops-agent", "optimization-agent", "explorer", "git-master"}


class ActiveAgentRegistryTests(unittest.TestCase):
    def load_json(self, rel_path: str) -> dict:
        return json.loads((ROOT / rel_path).read_text(encoding="utf-8"))

    def test_openclaw_configs_define_exactly_nine_active_workflow_owners(self):
        for rel_path in ("openclaw.json", "openclaw/openclaw.json"):
            with self.subTest(path=rel_path):
                data = self.load_json(rel_path)
                agent_ids = [item["id"] for item in data["agents"]["list"]]
                allowed = set(data["tools"]["agentToAgent"]["allow"])

                self.assertEqual(9, len(agent_ids))
                self.assertEqual(ACTIVE_WORKFLOW_OWNERS, set(agent_ids))
                self.assertTrue(RETIRED_AGENT_IDS.isdisjoint(agent_ids))
                self.assertEqual(ACTIVE_WORKFLOW_OWNERS, allowed)

    def test_cron_jobs_reference_only_active_workflow_owners(self):
        cron = self.load_json("cron/jobs.json")
        agent_ids = {str(item.get("agentId", "")) for item in cron["jobs"]}

        self.assertTrue(agent_ids)
        self.assertTrue(agent_ids.issubset(ACTIVE_WORKFLOW_OWNERS))
        self.assertTrue(RETIRED_AGENT_IDS.isdisjoint(agent_ids))


if __name__ == "__main__":
    unittest.main()
