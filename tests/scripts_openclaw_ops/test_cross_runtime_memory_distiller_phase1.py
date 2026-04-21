import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def load_module(name: str, rel_path: str):
    """按相对路径动态加载模块，便于测试未安装的脚本文件。"""
    path = ROOT / rel_path
    if not path.exists():
        raise FileNotFoundError(path)
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


class CrossRuntimeMemoryDistillerPhase1Tests(unittest.TestCase):
    def test_runtime_probe_supports_mixed_windows_and_wsl_hosts(self):
        module = load_module(
            "cross_runtime_runtime_probe",
            "skills/library/cross-runtime-memory-distiller/scripts/runtime_probe.py",
        )

        result = module.probe_hosts(
            hosts=("openclaw", "hermes"),
            current_os="windows",
            user_home=Path(r"C:\Users\Administrator"),
            hermes_wsl_distro="Ubuntu",
            hermes_wsl_user="ubuntu",
        )

        self.assertEqual(result["openclaw"]["runtime_kind"], "windows")
        self.assertEqual(result["openclaw"]["home"], r"C:\Users\Administrator\.openclaw")
        self.assertIn(r"C:\Users\Administrator\.openclaw\workspace*", result["openclaw"]["workspace_roots"][0])
        self.assertEqual(result["hermes"]["runtime_kind"], "wsl")
        self.assertEqual(result["hermes"]["distro"], "Ubuntu")
        self.assertEqual(result["hermes"]["home"], "/home/ubuntu/.hermes")
        self.assertEqual(result["hermes"]["hot_memory_paths"]["user"], "/home/ubuntu/.hermes/memories/USER.md")

    def test_host_adapters_build_shared_parser_packet_shape(self):
        runtime_probe = load_module(
            "cross_runtime_runtime_probe",
            "skills/library/cross-runtime-memory-distiller/scripts/runtime_probe.py",
        )
        hermes_adapter = load_module(
            "cross_runtime_host_adapter_hermes",
            "skills/library/cross-runtime-memory-distiller/scripts/host_adapter_hermes.py",
        )
        openclaw_adapter = load_module(
            "cross_runtime_host_adapter_openclaw",
            "skills/library/cross-runtime-memory-distiller/scripts/host_adapter_openclaw.py",
        )

        hermes_runtime = runtime_probe.RuntimeProbeResult(
            host="hermes",
            runtime_kind="wsl",
            transport="wsl_exec",
            distro="Ubuntu",
            home="/home/ubuntu/.hermes",
            session_roots=["/home/ubuntu/.hermes/sessions"],
            hot_memory_paths={
                "user": "/home/ubuntu/.hermes/memories/USER.md",
                "memory": "/home/ubuntu/.hermes/memories/MEMORY.md",
            },
            workspace_roots=[],
            state_db="/home/ubuntu/.hermes/state.db",
        )
        openclaw_runtime = runtime_probe.RuntimeProbeResult(
            host="openclaw",
            runtime_kind="windows",
            transport="native_fs",
            distro="",
            home=r"C:\Users\Administrator\.openclaw",
            session_roots=[r"C:\Users\Administrator\.openclaw\agents\*\sessions\*.jsonl"],
            hot_memory_paths={
                "user": r"C:\Users\Administrator\.openclaw\workspace*\USER.md",
                "memory": r"C:\Users\Administrator\.openclaw\workspace*\MEMORY.md",
            },
            workspace_roots=[r"C:\Users\Administrator\.openclaw\workspace*"],
            state_db="",
        )

        packet = runtime_probe.ParserCandidatePacket(
            candidate_id="cand_001",
            host="hermes",
            project="openclaw-hardflow-backup-20260302",
            trace_id="trace_001",
            task_id="task_001",
            run_id="run_001",
            source="claude",
            evidence_refs=["bundle_001:12-44"],
            window_text="候选窗口正文",
            target_schema_version="2026-04-15",
        )

        hermes_request = hermes_adapter.build_parser_request(hermes_runtime, packet)
        self.assertEqual(hermes_request["host"], "hermes")
        self.assertEqual(hermes_request["runtime"]["runtime_kind"], "wsl")
        self.assertEqual(hermes_request["parser_input"]["candidate_id"], "cand_001")
        self.assertEqual(hermes_request["parser_input"]["target_schema_version"], "2026-04-15")

        openclaw_packet = runtime_probe.ParserCandidatePacket(
            candidate_id="cand_002",
            host="openclaw",
            project="openclaw-hardflow-backup-20260302",
            trace_id="trace_002",
            task_id="task_002",
            run_id="run_002",
            source="repo_delta",
            evidence_refs=["bundle_002:1-9"],
            window_text="另一个候选窗口",
            target_schema_version="2026-04-15",
        )
        openclaw_request = openclaw_adapter.build_parser_request(openclaw_runtime, openclaw_packet)
        self.assertEqual(openclaw_request["host"], "openclaw")
        self.assertEqual(openclaw_request["runtime"]["runtime_kind"], "windows")
        self.assertEqual(openclaw_request["parser_input"]["candidate_id"], "cand_002")

        with self.assertRaises(ValueError):
            openclaw_adapter.build_parser_request(hermes_runtime, openclaw_packet)

    def test_phase1_contract_files_exist(self):
        shared_host_contract = ROOT / "skills/library/cross-runtime-memory-distiller/references/shared-host-contract.md"
        parser_contract = ROOT / "skills/library/cross-runtime-memory-distiller/references/parser-agent-contract.md"

        self.assertTrue(shared_host_contract.exists())
        self.assertTrue(parser_contract.exists())


if __name__ == "__main__":
    unittest.main()
