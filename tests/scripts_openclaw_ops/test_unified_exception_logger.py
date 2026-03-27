#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_unified_exception_logger.py — 统一异常日志器单元测试
"""

import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).resolve().parent.parent.parent / "scripts" / "openclaw-ops" / "unified_exception_logger.py"
_spec = importlib.util.spec_from_file_location("unified_exception_logger", SCRIPT_PATH)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

classify_exception = _mod.classify_exception
extract_exceptions_from_file = _mod.extract_exceptions_from_file
run_exception_scan = _mod.run_exception_scan
build_cli_parser = _mod.build_cli_parser


class TestClassification:
    """异常分类测试。"""

    def test_api_rate_limit(self):
        assert classify_exception("Error: rate limit exceeded for model gpt-4") == "api_error"

    def test_api_429(self):
        assert classify_exception("HTTP 429 Too Many Requests") == "api_error"

    def test_api_timeout(self):
        assert classify_exception("API timeout after 30s") == "api_error"

    def test_file_not_found(self):
        assert classify_exception("FileNotFoundError: /root/config.json") == "filesystem_error"

    def test_permission_denied(self):
        assert classify_exception("Permission denied: /etc/shadow") == "filesystem_error"

    def test_disk_full(self):
        assert classify_exception("No space left on device (ENOSPC)") == "filesystem_error"

    def test_json_parse_error(self):
        assert classify_exception("json parse error at line 42") == "config_error"

    def test_plugin_not_found(self):
        assert classify_exception("plugin 'memory-openviking' not found") == "config_error"

    def test_agent_session_failed(self):
        assert classify_exception("sub-agent session creation failed") == "agent_comm_error"

    def test_agent_dispatch_failed_chinese(self):
        assert classify_exception("子Agent创建失败: timeout") == "agent_comm_error"

    def test_oom(self):
        assert classify_exception("Process killed: out of memory (OOM)") == "system_error"

    def test_traceback(self):
        assert classify_exception("Traceback (most recent call last):") == "system_error"

    def test_generic_error(self):
        assert classify_exception("ERROR: something went wrong") == "generic_error"

    def test_chinese_failure(self):
        assert classify_exception("❌ 部署失败") == "generic_error"

    def test_normal_line_no_match(self):
        assert classify_exception("INFO: Task completed successfully") is None

    def test_empty_line(self):
        assert classify_exception("") is None


class TestFileExtraction:
    """文件级异常提取测试。"""

    def test_extract_from_file_with_errors(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False, encoding="utf-8") as tmp:
            tmp.write("INFO: starting\n")
            tmp.write("ERROR: rate limit exceeded\n")
            tmp.write("INFO: normal\n")
            tmp.write("FileNotFoundError: /missing/file\n")
            tmp.write("INFO: done\n")
            tmp_path = tmp.name

        try:
            exceptions = extract_exceptions_from_file(tmp_path)
            assert len(exceptions) >= 2
            categories = {e["category"] for e in exceptions}
            assert "api_error" in categories
            assert "filesystem_error" in categories
        finally:
            os.unlink(tmp_path)

    def test_extract_from_clean_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False, encoding="utf-8") as tmp:
            tmp.write("INFO: all good\nINFO: no issues\n")
            tmp_path = tmp.name

        try:
            exceptions = extract_exceptions_from_file(tmp_path)
            assert len(exceptions) == 0
        finally:
            os.unlink(tmp_path)

    def test_extract_nonexistent_file(self):
        exceptions = extract_exceptions_from_file("/nonexistent/file.log")
        assert len(exceptions) == 0


class TestFullScan:
    """完整扫描流程测试。"""

    def test_scan_empty_dir(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            result = run_exception_scan(log_dirs=[tmp_dir], dry_run=True)
            assert result["total_exceptions"] == 0
            assert result["alert_level"] == "ok"

    def test_scan_with_errors(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_file = Path(tmp_dir) / "test.log"
            log_file.write_text(
                "ERROR: rate limit\n"
                "FileNotFoundError: /x\n"
                "Traceback (most recent call last):\n"
                "INFO: ok\n",
                encoding="utf-8",
            )
            result = run_exception_scan(
                log_dirs=[tmp_dir],
                dry_run=True,
                scan_since_hours=1,
            )
            assert result["total_exceptions"] >= 3
            assert result["unique_exceptions"] >= 3

    def test_scan_writes_report(self):
        with tempfile.TemporaryDirectory() as log_dir, tempfile.TemporaryDirectory() as out_dir:
            (Path(log_dir) / "err.log").write_text("ERROR: test failure\n", encoding="utf-8")
            run_exception_scan(
                log_dirs=[log_dir],
                output_dir=out_dir,
                dry_run=False,
                scan_since_hours=1,
            )
            json_files = list(Path(out_dir).glob("exception-report-*.json"))
            assert len(json_files) >= 1

    def test_deduplication(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_file = Path(tmp_dir) / "repeated.log"
            # 同一错误重复 5 次
            log_file.write_text("ERROR: rate limit\n" * 5, encoding="utf-8")
            result = run_exception_scan(
                log_dirs=[tmp_dir],
                dry_run=True,
                scan_since_hours=1,
            )
            assert result["total_exceptions"] == 5
            assert result["unique_exceptions"] == 1


class TestCliParser:
    def test_help(self):
        parser = build_cli_parser()
        with pytest.raises(SystemExit) as exc_info:
            parser.parse_args(["--help"])
        assert exc_info.value.code == 0
