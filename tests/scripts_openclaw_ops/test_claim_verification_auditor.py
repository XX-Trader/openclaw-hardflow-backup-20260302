#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_claim_verification_auditor.py — claim_verification_auditor 单元测试

覆盖：
- CLI 入口可调用
- 声明提取正则匹配
- 文件存在性验证
- 进度声明标记
- 审计报告生成
- dry-run 不写文件
"""

import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

# 动态导入 scripts/openclaw-ops/claim_verification_auditor.py
SCRIPT_PATH = Path(__file__).resolve().parent.parent.parent / "scripts" / "openclaw-ops" / "claim_verification_auditor.py"
_spec = importlib.util.spec_from_file_location("claim_verification_auditor", SCRIPT_PATH)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

build_cli_parser = _mod.build_cli_parser
extract_claims_from_text = _mod.extract_claims_from_text
run_audit = _mod.run_audit
verify_file_exists = _mod.verify_file_exists
verify_progress = _mod.verify_progress
verify_resource_consumption = _mod.verify_resource_consumption


class TestCliEntrypoint:
    """CLI 入口可调用性测试。"""

    def test_help_does_not_crash(self):
        """--help 不应崩溃。"""
        parser = build_cli_parser()
        with pytest.raises(SystemExit) as exc_info:
            parser.parse_args(["--help"])
        assert exc_info.value.code == 0


class TestClaimExtraction:
    """声明提取正则匹配测试。"""

    def test_extract_file_creation_claim_chinese(self):
        """中文「已创建文件」声明应被提取。"""
        text = "已创建文件 `/root/test/output.json`"
        claims = extract_claims_from_text(text)
        assert len(claims) >= 1
        assert any(c["claim_type"] == "file_operation" for c in claims)

    def test_extract_file_modification_claim(self):
        """「已修改」声明应被提取。"""
        text = "已修改了 config.json 的内容"
        claims = extract_claims_from_text(text)
        assert any(c["claim_type"] == "file_operation" for c in claims)

    def test_extract_progress_claim(self):
        """「进度 XX%」声明应被提取。"""
        text = "当前进度: 78%"
        claims = extract_claims_from_text(text)
        assert any(c["claim_type"] == "progress_report" for c in claims)
        progress_claims = [c for c in claims if c["claim_type"] == "progress_report"]
        assert progress_claims[0]["captured_group"] == "78"

    def test_extract_progress_claim_alternate_format(self):
        """「85%完成」格式也应被提取。"""
        text = "整体85%完成"
        claims = extract_claims_from_text(text)
        assert any(c["claim_type"] == "progress_report" for c in claims)

    def test_extract_task_dispatch_claim(self):
        """「已派发」声明应被提取。"""
        text = "已派发任务给 optimization-agent"
        claims = extract_claims_from_text(text)
        assert any(c["claim_type"] == "task_dispatch" for c in claims)

    def test_extract_session_creation_claim(self):
        """「已创建3个子Agent」声明应被提取。"""
        text = "已创建3个子Agent会话"
        claims = extract_claims_from_text(text)
        assert any(c["claim_type"] == "session_creation" for c in claims)

    def test_extract_token_consumption_claim(self):
        """Token 消耗声明应被提取。"""
        text = "Token消耗: ~3.2万"
        claims = extract_claims_from_text(text)
        assert any(c["claim_type"] == "resource_consumption" for c in claims)

    def test_extract_time_consumption_claim(self):
        """耗时声明应被提取。"""
        text = "耗时: 2.5小时"
        claims = extract_claims_from_text(text)
        assert any(c["claim_type"] == "resource_consumption" for c in claims)

    def test_no_false_positives_on_normal_text(self):
        """普通文本不应产生误报。"""
        text = "今天天气很好，我们来讨论一下项目进展。"
        claims = extract_claims_from_text(text)
        assert len(claims) == 0

    def test_line_number_tracking(self):
        """应正确追踪声明所在行号。"""
        text = "第一行\n第二行\n已创建文件 test.py\n第四行"
        claims = extract_claims_from_text(text)
        file_claims = [c for c in claims if c["claim_type"] == "file_operation"]
        assert len(file_claims) >= 1
        assert file_claims[0]["line_number"] == 3


class TestFileVerification:
    """文件存在性验证测试。"""

    def test_verify_existing_file(self):
        """存在的文件应返回 verified。"""
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as tmp_file:
            tmp_file.write(b"test content")
            tmp_path = tmp_file.name

        try:
            claim = {"captured_group": tmp_path}
            result = verify_file_exists(claim)
            assert result["status"] == "verified"
            assert "test content" not in result["detail"]  # 不泄露文件内容
            assert result["evidence"]["size_bytes"] > 0
        finally:
            os.unlink(tmp_path)

    def test_verify_nonexistent_file(self):
        """不存在的文件应返回 inconsistent。"""
        claim = {"captured_group": "/nonexistent/path/fake_file_12345.txt"}
        result = verify_file_exists(claim)
        assert result["status"] == "inconsistent"

    def test_verify_no_path(self):
        """无文件路径应返回 unverifiable。"""
        claim = {"captured_group": None}
        result = verify_file_exists(claim)
        assert result["status"] == "unverifiable"


class TestProgressVerification:
    """进度声明验证测试。"""

    def test_progress_always_needs_review(self):
        """进度声明应始终标记为需人工审查。"""
        claim = {"captured_group": "85"}
        result = verify_progress(claim)
        assert result["status"] == "needs_human_review"
        assert "85" in result["detail"]


class TestResourceConsumptionVerification:
    """资源消耗声明验证测试。"""

    def test_resource_consumption_needs_review(self):
        """资源消耗声明应标记为需人工审查。"""
        claim = {"captured_group": "3.2"}
        result = verify_resource_consumption(claim)
        assert result["status"] == "needs_human_review"


class TestAuditRun:
    """完整审计流程测试。"""

    def test_audit_with_empty_dir(self):
        """空目录应返回 0 声明。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            result = run_audit(
                session_log_dir=tmp_dir,
                output_dir=None,
                dry_run=True,
            )
            assert result.get("claims_found", 0) == 0

    def test_audit_with_claims_in_log(self):
        """含声明的日志应被正确提取和验证。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_file = Path(tmp_dir) / "test-session.log"
            log_file.write_text(
                "已创建文件 /nonexistent/fake_output.json\n"
                "进度: 65%\n"
                "Token消耗: ~2.8万\n"
                "正常讨论内容，不含声明\n",
                encoding="utf-8",
            )

            result = run_audit(
                session_log_dir=tmp_dir,
                output_dir=None,
                dry_run=True,
                scan_since_hours=1,
            )
            assert result.get("claims_found", 0) >= 3

    def test_audit_writes_report_when_not_dry_run(self):
        """非 dry-run 模式应写入报告文件。"""
        with tempfile.TemporaryDirectory() as log_dir, tempfile.TemporaryDirectory() as output_dir:
            log_file = Path(log_dir) / "session.log"
            log_file.write_text("已创建文件 test.py\n", encoding="utf-8")

            run_audit(
                session_log_dir=log_dir,
                output_dir=output_dir,
                dry_run=False,
                scan_since_hours=1,
            )

            output_files = list(Path(output_dir).glob("claim-audit-*.json"))
            assert len(output_files) >= 1

            report_content = json.loads(output_files[0].read_text(encoding="utf-8"))
            assert "summary" in report_content
            assert "details" in report_content

    def test_audit_nonexistent_dir_returns_error(self):
        """不存在的日志目录应返回错误。"""
        result = run_audit(
            session_log_dir="/nonexistent/path/12345",
            output_dir=None,
            dry_run=True,
        )
        assert "error" in result
