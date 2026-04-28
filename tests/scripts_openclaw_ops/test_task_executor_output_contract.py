import importlib.util
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]


def load_module(name: str, rel_path: str):
    path = ROOT / rel_path
    if not path.exists() and rel_path == "scripts/openclaw-ops/policy/task_executor_runner.py":
        path = ROOT / "skills/library/control-plane-ops/scripts/policy/task_executor_runner.py"
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


class TaskExecutorOutputContractTests(unittest.TestCase):
    def test_evaluate_stage_contract_builds_evidence_and_validation_summary(self):
        module = load_module(
            "task_executor_runner",
            "scripts/openclaw-ops/policy/task_executor_runner.py",
        )

        assessment = module.evaluate_stage_contract(
            {
                "stage_id": "implement",
                "stage_score_gate": "backend",
                "stage_min_evidence_count": 3,
                "stage_output_contract": {
                    "deliverables": ["code_changes", "verification_result"],
                },
                "stage_verification_contract": {
                    "checks": ["tests_or_validation_recorded"],
                },
            },
            {
                "status": "passed",
                "solved": True,
                "resolution_summary": "Implemented API fix and ran pytest -q successfully.",
                "resolution_steps": ["updated service handler", "ran pytest -q"],
                "resolved_issues": ["fixed endpoint regression"],
                "failed_items": [],
                "context_fields_missing": [],
                "need_clarification": False,
                "clarification_reason": "",
                "raw_text": "Implemented API fix and ran pytest -q successfully.",
            },
        )

        self.assertEqual(assessment["stage_id"], "implement")
        self.assertEqual(assessment["score_gate"], "backend")
        self.assertEqual(assessment["evidence_count"], 4)
        self.assertTrue(assessment["deliverables_passed"])
        self.assertTrue(assessment["verification_passed"])
        self.assertTrue(assessment["contract_passed"])
        self.assertEqual(assessment["missing_deliverables"], [])

    def test_evaluate_stage_contract_flags_missing_validation_evidence(self):
        module = load_module(
            "task_executor_runner",
            "scripts/openclaw-ops/policy/task_executor_runner.py",
        )

        assessment = module.evaluate_stage_contract(
            {
                "stage_id": "implement",
                "stage_score_gate": "backend",
                "stage_min_evidence_count": 3,
                "stage_output_contract": {
                    "deliverables": ["code_changes", "verification_result"],
                },
                "stage_verification_contract": {
                    "checks": ["tests_or_validation_recorded"],
                },
            },
            {
                "status": "passed",
                "solved": True,
                "resolution_summary": "Implemented API fix.",
                "resolution_steps": ["updated service handler"],
                "resolved_issues": ["fixed endpoint regression"],
                "failed_items": [],
                "context_fields_missing": [],
                "need_clarification": False,
                "clarification_reason": "",
                "raw_text": "Implemented API fix.",
            },
        )

        self.assertEqual(assessment["evidence_count"], 3)
        self.assertFalse(assessment["deliverables_passed"])
        self.assertFalse(assessment["verification_passed"])
        self.assertFalse(assessment["contract_passed"])
        self.assertIn("verification_result", assessment["missing_deliverables"])
        self.assertIn("tests_or_validation_recorded", assessment["failed_checks"])

    def test_gateway_agent_step_uses_chat_history_reply_for_local_runs(self):
        module = load_module(
            "task_executor_runner",
            "scripts/openclaw-ops/policy/task_executor_runner.py",
        )

        history_payload = {
            "sessionKey": "agent:optimization-agent:cron:task-executor:run:task-1",
            "sessionId": "sess-1",
            "messages": [
                {"role": "user", "content": [{"type": "text", "text": "prompt"}]},
                {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "text",
                            "text": '{"status":"passed","solved":true,"resolution_summary":"ok"}',
                        }
                    ],
                },
            ],
        }

        mocked_results = [
            SimpleNamespace(
                returncode=0,
                stdout='{"runId":"run-1","status":"accepted"}',
                stderr="",
            ),
            SimpleNamespace(
                returncode=0,
                stdout='{"runId":"run-1","status":"ok"}',
                stderr="",
            ),
            SimpleNamespace(
                returncode=0,
                stdout=module.json.dumps(history_payload, ensure_ascii=False),
                stderr="",
            ),
        ]

        with mock.patch.object(module.subprocess, "run", side_effect=mocked_results) as mocked_run:
            rc, out, err, attempts, details = module.call_agent_with_retries(
                "openclaw",
                "optimization-agent",
                "prompt",
                "task-1",
                300,
                True,
                "xhigh",
                max_retries=0,
                retry_delay_sec=1,
                prefer_gateway=True,
            )

        self.assertEqual(rc, 0)
        self.assertEqual(err, "")
        self.assertEqual(attempts, 1)
        self.assertEqual(len(details), 1)
        payload = module.json.loads(out)
        self.assertEqual(payload["payloads"][0]["text"], '{"status":"passed","solved":true,"resolution_summary":"ok"}')

        first_cmd = mocked_run.call_args_list[0].args[0]
        second_cmd = mocked_run.call_args_list[1].args[0]
        third_cmd = mocked_run.call_args_list[2].args[0]

        self.assertEqual(first_cmd[:4], ["openclaw", "gateway", "call", "agent"])
        self.assertIn("--json", first_cmd)
        first_params = module.json.loads(first_cmd[first_cmd.index("--params") + 1])
        self.assertEqual(first_params["thinking"], "xhigh")
        self.assertEqual(
            first_params["sessionKey"],
            "agent:optimization-agent:cron:task-executor:run:task-1",
        )

        self.assertEqual(second_cmd[:4], ["openclaw", "gateway", "call", "agent.wait"])
        self.assertEqual(third_cmd[:4], ["openclaw", "gateway", "call", "chat.history"])

    def test_warning_only_stderr_does_not_become_partial_reply(self):
        module = load_module(
            "task_executor_runner",
            "scripts/openclaw-ops/policy/task_executor_runner.py",
        )

        contract, agent_json, reply_text, sanitized_stderr = module.contract_from_agent_result(
            0,
            "",
            "[plugins] memory-openviking: loaded without install/load-path provenance; "
            "treat as untracked local code and pin trust via plugins.allow or install records "
            "(/root/.openclaw/extensions/memory-openviking/index.ts)",
        )

        self.assertEqual(agent_json, {})
        self.assertEqual(reply_text, "")
        self.assertEqual(sanitized_stderr, "")
        self.assertEqual(contract["status"], "failed")
        self.assertFalse(contract["solved"])
        self.assertGreaterEqual(contract["failure_count"], 1)
        self.assertEqual(contract["resolution_summary"], "agent_returned_no_structured_output")

    def test_payload_json_takes_priority_over_benign_stderr_warning(self):
        module = load_module(
            "task_executor_runner",
            "scripts/openclaw-ops/policy/task_executor_runner.py",
        )

        stdout = (
            '{"payloads":[{"text":"{\\"status\\":\\"passed\\",\\"solved\\":true,'
            '\\"resolution_summary\\":\\"ok\\"}"}]}'
        )
        contract, agent_json, reply_text, sanitized_stderr = module.contract_from_agent_result(
            0,
            stdout,
            "[plugins] memory-openviking: loaded without install/load-path provenance; "
            "treat as untracked local code and pin trust via plugins.allow or install records "
            "(/root/.openclaw/extensions/memory-openviking/index.ts)",
        )

        self.assertIn("payloads", agent_json)
        self.assertIn('"status":"passed"', reply_text)
        self.assertEqual(sanitized_stderr, "")
        self.assertEqual(contract["status"], "passed")
        self.assertTrue(contract["solved"])
        self.assertEqual(contract["resolution_summary"], "ok")

    def test_hermes_bin_wraps_chat_output_with_runtime_refs(self):
        module = load_module(
            "task_executor_runner",
            "scripts/openclaw-ops/policy/task_executor_runner.py",
        )

        mocked_result = SimpleNamespace(
            returncode=0,
            stdout='session_id: sess-hermes-1\n{"status":"passed","solved":true,"resolution_summary":"ok"}',
            stderr="",
        )
        with mock.patch.object(module.subprocess, "run", return_value=mocked_result) as mocked_run:
            rc, out, err, attempts, details = module.call_agent_with_retries(
                "/home/arbops/.local/bin/hermes",
                "tester",
                "prompt",
                "task-1",
                30,
                False,
                "",
                max_retries=0,
                retry_delay_sec=1,
                prefer_gateway=True,
            )

        self.assertEqual(rc, 0)
        self.assertEqual(err, "")
        self.assertEqual(attempts, 1)
        self.assertEqual(details[0]["exit_code"], 0)
        payload = module.json.loads(out)
        agent_meta = payload["meta"]["agentMeta"]
        self.assertEqual(agent_meta["runtime"], "hermes-chat")
        self.assertEqual(agent_meta["runId"], "sess-hermes-1")
        self.assertEqual(agent_meta["sessionId"], "sess-hermes-1")
        self.assertEqual(agent_meta["sessionKey"], "agent:tester:cron:task-executor:run:task-1")
        self.assertIn('"status":"passed"', payload["payloads"][0]["text"])

        cmd = mocked_run.call_args.args[0]
        self.assertEqual(cmd[:3], ["/home/arbops/.local/bin/hermes", "--pass-session-id", "chat"])


if __name__ == "__main__":
    unittest.main()
