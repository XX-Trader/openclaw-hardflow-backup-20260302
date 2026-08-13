import importlib
import subprocess
import sys
from pathlib import Path


POLICY_DIR = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "library"
    / "control-plane-ops"
    / "scripts"
    / "policy"
)


def import_policy_module(name: str):
    sys.path.insert(0, str(POLICY_DIR))
    try:
        return importlib.import_module(name)
    finally:
        sys.path.remove(str(POLICY_DIR))


def clear_policy_modules() -> None:
    for name in (
        "policy_task",
        "task_center",
    ):
        sys.modules.pop(name, None)


def test_read_json_can_atomically_create_default_file(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENCLAW_FILE_WRITE_AUDIT_DISABLED", "1")
    policy_utils = import_policy_module("policy_utils")
    output = tmp_path / "nested" / "policy.json"

    result = policy_utils.read_json(output, {"enabled": True}, write_if_missing=True)

    assert result == {"enabled": True}
    assert policy_utils.read_json(output) == result


def test_policy_task_imports_task_center_error():
    clear_policy_modules()
    policy_task = import_policy_module("policy_task")
    task_center = import_policy_module("task_center")

    assert policy_task.TaskCenterError is task_center.TaskCenterError


def test_policy_observe_cli_help_has_valid_main_entrypoint():
    result = subprocess.run(
        [sys.executable, str(POLICY_DIR / "policy_observe.py"), "--help"],
        cwd=POLICY_DIR,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "usage:" in result.stdout
