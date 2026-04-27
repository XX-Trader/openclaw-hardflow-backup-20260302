#!/usr/bin/env python3
"""Run a non-dry-run Hermes profile smoke for the project delivery pipeline."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "2026-04-24.hermes-profile-smoke"
UTC = timezone.utc
REVIEW_STAGE_VERDICTS = {
    "requirements_review": "ready_for_solution",
    "solution_review": "ready_for_implement",
    "code_review": "pass",
    "review": "pass",
}


class SmokeError(RuntimeError):
    """Raised when the smoke cannot be executed safely."""


@dataclass(frozen=True)
class SmokeConfig:
    project_key: str = "hermes-smoke"
    requirement: str = "Smoke-test the project delivery pipeline inside the Hermes runtime profile."
    runtime_home: Path = Path.home() / ".hermes"
    workspace_root: Path | None = None
    project_memory_root: Path | None = None
    task_center_db: Path | None = None
    run_id: str | None = None
    command_cwd: Path | None = None
    agent_mode: str = "echo"
    hermes_bin: str = "hermes"
    hermes_profile: str = ""
    provider: str = ""
    model: str = ""
    max_turns: int = 1
    agent_timeout_seconds: int = 180
    command_timeout_seconds: int = 300
    record_task_center: bool = True
    force: bool = False


def utc_now() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat()


def default_run_id() -> str:
    return "hermes-profile-smoke-" + datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")


def repo_root_from_script() -> Path:
    cur = Path(__file__).resolve()
    for candidate in cur.parents:
        if (candidate / "skills" / "library" / "project-delivery-pipeline").exists():
            return candidate
    raise SmokeError(f"repo root not found from {cur}")


def load_runner_module() -> Any:
    runner_path = Path(__file__).resolve().with_name("pipeline_runner.py")
    spec = importlib.util.spec_from_file_location("project_delivery_pipeline_runner_for_smoke", runner_path)
    if not spec or not spec.loader:
        raise SmokeError(f"cannot load pipeline runner: {runner_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def shell_join(parts: list[str]) -> str:
    if os.name == "nt":
        return subprocess.list2cmdline(parts)
    return " ".join(sh_quote(part) for part in parts)


def sh_quote(value: str) -> str:
    if not value:
        return "''"
    if re.fullmatch(r"[A-Za-z0-9_@%+=:,./\\-]+", value):
        return value
    return "'" + value.replace("'", "'\"'\"'") + "'"


def resolve_paths(config: SmokeConfig) -> tuple[Path, Path, Path, Path, str]:
    runtime_home = config.runtime_home.expanduser().resolve()
    workspace_root = (config.workspace_root or runtime_home / ".workflow" / "pipeline-runs").expanduser()
    project_memory_root = (config.project_memory_root or runtime_home / ".workflow" / "project-memory").expanduser()
    task_center_db = (config.task_center_db or runtime_home / "ops" / "task-center" / "task_center.db").expanduser()
    command_cwd = (config.command_cwd or repo_root_from_script()).expanduser().resolve()
    run_id = config.run_id or default_run_id()
    return runtime_home, workspace_root, project_memory_root, task_center_db, run_id


def echo_outputs(stage: str, config: SmokeConfig, reviewer_role: str = "") -> str:
    if stage == "research":
        return "\n".join(
            [
                "# Research",
                "- Hermes runtime profile smoke verified command dispatch wiring.",
                "- Source: local Hermes CLI status/profile inspection.",
                "- Source URL: https://github.com/openai/codex",
            ]
        )
    if stage == "code":
        return "\n".join(
            [
                "# Patch Summary",
                "- Smoke command executed through the Hermes runtime adapter.",
                "- No production code was modified by the smoke agent.",
            ]
        )
    if stage == "verify":
        return "\n".join(
            [
                "# Verification",
                "- runtime_host=hermes",
                f"- runtime_home={config.runtime_home}",
                "- smoke verification passed",
            ]
        )
    if stage in REVIEW_STAGE_VERDICTS:
        title = "Code Review" if stage == "review" else stage.replace("_", " ").title()
        verdict = REVIEW_STAGE_VERDICTS[stage]
        lines = [
            f"# {title}",
            f"Final verdict: {verdict}",
            "Confidence: high",
        ]
        if reviewer_role:
            lines.append(f"Reviewer role: {reviewer_role}")
        lines.append(f"- Smoke output contains the required {stage} gate verdict.")
        return "\n".join(lines)
    raise SmokeError(f"unknown smoke stage: {stage}")


def hermes_prompt(stage: str, reviewer_role: str = "") -> tuple[str, str]:
    if stage == "research":
        return (
            "Return exactly this markdown and do not call tools:\n"
            "# Research\n"
            "- Hermes profile smoke verified native hermes chat command dispatch.\n"
            "- Source URL: https://github.com/openai/codex",
            "",
        )
    if stage == "code":
        return (
            "Return exactly this markdown and do not call tools:\n"
            "# Patch Summary\n"
            "- Hermes chat coding stage command executed.\n"
            "- No production code was modified by this smoke.",
            "",
        )
    if stage == "verify":
        return (
            "Return exactly this markdown and do not call tools:\n"
            "# Verification\n"
            "- Hermes chat verification stage passed.",
            "",
        )
    if stage in REVIEW_STAGE_VERDICTS:
        title = "Code Review" if stage == "review" else stage.replace("_", " ").title()
        verdict = REVIEW_STAGE_VERDICTS[stage]
        reviewer_line = f"Reviewer role: {reviewer_role}\n" if reviewer_role else ""
        return (
            "Return exactly this markdown and do not call tools:\n"
            f"# {title}\n"
            f"Final verdict: {verdict}\n"
            f"{reviewer_line}"
            "Confidence: high",
            rf"(?im)^\s*Final verdict\s*:\s*{re.escape(verdict)}\b",
        )
    raise SmokeError(f"unknown smoke stage: {stage}")


def hybrid_bundle_prompt() -> str:
    return (
        "Return only a JSON object with exactly these string keys: research, code, "
        "requirements_review, solution_review, code_review. "
        "Do not call tools. Do not wrap the JSON in markdown. Use these exact values:\n"
        "{\n"
        '  "research": "# Research\\n- Hermes profile smoke verified native hermes chat command dispatch.\\n- Source URL: https://github.com/openai/codex",\n'
        '  "code": "# Patch Summary\\n- Hermes chat coding stage command executed.\\n- No production code was modified by this smoke.",\n'
        '  "requirements_review": "# Requirements Review\\nFinal verdict: ready_for_solution\\nConfidence: high",\n'
        '  "solution_review": "# Solution Review\\nFinal verdict: ready_for_implement\\nConfidence: high",\n'
        '  "code_review": "# Code Review\\nFinal verdict: pass\\nConfidence: high"\n'
        "}"
    )


def extract_json_object(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\s*```$", "", raw).strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start < 0 or end <= start:
            raise
        data = json.loads(raw[start : end + 1])
    if not isinstance(data, dict):
        raise SmokeError("Hermes bundle response is not a JSON object")
    return data


def hermes_base_command(config: SmokeConfig) -> list[str]:
    hermes_cmd = [config.hermes_bin]
    if config.hermes_profile:
        hermes_cmd.extend(["-p", config.hermes_profile])
    hermes_cmd.extend(["chat", "-Q", "--source", "project-delivery-smoke", "--max-turns", str(config.max_turns)])
    if config.provider:
        hermes_cmd.extend(["--provider", config.provider])
    if config.model:
        hermes_cmd.extend(["--model", config.model])
    return hermes_cmd


def run_hybrid_bundle(command_dir: Path, config: SmokeConfig) -> tuple[dict[str, str], Path]:
    cmd = [*hermes_base_command(config), "-q", hybrid_bundle_prompt()]
    bundle_file = command_dir / "hermes_ai_stage_bundle.json"
    started_at = utc_now()
    try:
        proc = subprocess.run(
            cmd,
            text=True,
            capture_output=True,
            timeout=config.agent_timeout_seconds,
            check=False,
        )
        ended_at = utc_now()
        timed_out = False
        error = ""
    except subprocess.TimeoutExpired as exc:
        ended_at = utc_now()
        proc = subprocess.CompletedProcess(
            cmd,
            124,
            stdout=(exc.stdout.decode() if isinstance(exc.stdout, bytes) else exc.stdout) or "",
            stderr=(exc.stderr.decode() if isinstance(exc.stderr, bytes) else exc.stderr) or "",
        )
        timed_out = True
        error = f"Hermes hybrid bundle timed out after {config.agent_timeout_seconds}s"

    parsed: dict[str, Any] = {}
    parse_error = ""
    if proc.returncode == 0:
        try:
            parsed = extract_json_object(proc.stdout or "")
        except Exception as exc:
            parse_error = str(exc)
    outputs = {
        key: str(parsed.get(key, "")).strip()
        for key in ("research", "code", "requirements_review", "solution_review", "code_review")
    }
    ok = (
        proc.returncode == 0
        and not parse_error
        and all(outputs.values())
        and re.search(r"(?im)^\s*Final verdict\s*:\s*ready_for_solution\b", outputs["requirements_review"]) is not None
        and re.search(r"(?im)^\s*Final verdict\s*:\s*ready_for_implement\b", outputs["solution_review"]) is not None
        and re.search(r"(?im)^\s*Final verdict\s*:\s*pass\b", outputs["code_review"]) is not None
    )
    payload = {
        "mode": "hybrid-single-chat",
        "command": cmd,
        "started_at": started_at,
        "ended_at": ended_at,
        "returncode": int(proc.returncode),
        "ok": ok,
        "timed_out": timed_out,
        "error": error,
        "parse_error": parse_error,
        "stdout": proc.stdout or "",
        "stderr": proc.stderr or "",
        "outputs": outputs,
    }
    bundle_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not ok:
        reason = error or parse_error or f"Hermes hybrid bundle failed with exit code {proc.returncode}"
        raise SmokeError(reason)
    return outputs, bundle_file


def write_echo_agent(path: Path, stage: str, config: SmokeConfig, reviewer_role: str = "") -> None:
    output = echo_outputs(stage, config, reviewer_role)
    path.write_text(
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "from __future__ import annotations",
                f"OUTPUT = {json.dumps(output, ensure_ascii=False)}",
                "print(OUTPUT)",
                "",
            ]
        ),
        encoding="utf-8",
    )


def write_hermes_chat_agent(path: Path, stage: str, config: SmokeConfig, reviewer_role: str = "") -> None:
    prompt, expected_regex = hermes_prompt(stage, reviewer_role)
    hermes_cmd = [*hermes_base_command(config), "-q", prompt]
    path.write_text(
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "from __future__ import annotations",
                "import json",
                "import re",
                "import subprocess",
                "import sys",
                f"CMD = {json.dumps(hermes_cmd, ensure_ascii=False)}",
                f"EXPECTED_RE = {json.dumps(expected_regex)}",
                f"TIMEOUT = {int(config.agent_timeout_seconds)}",
                "try:",
                "    proc = subprocess.run(CMD, text=True, capture_output=True, timeout=TIMEOUT, check=False)",
                "except subprocess.TimeoutExpired as exc:",
                "    if exc.stdout:",
                "        out = exc.stdout.decode() if isinstance(exc.stdout, bytes) else exc.stdout",
                "        print(out.rstrip())",
                "    if exc.stderr:",
                "        err = exc.stderr.decode() if isinstance(exc.stderr, bytes) else exc.stderr",
                "        print(err.rstrip(), file=sys.stderr)",
                "    print(f'Hermes smoke command timed out after {TIMEOUT}s', file=sys.stderr)",
                "    sys.exit(124)",
                "if proc.stdout:",
                "    print(proc.stdout.rstrip())",
                "if proc.stderr:",
                "    print(proc.stderr.rstrip(), file=sys.stderr)",
                "if proc.returncode != 0:",
                "    sys.exit(proc.returncode)",
                "if EXPECTED_RE and not re.search(EXPECTED_RE, proc.stdout or ''):",
                "    print('Hermes smoke response missing required verdict gate', file=sys.stderr)",
                "    sys.exit(3)",
                "",
            ]
        ),
        encoding="utf-8",
    )


def with_reviewer_role(output: str, reviewer_role: str) -> str:
    if not reviewer_role:
        return output
    if re.search(r"(?im)^\s*(?:Reviewer role|reviewer_role|reviewer-role)\s*:", output or ""):
        return output
    return str(output or "").rstrip() + f"\nReviewer role: {reviewer_role}"


def write_cached_agent(path: Path, output: str) -> None:
    path.write_text(
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "from __future__ import annotations",
                f"OUTPUT = {json.dumps(output, ensure_ascii=False)}",
                "print(OUTPUT)",
                "",
            ]
        ),
        encoding="utf-8",
    )


def write_agent_scripts(command_dir: Path, config: SmokeConfig, stage_outputs: dict[str, str] | None = None) -> dict[str, Path]:
    command_dir.mkdir(parents=True, exist_ok=True)
    scripts: dict[str, Path] = {}
    stage_outputs = stage_outputs or {}
    script_stages = {
        "research": ("research", ""),
        "code": ("code", ""),
        "verify": ("verify", ""),
        "requirements_review_a": ("requirements_review", "reviewer-a"),
        "requirements_review_b": ("requirements_review", "reviewer-b"),
        "solution_review_a": ("solution_review", "reviewer-a"),
        "solution_review_b": ("solution_review", "reviewer-b"),
        "code_review_a": ("code_review", "reviewer-a"),
        "code_review_b": ("code_review", "reviewer-b"),
    }
    for script_key, (stage, reviewer_role) in script_stages.items():
        path = command_dir / f"{script_key}_agent.py"
        if stage in stage_outputs:
            write_cached_agent(path, with_reviewer_role(stage_outputs[stage], reviewer_role))
        elif config.agent_mode == "echo" or (config.agent_mode == "hybrid" and stage == "verify"):
            write_echo_agent(path, stage, config, reviewer_role)
        elif config.agent_mode in {"hermes-chat", "hybrid"}:
            write_hermes_chat_agent(path, stage, config, reviewer_role)
        else:
            raise SmokeError(f"unsupported agent mode: {config.agent_mode}")
        scripts[script_key] = path
    return scripts


def check_hermes_available(config: SmokeConfig) -> dict[str, Any]:
    hermes_path = shutil.which(config.hermes_bin)
    payload = {
        "checked": config.agent_mode in {"hermes-chat", "hybrid"},
        "hermes_bin": config.hermes_bin,
        "hermes_path": hermes_path,
        "ok": True,
    }
    if config.agent_mode in {"hermes-chat", "hybrid"} and not hermes_path:
        payload["ok"] = False
        raise SmokeError(f"hermes binary not found: {config.hermes_bin}")
    return payload


def run_smoke(config: SmokeConfig) -> dict[str, Any]:
    runner = load_runner_module()
    hermes_check = check_hermes_available(config)
    runtime_home, workspace_root, project_memory_root, task_center_db, run_id = resolve_paths(config)
    command_cwd = (config.command_cwd or repo_root_from_script()).expanduser().resolve()
    command_dir = runtime_home / ".workflow" / "smoke-agent-commands" / run_id
    command_dir.mkdir(parents=True, exist_ok=True)
    bundle_file: Path | None = None
    stage_outputs: dict[str, str] = {}
    if config.agent_mode == "hybrid":
        stage_outputs, bundle_file = run_hybrid_bundle(command_dir, config)
    scripts = write_agent_scripts(command_dir, config, stage_outputs=stage_outputs)

    def py_cmd(path: Path) -> str:
        return shell_join([sys.executable, str(path)])

    pipeline_config = runner.PipelineConfig(
        project_key=config.project_key,
        requirement=config.requirement,
        runtime_host="hermes",
        runtime_home=str(runtime_home),
        workspace_root=workspace_root,
        project_memory_root=project_memory_root,
        run_id=run_id,
        dry_run=False,
        source_urls=("https://github.com/openai/codex",),
        research_commands=(py_cmd(scripts["research"]),),
        requirements_discussion_commands=(py_cmd(scripts["research"]),),
        requirements_review_commands=(
            py_cmd(scripts["requirements_review_a"]),
            py_cmd(scripts["requirements_review_b"]),
        ),
        solution_review_commands=(
            py_cmd(scripts["solution_review_a"]),
            py_cmd(scripts["solution_review_b"]),
        ),
        code_command=py_cmd(scripts["code"]),
        verification_commands=(py_cmd(scripts["verify"]),),
        code_review_commands=(
            py_cmd(scripts["code_review_a"]),
            py_cmd(scripts["code_review_b"]),
        ),
        write_project_memory=True,
        command_cwd=command_cwd,
        command_timeout_seconds=config.command_timeout_seconds,
        record_task_center=config.record_task_center,
        task_center_db=task_center_db if config.record_task_center else None,
        force=config.force,
    )
    state = runner.run_pipeline(pipeline_config)
    ok = state.get("status") == "completed"
    report = {
        "schema_version": SCHEMA_VERSION,
        "ok": ok,
        "created_at": utc_now(),
        "agent_mode": config.agent_mode,
        "real_hermes_chat_used": config.agent_mode in {"hermes-chat", "hybrid"},
        "hermes_check": hermes_check,
        "runtime_home": str(runtime_home),
        "workspace_root": str(workspace_root),
        "project_memory_root": str(project_memory_root),
        "task_center_db": str(task_center_db) if config.record_task_center else "",
        "run_id": run_id,
        "run_dir": state.get("run_dir"),
        "status": state.get("status"),
        "next_action": state.get("next_action"),
        "failed_stage": state.get("failed_stage"),
        "task_center": state.get("task_center", {}),
    }
    report_path = Path(str(state.get("run_dir", workspace_root / run_id))) / "hermes_smoke_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    if bundle_file:
        bundle_target = report_path.parent / "hermes_ai_stage_bundle.json"
        shutil.copy2(bundle_file, bundle_target)
        report["ai_bundle_file"] = str(bundle_target)
        report["ai_bundle_mode"] = "hybrid-single-chat"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report["report_file"] = str(report_path)
    return report


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a Hermes profile smoke for project-delivery-pipeline")
    parser.add_argument("--project-key", default="hermes-smoke")
    parser.add_argument("--requirement", default=SmokeConfig.requirement)
    parser.add_argument("--runtime-home", type=Path, default=Path.home() / ".hermes")
    parser.add_argument("--workspace-root", type=Path)
    parser.add_argument("--project-memory-root", type=Path)
    parser.add_argument("--task-center-db", type=Path)
    parser.add_argument("--run-id")
    parser.add_argument("--command-cwd", type=Path)
    parser.add_argument(
        "--agent-mode",
        choices=["echo", "hybrid", "hermes-chat"],
        default="echo",
        help="echo=deterministic local agents; hybrid=one Hermes chat bundles research/code/review plus local verification; hermes-chat=Hermes chat for every stage",
    )
    parser.add_argument("--hermes-bin", default="hermes")
    parser.add_argument("--hermes-profile", default="")
    parser.add_argument("--provider", default="")
    parser.add_argument("--model", default="")
    parser.add_argument("--max-turns", type=int, default=1)
    parser.add_argument("--agent-timeout-seconds", type=int, default=180)
    parser.add_argument("--command-timeout-seconds", type=int, default=300)
    parser.add_argument("--skip-task-center", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--emit-json", action="store_true")
    return parser


def config_from_args(args: argparse.Namespace) -> SmokeConfig:
    return SmokeConfig(
        project_key=args.project_key,
        requirement=args.requirement,
        runtime_home=args.runtime_home,
        workspace_root=args.workspace_root,
        project_memory_root=args.project_memory_root,
        task_center_db=args.task_center_db,
        run_id=args.run_id,
        command_cwd=args.command_cwd,
        agent_mode=args.agent_mode,
        hermes_bin=args.hermes_bin,
        hermes_profile=args.hermes_profile,
        provider=args.provider,
        model=args.model,
        max_turns=args.max_turns,
        agent_timeout_seconds=args.agent_timeout_seconds,
        command_timeout_seconds=args.command_timeout_seconds,
        record_task_center=not args.skip_task_center,
        force=bool(args.force),
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    try:
        report = run_smoke(config_from_args(args))
    except Exception as exc:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "ok": False,
            "error": str(exc),
        }
        if args.emit_json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(f"hermes_profile_smoke failed: {exc}", file=sys.stderr)
        return 1

    if args.emit_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"ok={report['ok']}")
        print(f"agent_mode={report['agent_mode']}")
        print(f"run_dir={report['run_dir']}")
        print(f"report_file={report['report_file']}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
