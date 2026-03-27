#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_fault_knowledge_base.py — 故障知识库单元测试
"""

import importlib.util
import json
import sys
import tempfile
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).resolve().parent.parent.parent / "scripts" / "openclaw-ops" / "fault_knowledge_base.py"
_spec = importlib.util.spec_from_file_location("fault_knowledge_base", SCRIPT_PATH)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

classify_fault = _mod.classify_fault
parse_fault_document = _mod.parse_fault_document
build_knowledge_index = _mod.build_knowledge_index
query_knowledge_base = _mod.query_knowledge_base
format_query_results = _mod.format_query_results
build_cli_parser = _mod.build_cli_parser


class TestFaultClassification:
    def test_config_fault(self):
        matches = classify_fault("JSON配置文件解析错误，插件引用缺失")
        categories = [m[0] for m in matches]
        assert "config_fault" in categories

    def test_cron_fault(self):
        matches = classify_fault("定时任务不执行，cron调度卡住")
        categories = [m[0] for m in matches]
        assert "cron_fault" in categories

    def test_deploy_fault(self):
        matches = classify_fault("部署到服务器失败，SSH连接超时")
        categories = [m[0] for m in matches]
        assert "deploy_fault" in categories

    def test_agent_fault(self):
        matches = classify_fault("Agent会话创建失败，模型API rate limit")
        categories = [m[0] for m in matches]
        assert "agent_fault" in categories

    def test_no_match(self):
        matches = classify_fault("今天天气真好")
        assert len(matches) == 0


class TestDocumentParsing:
    def test_parse_fault_doc(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8", prefix="2026-03-14-") as tmp:
            tmp.write("# 配置启动失败问题\n\n## 问题描述\n\n- JSON语法错误\n- 插件引用缺失\n\n## 修复步骤\n\n1. 检查JSON格式\n2. 删除无效插件引用\n\n## 相关文件\n\n- `cron/jobs.json`\n- `config_watchdog.py`\n")
            tmp_path = tmp.name

        try:
            result = parse_fault_document(tmp_path)
            assert result is not None
            assert "配置启动失败" in result["title"]
            assert len(result["symptoms"]) >= 1
            assert len(result["fixes"]) >= 1
            assert len(result["file_refs"]) >= 1
        finally:
            Path(tmp_path).unlink()

    def test_parse_nonexistent(self):
        result = parse_fault_document("/nonexistent/doc.md")
        assert result is None


class TestKnowledgeIndex:
    def test_build_index(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            (Path(tmp_dir) / "2026-03-14-故障A.md").write_text("# 故障A\n\n## 问题\n\n- cron任务卡住\n\n## 修复\n\n1. 清理任务状态\n", encoding="utf-8")
            (Path(tmp_dir) / "2026-03-15-故障B.md").write_text("# 故障B\n\n## 问题\n\n- SSH连接超时\n\n## 修复\n\n1. 检查网络\n", encoding="utf-8")

            index = build_knowledge_index(tmp_dir)
            assert index["total_entries"] == 2

    def test_build_and_save_index(self):
        with tempfile.TemporaryDirectory() as docs_dir, tempfile.TemporaryDirectory() as out_dir:
            (Path(docs_dir) / "2026-03-14-test.md").write_text("# 测试故障\n\n## 问题\n\n- 配置错误\n", encoding="utf-8")
            out_path = Path(out_dir) / "index.json"
            index = build_knowledge_index(docs_dir, str(out_path))
            assert out_path.exists()
            loaded = json.loads(out_path.read_text(encoding="utf-8"))
            assert loaded["total_entries"] == 1


class TestQueryEngine:
    def _build_test_index(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            (Path(tmp_dir) / "2026-03-14-cron故障.md").write_text("# 定时任务不执行\n\n## 问题\n\n- cron卡住\n- executor超时\n\n## 修复\n\n1. 清理running状态\n2. 重启调度器\n", encoding="utf-8")
            (Path(tmp_dir) / "2026-03-15-配置错误.md").write_text("# JSON配置启动失败\n\n## 问题\n\n- 插件引用缺失\n- JSON语法错误\n\n## 修复\n\n1. 检查JSON格式\n", encoding="utf-8")
            (Path(tmp_dir) / "2026-03-16-SSH故障.md").write_text("# 部署失败SSH超时\n\n## 问题\n\n- SSH连接refused\n\n## 修复\n\n1. 检查服务器防火墙\n", encoding="utf-8")
            return build_knowledge_index(tmp_dir)

    def test_query_by_keyword(self):
        index = self._build_test_index()
        results = query_knowledge_base(index, "cron任务不执行")
        assert len(results) >= 1
        titles = [r["entry"]["title"] for r in results]
        assert any("cron" in t.lower() or "定时" in t for t in titles)

    def test_query_config(self):
        index = self._build_test_index()
        results = query_knowledge_base(index, "JSON配置文件错误")
        assert len(results) >= 1

    def test_query_no_match(self):
        index = self._build_test_index()
        results = query_knowledge_base(index, "量子计算芯片故障")
        # 可能有 0 或极低相关度结果
        assert isinstance(results, list)

    def test_format_results(self):
        index = self._build_test_index()
        results = query_knowledge_base(index, "SSH部署")
        md = format_query_results(results, "SSH部署")
        assert "故障知识库查询结果" in md


class TestCliParser:
    def test_help(self):
        parser = build_cli_parser()
        with pytest.raises(SystemExit) as exc_info:
            parser.parse_args(["--help"])
        assert exc_info.value.code == 0
