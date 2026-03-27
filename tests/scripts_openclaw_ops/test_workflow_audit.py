#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_workflow_audit.py — 工作流审计脚本单元测试
"""

import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).resolve().parent.parent.parent / "scripts" / "openclaw-ops" / "workflow_audit.py"
_spec = importlib.util.spec_from_file_location("workflow_audit", SCRIPT_PATH)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

parse_session_logs = _mod.parse_session_logs
compute_audit_score = _mod.compute_audit_score
run_audit = _mod.run_audit
build_cli_parser = _mod.build_cli_parser


class TestSessionParsing:
    """会话解析测试。"""

    def test_parse_session_with_logs(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_file = Path(tmp_dir) / "session.log"
            log_file.write_text(
                "✅ 完成任务 A\n"
                "INFO: 中间步骤\n"
                "已创建文件 `output.py`\n"
                "3/3 测试通过\n"
                "❌ 部署失败\n",
                encoding="utf-8",
            )
            result = parse_session_logs(tmp_dir)
            assert result["log_files_count"] >= 1
            assert len(result["tasks"]) >= 2  # 完成 + 失败
            assert len(result["claims"]) >= 2  # 文件创建 + 测试通过

    def test_parse_empty_session(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            result = parse_session_logs(tmp_dir)
            assert result["total_lines"] == 0
            assert len(result["tasks"]) == 0

    def test_parse_nonexistent_dir(self):
        result = parse_session_logs("/nonexistent/session/")
        assert "error" in result


class TestAuditScoring:
    """审计评分测试。"""

    def test_healthy_session_score(self):
        parsed = {
            "total_lines": 100,
            "tasks": [
                {"status": "completed"},
                {"status": "completed"},
                {"status": "completed"},
            ],
            "claims": [
                {"type": "file_created", "match": "test"},
                {"type": "test_passed", "match": "3/3"},
            ],
            "errors": [],
        }
        score = compute_audit_score(parsed)
        assert score["completion_rate"] == 100
        assert score["integrity_score"] >= 50

    def test_session_with_failures(self):
        parsed = {
            "total_lines": 50,
            "tasks": [
                {"status": "completed"},
                {"status": "failed"},
                {"status": "failed"},
            ],
            "claims": [{"type": "progress_pct", "match": "80%"}],
            "errors": [{"line": "ERROR: crashed"}],
        }
        score = compute_audit_score(parsed)
        assert score["completion_rate"] < 50
        assert score["failed"] == 2

    def test_empty_session_score(self):
        parsed = {"total_lines": 0, "tasks": [], "claims": [], "errors": []}
        score = compute_audit_score(parsed)
        assert score["integrity_score"] == 50  # 无数据给中间分


class TestFullAudit:
    """完整审计流程测试。"""

    def test_summary_mode(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            (Path(tmp_dir) / "test.log").write_text("✅ 完成\n", encoding="utf-8")
            result = run_audit(session_dir=tmp_dir, mode="summary", dry_run=True)
            assert result["sessions_audited"] == 1

    def test_detail_mode(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            (Path(tmp_dir) / "test.log").write_text(
                "✅ 完成任务\n已创建文件 out.py\n❌ 失败\n",
                encoding="utf-8",
            )
            result = run_audit(session_dir=tmp_dir, mode="detail", dry_run=True)
            assert result["sessions_audited"] == 1

    def test_batch_mode(self):
        with tempfile.TemporaryDirectory() as parent_dir:
            s1 = Path(parent_dir) / "session-1"
            s1.mkdir()
            (s1 / "log.txt").write_text("✅ done\n", encoding="utf-8")

            s2 = Path(parent_dir) / "session-2"
            s2.mkdir()
            (s2 / "log.txt").write_text("❌ failed\n", encoding="utf-8")

            result = run_audit(session_dir=parent_dir, mode="summary", batch=True, dry_run=True, since_hours=1)
            assert result["sessions_audited"] >= 2

    def test_writes_report(self):
        with tempfile.TemporaryDirectory() as session_dir, tempfile.TemporaryDirectory() as out_dir:
            (Path(session_dir) / "test.log").write_text("✅ 完成\n", encoding="utf-8")
            run_audit(session_dir=session_dir, output_dir=out_dir, dry_run=False)
            json_files = list(Path(out_dir).glob("audit-*.json"))
            assert len(json_files) >= 1


class TestCliParser:
    def test_help(self):
        parser = build_cli_parser()
        with pytest.raises(SystemExit) as exc_info:
            parser.parse_args(["--help"])
        assert exc_info.value.code == 0
