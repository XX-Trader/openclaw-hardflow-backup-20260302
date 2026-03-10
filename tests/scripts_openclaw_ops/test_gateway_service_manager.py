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


if __name__ == "__main__":
    unittest.main()
