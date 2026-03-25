import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/openclaw-ops/policy/gateway_service_manager.py"


def load_module(name: str):
    sys.path.insert(0, str(SCRIPT.parent))
    try:
        spec = importlib.util.spec_from_file_location(name, SCRIPT)
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.modules.pop(name, None)
        sys.path.pop(0)


class GatewayServiceManagerTests(unittest.TestCase):
    def test_prefers_system_service_and_disables_user_service_when_both_exist(self):
        module = load_module("gateway_service_manager")
        snapshot = module.ServiceSnapshot(
            system=module.UnitStatus(
                scope="system",
                name="openclaw.service",
                exists=True,
                active=True,
                enabled=False,
                load_state="loaded",
                active_state="active",
                unit_file_state="disabled",
            ),
            user=module.UnitStatus(
                scope="user",
                name="openclaw-gateway.service",
                exists=True,
                active=True,
                enabled=True,
                load_state="loaded",
                active_state="active",
                unit_file_state="enabled",
            ),
            user_scope_ready=True,
            user_uid=0,
        )

        plan = module.build_reconcile_plan(snapshot, action="restart", preferred_scope="system")

        self.assertEqual(plan.selected_scope, "system")
        self.assertEqual(
            [step["id"] for step in plan.steps],
            [
                "user_disable_now",
                "user_reset_failed",
                "system_enable",
                "system_restart",
            ],
        )

    def test_uses_user_service_when_system_service_is_missing(self):
        module = load_module("gateway_service_manager")
        snapshot = module.ServiceSnapshot(
            system=module.UnitStatus(
                scope="system",
                name="openclaw.service",
                exists=False,
                active=False,
                enabled=False,
                load_state="not-found",
                active_state="inactive",
                unit_file_state="disabled",
            ),
            user=module.UnitStatus(
                scope="user",
                name="openclaw-gateway.service",
                exists=True,
                active=True,
                enabled=True,
                load_state="loaded",
                active_state="active",
                unit_file_state="enabled",
            ),
            user_scope_ready=True,
            user_uid=1000,
        )

        plan = module.build_reconcile_plan(snapshot, action="restart", preferred_scope="system")

        self.assertEqual(plan.selected_scope, "user")
        self.assertEqual([step["id"] for step in plan.steps], ["user_restart"])

    def test_falls_back_to_cli_restart_without_supervised_service(self):
        module = load_module("gateway_service_manager")
        snapshot = module.ServiceSnapshot(
            system=module.UnitStatus(
                scope="system",
                name="openclaw.service",
                exists=False,
                active=False,
                enabled=False,
                load_state="not-found",
                active_state="inactive",
                unit_file_state="disabled",
            ),
            user=module.UnitStatus(
                scope="user",
                name="openclaw-gateway.service",
                exists=False,
                active=False,
                enabled=False,
                load_state="not-found",
                active_state="inactive",
                unit_file_state="disabled",
            ),
            user_scope_ready=False,
            user_uid=1000,
        )

        plan = module.build_reconcile_plan(snapshot, action="restart", preferred_scope="system")

        self.assertEqual(plan.selected_scope, "process")
        self.assertEqual([step["id"] for step in plan.steps], ["process_restart"])


class GatewayRestartScriptUsageTests(unittest.TestCase):
    def test_target_scripts_use_gateway_service_manager_helper(self):
        targets = [
            ROOT / "scripts/openclaw-ops/sync_policy_enforcer_to_servers.sh",
            ROOT / "scripts/openclaw-ops/sync_policy_enforcer_to_servers.ps1",
            ROOT / "scripts/openclaw-ops/sync_gpt54_to_servers.sh",
            ROOT / "scripts/openclaw-ops/sync_gpt54_to_servers.ps1",
            ROOT / "scripts/openclaw-ops/sync_model_to_doubao_servers.sh",
            ROOT / "scripts/openclaw-ops/sync_model_to_doubao_servers.ps1",
            ROOT / "scripts/openclaw-ops/sync_agents_12_to_servers.sh",
            ROOT / "scripts/hardflow/deploy-evolution-hooks.sh",
        ]
        for path in targets:
            text = path.read_text(encoding="utf-8", errors="replace")
            self.assertIn("gateway_service_manager.py", text, msg=str(path))

    def test_sync_gpt54_scripts_sync_runtime_dependencies(self):
        required_entries = [
            "scripts/openclaw-ops/chat_output.py",
            "scripts/openclaw-ops/policy/task_executor_runner.py",
            "scripts/openclaw-ops/policy/alert_dedupe.py",
            "scripts/openclaw-ops/policy/task_capability_binding.py",
            "scripts/openclaw-ops/policy/dataclass_compat.py",
            "scripts/openclaw-ops/utf8_runtime.py",
            "scripts/openclaw-ops/workflow_views.py",
        ]
        targets = [
            ROOT / "scripts/openclaw-ops/sync_gpt54_to_servers.sh",
            ROOT / "scripts/openclaw-ops/sync_gpt54_to_servers.ps1",
        ]
        for path in targets:
            text = path.read_text(encoding="utf-8", errors="replace")
            for entry in required_entries:
                with self.subTest(path=str(path), entry=entry):
                    self.assertIn(entry, text, msg=f"{path} missing runtime dependency {entry}")

    def test_sync_gpt54_scripts_validate_real_runtime_policy_dir(self):
        expectations = {
            ROOT / "scripts/openclaw-ops/sync_gpt54_to_servers.sh": [
                "${remote_ops_policy_dir}/policy_enforcer.py",
                "${remote_workspace_ops_policy_dir}/policy_enforcer.py",
            ],
            ROOT / "scripts/openclaw-ops/sync_gpt54_to_servers.ps1": [
                "$remoteOpsPolicyDir/policy_enforcer.py",
                "$remoteWorkspaceOpsPolicyDir/policy_enforcer.py",
            ],
        }
        for path, snippets in expectations.items():
            text = path.read_text(encoding="utf-8", errors="replace")
            for snippet in snippets:
                with self.subTest(path=str(path), snippet=snippet):
                    self.assertIn(snippet, text, msg=f"{path} missing validate-runtime target {snippet}")


if __name__ == "__main__":
    unittest.main()
