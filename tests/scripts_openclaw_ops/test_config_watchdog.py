#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_config_watchdog.py — Config Watchdog 单元测试

覆盖：
- 文件 hash 计算
- 快照创建
- 变更检测
- JSON 语法校验
- 回滚功能
- 完整流程
"""

import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

# 动态导入
SCRIPT_PATH = Path(__file__).resolve().parent.parent.parent / "scripts" / "openclaw-ops" / "config_watchdog.py"
_spec = importlib.util.spec_from_file_location("config_watchdog", SCRIPT_PATH)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

compute_file_hash = _mod.compute_file_hash
take_snapshot = _mod.take_snapshot
verify_against_snapshot = _mod.verify_against_snapshot
validate_json_file = _mod.validate_json_file
rollback_file = _mod.rollback_file
run_watchdog = _mod.run_watchdog
build_cli_parser = _mod.build_cli_parser
SNAPSHOT_DIR_NAME = _mod.SNAPSHOT_DIR_NAME


def _create_mock_config_dir(base_dir):
    """创建模拟的配置目录结构。"""
    root = Path(base_dir)
    (root / "openclaw.json").write_text(json.dumps({
        "agents": {"list": []},
        "models": {"default": "gpt-4"},
        "hooks": [],
    }, indent=2), encoding="utf-8")
    (root / "cron").mkdir(exist_ok=True)
    (root / "cron" / "jobs.json").write_text(json.dumps({"jobs": []}, indent=2), encoding="utf-8")
    (root / "agents" / "main").mkdir(parents=True, exist_ok=True)
    (root / "agents" / "main" / "SOUL.md").write_text("# Main Agent Soul", encoding="utf-8")
    return root


class TestFileHash:
    """文件 hash 测试。"""

    def test_hash_consistency(self):
        """相同内容应产生相同 hash。"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as tmp:
            tmp.write('{"test": true}')
            tmp_path = tmp.name
        try:
            hash1 = compute_file_hash(tmp_path)
            hash2 = compute_file_hash(tmp_path)
            assert hash1 == hash2
            assert len(hash1) == 64  # SHA-256 = 64 hex chars
        finally:
            os.unlink(tmp_path)

    def test_hash_nonexistent_returns_none(self):
        """不存在文件应返回 None。"""
        result = compute_file_hash("/nonexistent/file.json")
        assert result is None

    def test_different_content_different_hash(self):
        """不同内容应产生不同 hash。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            file_a = Path(tmp_dir) / "a.json"
            file_b = Path(tmp_dir) / "b.json"
            file_a.write_text("content_a", encoding="utf-8")
            file_b.write_text("content_b", encoding="utf-8")
            assert compute_file_hash(str(file_a)) != compute_file_hash(str(file_b))


class TestSnapshot:
    """快照测试。"""

    def test_snapshot_creates_files_and_manifest(self):
        """快照应创建文件副本和 manifest.json。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_root = _create_mock_config_dir(tmp_dir)
            backup_dir = Path(tmp_dir) / "backups"

            result = take_snapshot(str(config_root), str(backup_dir))
            assert result["file_count"] >= 2
            assert "snapshot_id" in result
            assert "hashes" in result

            # 验证 manifest 存在
            snapshot_dir = backup_dir / result["snapshot_id"]
            manifest = snapshot_dir / "manifest.json"
            assert manifest.exists()

    def test_snapshot_preserves_content(self):
        """快照备份的文件内容应与原文件一致。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_root = _create_mock_config_dir(tmp_dir)
            backup_dir = Path(tmp_dir) / "backups"

            result = take_snapshot(str(config_root), str(backup_dir))
            snapshot_dir = backup_dir / result["snapshot_id"]

            original = (config_root / "openclaw.json").read_text(encoding="utf-8")
            backup = (snapshot_dir / "openclaw.json").read_text(encoding="utf-8")
            assert original == backup


class TestVerifyChanges:
    """变更检测测试。"""

    def test_no_changes_detected(self):
        """未修改应报告无变更。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_root = _create_mock_config_dir(tmp_dir)
            backup_dir = Path(tmp_dir) / "backups"

            take_snapshot(str(config_root), str(backup_dir))
            result = verify_against_snapshot(str(config_root), str(backup_dir))
            assert result["status"] == "no_changes"

    def test_changes_detected_after_modification(self):
        """修改后应检测到变更。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_root = _create_mock_config_dir(tmp_dir)
            backup_dir = Path(tmp_dir) / "backups"

            take_snapshot(str(config_root), str(backup_dir))

            # 修改文件
            openclaw_path = config_root / "openclaw.json"
            openclaw_path.write_text(json.dumps({"modified": True}), encoding="utf-8")

            result = verify_against_snapshot(str(config_root), str(backup_dir))
            assert result["status"] == "changes_detected"
            assert "openclaw.json" in result["changed"]

    def test_no_snapshot_available(self):
        """无快照时应报告。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_root = _create_mock_config_dir(tmp_dir)
            result = verify_against_snapshot(str(config_root), str(Path(tmp_dir) / "empty-backups"))
            assert result["status"] == "no_snapshot"


class TestJsonValidation:
    """JSON 语法校验测试。"""

    def test_valid_json(self):
        """合法 JSON 应通过校验。"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as tmp:
            json.dump({"valid": True}, tmp)
            tmp_path = tmp.name
        try:
            result = validate_json_file(tmp_path)
            assert result["valid"] is True
        finally:
            os.unlink(tmp_path)

    def test_invalid_json(self):
        """非法 JSON 应报告错误。"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as tmp:
            tmp.write("{invalid json: missing quotes}")
            tmp_path = tmp.name
        try:
            result = validate_json_file(tmp_path)
            assert result["valid"] is False
            assert result["error"] is not None
        finally:
            os.unlink(tmp_path)

    def test_nonexistent_file(self):
        """不存在的文件应报错。"""
        result = validate_json_file("/nonexistent/file.json")
        assert result["valid"] is False


class TestRollback:
    """回滚测试。"""

    def test_rollback_restores_file(self):
        """回滚应恢复文件到快照版本。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_root = _create_mock_config_dir(tmp_dir)
            backup_dir = Path(tmp_dir) / "backups"

            # 先快照
            take_snapshot(str(config_root), str(backup_dir))

            # 破坏文件
            openclaw_path = config_root / "openclaw.json"
            original_content = openclaw_path.read_text(encoding="utf-8")
            openclaw_path.write_text("BROKEN!", encoding="utf-8")

            # 回滚
            result = rollback_file(str(config_root), "openclaw.json", str(backup_dir))
            assert result["status"] == "rolled_back"

            # 验证恢复
            restored = openclaw_path.read_text(encoding="utf-8")
            assert restored == original_content

    def test_rollback_dry_run(self):
        """dry-run 回滚不应修改文件。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_root = _create_mock_config_dir(tmp_dir)
            backup_dir = Path(tmp_dir) / "backups"

            take_snapshot(str(config_root), str(backup_dir))
            openclaw_path = config_root / "openclaw.json"
            openclaw_path.write_text("BROKEN!", encoding="utf-8")

            result = rollback_file(str(config_root), "openclaw.json", str(backup_dir), dry_run=True)
            assert result["status"] == "rolled_back"
            assert result["dry_run"] is True
            # 文件应仍然是损坏的
            assert openclaw_path.read_text(encoding="utf-8") == "BROKEN!"

    def test_rollback_no_snapshot(self):
        """无快照时回滚应失败。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_root = _create_mock_config_dir(tmp_dir)
            result = rollback_file(str(config_root), "openclaw.json", str(Path(tmp_dir) / "empty"))
            assert result["status"] == "failed"


class TestCliParser:
    """CLI 参数解析测试。"""

    def test_help_does_not_crash(self):
        """--help 不应崩溃。"""
        parser = build_cli_parser()
        with pytest.raises(SystemExit) as exc_info:
            parser.parse_args(["--help"])
        assert exc_info.value.code == 0
