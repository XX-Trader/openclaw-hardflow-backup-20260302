#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_workflow_builder.py — Workflow Builder 单元测试
"""

import importlib.util
import sys
import tempfile
from pathlib import Path

import pytest

SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "skills"
    / "library"
    / "openclaw-workflow-manager"
    / "scripts"
    / "workflow_builder.py"
)
_spec = importlib.util.spec_from_file_location("workflow_builder", SCRIPT_PATH)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

classify_step = _mod.classify_step
parse_steps_from_text = _mod.parse_steps_from_text
generate_workflow = _mod.generate_workflow
build_workflow = _mod.build_workflow
build_cli_parser = _mod.build_cli_parser


class TestStepClassification:
    def test_ssh_command(self):
        cat, _ = classify_step("SSH连接到服务器")
        assert cat == "ssh_command"

    def test_scp_transfer(self):
        cat, _ = classify_step("上传文件到远端")
        assert cat == "scp_transfer"

    def test_git_operation(self):
        cat, _ = classify_step("git push提交代码")
        assert cat == "git_operation"

    def test_python_script(self):
        cat, _ = classify_step("执行脚本 deploy.py")
        assert cat == "python_script"

    def test_verification(self):
        cat, _ = classify_step("验证页面是否可访问")
        assert cat == "verification"

    def test_restart(self):
        cat, _ = classify_step("重启 pm2 服务")
        assert cat == "restart_service"

    def test_general(self):
        cat, _ = classify_step("做一些其他事情")
        assert cat == "general"


class TestStepParsing:
    def test_numbered_steps(self):
        text = "1. SSH连接服务器 2. 上传文件 3. 验证部署"
        steps = parse_steps_from_text(text)
        assert len(steps) == 3
        assert steps[0]["number"] == 1
        assert steps[2]["category"] == "verification"

    def test_semicolon_steps(self):
        text = "git commit; git push; 验证推送成功"
        steps = parse_steps_from_text(text)
        assert len(steps) == 3

    def test_newline_steps(self):
        text = "SSH连接\n上传文件\n重启服务"
        steps = parse_steps_from_text(text)
        assert len(steps) == 3

    def test_empty_text(self):
        steps = parse_steps_from_text("")
        assert len(steps) == 0


class TestWorkflowGeneration:
    def test_basic_workflow(self):
        steps = [
            {"number": 1, "description": "SSH连接", "category": "ssh_command", "safe": False},
            {"number": 2, "description": "验证服务", "category": "verification", "safe": True},
        ]
        content = generate_workflow("测试", "测试工作流", steps)
        assert "---" in content
        assert "description: 测试工作流" in content
        assert "SSH连接" in content

    def test_turbo_all(self):
        steps = [{"number": 1, "description": "测试", "category": "general", "safe": True}]
        content = generate_workflow("测试", "desc", steps, turbo_all=True)
        assert "// turbo-all" in content

    def test_with_preconditions(self):
        steps = [{"number": 1, "description": "部署", "category": "general", "safe": True}]
        content = generate_workflow("测试", "desc", steps, preconditions=["SSH可连通"])
        assert "前置条件" in content
        assert "SSH可连通" in content


class TestBuildWorkflow:
    def test_build_to_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            out = Path(tmp_dir) / "test-workflow.md"
            result = build_workflow(
                title="测试工作流",
                description="用于测试",
                steps_text="1. SSH连接 2. 上传文件 3. 验证",
                output_path=str(out),
            )
            assert result["steps_count"] == 3
            assert out.exists()

    def test_build_dry(self):
        result = build_workflow(
            title="测试",
            description="desc",
            steps_text="1. 检查服务状态",
        )
        assert result["steps_count"] == 1


class TestCliParser:
    def test_help(self):
        parser = build_cli_parser()
        with pytest.raises(SystemExit) as exc_info:
            parser.parse_args(["--help"])
        assert exc_info.value.code == 0
