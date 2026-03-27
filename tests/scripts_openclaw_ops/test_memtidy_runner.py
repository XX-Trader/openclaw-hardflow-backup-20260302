#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_memtidy_runner.py — MemTidy 记忆整理工具单元测试

覆盖：
- 规则加载
- 文件分类（热/温/冷/修剪/保护）
- 文件压缩
- 文件归档
- 文件修剪
- 完整 dry-run 流程
"""

import importlib.util
import json
import os
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest

# 动态导入
SCRIPT_PATH = Path(__file__).resolve().parent.parent.parent / "scripts" / "openclaw-ops" / "memtidy_runner.py"
_spec = importlib.util.spec_from_file_location("memtidy_runner", SCRIPT_PATH)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

load_rules = _mod.load_rules
classify_file = _mod.classify_file
compact_file = _mod.compact_file
archive_file = _mod.archive_file
prune_file = _mod.prune_file
run_memtidy = _mod.run_memtidy
build_cli_parser = _mod.build_cli_parser
DEFAULT_RULES = _mod.DEFAULT_RULES


class TestRulesLoading:
    """规则加载测试。"""

    def test_default_rules_returned_when_no_file(self):
        """未指定文件时返回默认规则。"""
        rules = load_rules(None)
        assert "hot_memory" in rules
        assert "cold_memory" in rules

    def test_load_rules_from_file(self):
        """从文件加载规则。"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as tmp:
            json.dump({"hot_memory": {"days": 7}}, tmp)
            tmp_path = tmp.name

        try:
            rules = load_rules(tmp_path)
            assert rules["hot_memory"]["days"] == 7
        finally:
            os.unlink(tmp_path)

    def test_load_nonexistent_file_raises(self):
        """不存在的规则文件应抛出 FileNotFoundError。"""
        with pytest.raises(FileNotFoundError):
            load_rules("/nonexistent/rules.json")


class TestFileClassification:
    """文件分类测试。"""

    def test_protected_memory_md(self):
        """MEMORY.md 应为 protected。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            memory_file = Path(tmp_dir) / "MEMORY.md"
            memory_file.write_text("core memory", encoding="utf-8")
            result = classify_file(memory_file, DEFAULT_RULES)
            assert result == "protected"

    def test_protected_core_identity(self):
        """core-identity 文件应为 protected。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            identity_file = Path(tmp_dir) / "core-identity.md"
            identity_file.write_text("identity", encoding="utf-8")
            result = classify_file(identity_file, DEFAULT_RULES)
            assert result == "protected"

    def test_prune_test_session(self):
        """包含 test_session 的文件应为 prune。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            test_file = Path(tmp_dir) / "test_session_20260101.md"
            test_file.write_text("test", encoding="utf-8")
            result = classify_file(test_file, DEFAULT_RULES)
            assert result == "prune"

    def test_prune_empty_file(self):
        """空文件应为 prune。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            empty_file = Path(tmp_dir) / "empty.md"
            empty_file.write_text("", encoding="utf-8")
            result = classify_file(empty_file, DEFAULT_RULES)
            assert result == "prune"

    def test_hot_file_recent(self):
        """刚创建的文件应为 hot。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            hot_file = Path(tmp_dir) / "recent-note.md"
            hot_file.write_text("recent content", encoding="utf-8")
            result = classify_file(hot_file, DEFAULT_RULES, now=datetime.now())
            assert result == "hot"

    def test_warm_file_60_days_old(self):
        """60天前的文件应为 warm。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            warm_file = Path(tmp_dir) / "old-note.md"
            warm_file.write_text("old content", encoding="utf-8")
            # 手动设置修改时间为60天前
            old_time = time.time() - 60 * 86400
            os.utime(str(warm_file), (old_time, old_time))
            result = classify_file(warm_file, DEFAULT_RULES, now=datetime.now())
            assert result == "warm"

    def test_cold_file_200_days_old(self):
        """200天前的文件应为 cold。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            cold_file = Path(tmp_dir) / "ancient-note.md"
            cold_file.write_text("ancient content", encoding="utf-8")
            old_time = time.time() - 200 * 86400
            os.utime(str(cold_file), (old_time, old_time))
            result = classify_file(cold_file, DEFAULT_RULES, now=datetime.now())
            assert result == "cold"


class TestCompactFile:
    """文件压缩测试。"""

    def test_skip_short_file(self):
        """短文件不应被压缩。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            short_file = Path(tmp_dir) / "short.md"
            short_file.write_text("\n".join([f"line {i}" for i in range(50)]), encoding="utf-8")
            result = compact_file(short_file, DEFAULT_RULES)
            assert result["action"] == "skip"

    def test_compact_long_file(self):
        """超长文件应被压缩。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            long_file = Path(tmp_dir) / "long.md"
            long_file.write_text("\n".join([f"line {i}" for i in range(300)]), encoding="utf-8")
            result = compact_file(long_file, DEFAULT_RULES, dry_run=False)
            assert result["action"] == "compacted"
            assert result["original_lines"] == 300
            assert result["compacted_lines"] < 300

            # 验证文件确实被修改了
            content = long_file.read_text(encoding="utf-8")
            assert "MemTidy" in content

    def test_compact_dry_run_preserves_file(self):
        """dry-run 不应修改文件。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            long_file = Path(tmp_dir) / "long.md"
            original_content = "\n".join([f"line {i}" for i in range(300)])
            long_file.write_text(original_content, encoding="utf-8")
            result = compact_file(long_file, DEFAULT_RULES, dry_run=True)
            assert result["action"] == "compacted"
            assert result["dry_run"] is True
            # 文件应保持不变
            assert long_file.read_text(encoding="utf-8") == original_content


class TestArchiveFile:
    """文件归档测试。"""

    def test_archive_moves_file(self):
        """归档应将文件移入目标目录。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            source_file = Path(tmp_dir) / "old-memory.md"
            source_file.write_text("old content", encoding="utf-8")
            archive_dir = Path(tmp_dir) / "archive"

            result = archive_file(source_file, str(archive_dir), dry_run=False)
            assert result["action"] == "archived"
            assert not source_file.exists()
            assert Path(result["destination"]).exists()

    def test_archive_dry_run_preserves_file(self):
        """dry-run 归档不应移动文件。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            source_file = Path(tmp_dir) / "old-memory.md"
            source_file.write_text("old content", encoding="utf-8")
            archive_dir = Path(tmp_dir) / "archive"

            result = archive_file(source_file, str(archive_dir), dry_run=True)
            assert result["action"] == "archived"
            assert result["dry_run"] is True
            assert source_file.exists()


class TestPruneFile:
    """文件修剪测试。"""

    def test_prune_deletes_file(self):
        """修剪应删除文件。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            trash_file = Path(tmp_dir) / "trash.md"
            trash_file.write_text("garbage", encoding="utf-8")
            result = prune_file(trash_file, dry_run=False)
            assert result["action"] == "pruned"
            assert not trash_file.exists()

    def test_prune_dry_run_preserves_file(self):
        """dry-run 修剪不应删除文件。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            trash_file = Path(tmp_dir) / "trash.md"
            trash_file.write_text("garbage", encoding="utf-8")
            result = prune_file(trash_file, dry_run=True)
            assert result["action"] == "pruned"
            assert result["dry_run"] is True
            assert trash_file.exists()


class TestFullDryRun:
    """完整 dry-run 流程测试。"""

    def test_dry_run_reports_without_changes(self):
        """dry-run 应生成报告但不修改任何文件。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            # 创建测试文件
            (Path(tmp_dir) / "MEMORY.md").write_text("protected", encoding="utf-8")
            (Path(tmp_dir) / "recent.md").write_text("hot content", encoding="utf-8")
            empty_file = Path(tmp_dir) / "empty.md"
            empty_file.write_text("", encoding="utf-8")

            result = run_memtidy(
                memory_dirs=[tmp_dir],
                rules=DEFAULT_RULES,
                dry_run=True,
            )

            assert result["dry_run"] is True
            assert result["scanned"] >= 3
            assert result["protected"] >= 1
            # empty 文件应仍然存在
            assert empty_file.exists()

    def test_cli_parser_help(self):
        """CLI --help 不应崩溃。"""
        parser = build_cli_parser()
        with pytest.raises(SystemExit) as exc_info:
            parser.parse_args(["--help"])
        assert exc_info.value.code == 0
