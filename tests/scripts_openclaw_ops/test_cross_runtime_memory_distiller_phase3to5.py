"""Phase 3-5 综合测试：evidence_store, source_adapters, cleaner, classifier, reporter, skill_draft_generator。"""

import json
import sqlite3
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]

import importlib.util
import sys


def load_module(name: str, rel_path: str):
    """动态加载模块。"""
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


es = load_module("evidence_store", "skills/library/cross-runtime-memory-distiller/scripts/evidence_store.py")
sa = load_module("distill_source_adapters", "skills/library/cross-runtime-memory-distiller/scripts/distill_source_adapters.py")
dc = load_module("distill_cleaner", "skills/library/cross-runtime-memory-distiller/scripts/distill_cleaner.py")
clf = load_module("distill_classifier", "skills/library/cross-runtime-memory-distiller/scripts/distill_classifier.py")
dr = load_module("distill_reporter", "skills/library/cross-runtime-memory-distiller/scripts/distill_reporter.py")
sdg = load_module("skill_draft_generator", "skills/library/cross-runtime-memory-distiller/scripts/skill_draft_generator.py")


# ── EvidenceStore 测试 ────────────────────────────────────────────────


class TestEvidenceStore(unittest.TestCase):
    """SQLite 证据存储层测试。"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.store = es.EvidenceStore(Path(self.tmpdir) / "test_distill.db")

    def tearDown(self):
        self.store.close()

    def test_initialize_creates_tables(self):
        stats = self.store.stats()
        self.assertEqual(stats["normalized_events"], 0)
        self.assertEqual(stats["ingest_cursors"], 0)

    def test_next_id_generates_unique(self):
        id1 = self.store.next_id("artifact")
        id2 = self.store.next_id("artifact")
        self.assertNotEqual(id1, id2)
        self.assertTrue(id1.startswith("artifact_"))

    def test_upsert_and_query_events(self):
        events = [{
            "event_id": "claude:ses001:0",
            "source": "claude",
            "host": "openclaw",
            "project": "test",
            "session_id": "claude:ses001",
            "role": "user",
            "content": "测试内容",
            "timestamp": "2026-04-16T10:00:00Z",
            "metadata": {"tool_name": "Bash"},
        }]
        count = self.store.upsert_events(events)
        self.assertEqual(count, 1)

        result = self.store.query_events(source="claude")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["content"], "测试内容")

    def test_upsert_idempotent(self):
        events = [{
            "event_id": "claude:ses001:0",
            "source": "claude", "host": "openclaw", "project": "test",
            "session_id": "claude:ses001", "role": "user",
            "content": "内容", "timestamp": "2026-04-16T10:00:00Z",
        }]
        self.store.upsert_events(events)
        self.store.upsert_events(events)  # 幂等
        self.assertEqual(self.store.stats()["normalized_events"], 1)

    def test_cursor_read_write(self):
        self.store.set_cursor("claude", "openclaw", "test", {"last_mtime": "2026-04-16T10:00:00Z", "last_offset": 42})
        cursor = self.store.get_cursor("claude", "openclaw", "test")
        self.assertIsNotNone(cursor)
        self.assertEqual(cursor["cursor_value"]["last_offset"], 42)

    def test_candidate_upsert_and_query(self):
        self.store.upsert_candidate({
            "candidate_id": "cand_001",
            "event_ids": ["claude:ses001:0"],
            "source": "claude",
            "host": "openclaw",
            "window_text": "测试窗口",
            "score": 0.85,
            "status": "pending",
        })
        pending = self.store.get_pending_candidates(min_score=0.7)
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["candidate_id"], "cand_001")

    def test_artifact_upsert(self):
        self.store.upsert_artifact({
            "artifact_id": "art_001",
            "kind": "memory",
            "title": "SSH 端口是 2222",
            "confidence": 0.9,
        })
        stats = self.store.stats()
        self.assertEqual(stats["distill_artifacts"], 1)

    def test_bridge_upsert(self):
        self.store.upsert_bridge({
            "bridge_id": "bridge_001",
            "artifact_id": "art_001",
            "trace_id": "trace_abc",
        })
        stats = self.store.stats()
        self.assertEqual(stats["control_plane_bridge"], 1)

    def test_fts_search(self):
        events = [{
            "event_id": "claude:ses001:0",
            "source": "claude", "host": "openclaw", "project": "test",
            "session_id": "claude:ses001", "role": "user",
            "content": "SSH port changed from 22 to 2222",
            "timestamp": "2026-04-16T10:00:00Z",
        }]
        self.store.upsert_events(events)
        results = self.store.search("SSH")
        self.assertGreater(len(results), 0)
        self.assertIn("SSH", results[0]["content"])

    def test_fts_search_with_source_filter(self):
        events = [{
            "event_id": "claude:ses001:0",
            "source": "claude", "host": "openclaw", "project": "test",
            "session_id": "claude:ses001", "role": "user",
            "content": "测试搜索",
            "timestamp": "2026-04-16T10:00:00Z",
        }]
        self.store.upsert_events(events)
        results = self.store.search("测试", sources=["gemini"])
        self.assertEqual(len(results), 0)


# ── SourceAdapter 测试 ────────────────────────────────────────────────


class TestSourceAdapters(unittest.TestCase):
    """多源适配器测试。"""

    def test_claude_adapter_probe(self):
        adapter = sa.ClaudeSourceAdapter()
        paths = adapter.probe({})
        # 本机应该有 .claude/transcripts 目录
        self.assertIsInstance(paths, list)

    def test_claude_adapter_extract_real(self):
        adapter = sa.ClaudeSourceAdapter()
        paths = adapter.probe({})
        if not paths:
            self.skipTest("无 Claude transcript 文件")
        events = adapter.extract(paths[0], None)
        self.assertIsInstance(events, list)
        if events:
            self.assertTrue(events[0].event_id.startswith("claude:"))
            self.assertIn(events[0].role, ("user", "assistant", "tool", "system"))

    def test_claude_adapter_extract_with_cursor(self):
        adapter = sa.ClaudeSourceAdapter()
        paths = adapter.probe({})
        if not paths:
            self.skipTest("无 Claude transcript 文件")
        # 设置游标为行数，应该只提取新增部分
        hint = adapter.cursor_hint(paths[0])
        events_with_cursor = adapter.extract(paths[0], hint)
        self.assertEqual(len(events_with_cursor), 0)  # 已全部游标过

    def test_adapter_registry(self):
        adapter = sa.get_adapter("claude")
        self.assertIsInstance(adapter, sa.ClaudeSourceAdapter)
        with self.assertRaises(ValueError):
            sa.get_adapter("unknown_source")

    def test_docs_adapter_probe(self):
        adapter = sa.DocsSourceAdapter(workspace_root=str(ROOT))
        paths = adapter.probe({})
        self.assertGreater(len(paths), 0)

    def test_truncate_tool_output(self):
        long_text = "x" * 1000
        result = sa._truncate_tool_output(long_text, max_chars=100, tail_chars=50)
        self.assertLess(len(result), 1000)
        self.assertIn("truncated", result)

    def test_safe_read_jsonl_nonexistent(self):
        result = sa._safe_read_jsonl("/nonexistent/path.jsonl")
        self.assertEqual(result, [])


# ── Cleaner 测试 ──────────────────────────────────────────────────────


class TestDistillCleaner(unittest.TestCase):
    """蒸馏清洗器测试。"""

    def test_clean_tool_output_long(self):
        long_content = "x" * 1000
        result = dc.clean_tool_outputs(long_content, "tool")
        self.assertLess(len(result), 1000)

    def test_clean_heartbeat_removes_duplicates(self):
        content = "line1\nline1\nline1\nline2\nline2"
        result = dc.clean_heartbeat_and_templates(content)
        self.assertEqual(result.count("line1"), 1)
        self.assertEqual(result.count("line2"), 1)

    def test_segment_events(self):
        events = [
            {"event_id": f"e{i}", "session_id": "ses1", "role": "user",
             "content": f"内容{i}" * 50, "timestamp": f"2026-04-16T10:{i:02d}:00Z"}
            for i in range(20)
        ]
        windows = dc.segment_events_into_windows(events, source="test", host="openclaw")
        self.assertGreater(len(windows), 0)
        self.assertTrue(windows[0].window_id.startswith("win_test_"))

    def test_score_high_density(self):
        window = dc.CandidateWindow(
            window_id="w1", session_id="s1", source="test", host="openclaw",
            event_ids=[], text="```python\nprint('hello')\n```\n决定采用方案A",
            char_count=50, turn_count=2, time_span=["", ""],
        )
        score = dc.score_window(window)
        self.assertGreater(score, 0.3)

    def test_score_low_noise(self):
        window = dc.CandidateWindow(
            window_id="w1", session_id="s1", source="test", host="openclaw",
            event_ids=[], text="好的\n谢谢\n没问题",
            char_count=10, turn_count=3, time_span=["", ""],
        )
        score = dc.score_window(window)
        self.assertLess(score, 0.4)

    def test_score_and_route(self):
        windows = [
            dc.CandidateWindow(
                window_id=f"w{i}", session_id="s1", source="test", host="openclaw",
                event_ids=[], text="```python\nimport os\n```" * 5,
                char_count=200, turn_count=1, time_span=["", ""],
            )
            for i in range(3)
        ]
        routed = dc.score_and_route(windows)
        self.assertTrue(all(w.score >= 0 for w in routed))
        self.assertTrue(all(w.status in ("high_value", "index_only", "skip") for w in routed))

    def test_fallback_classify_memory(self):
        result = dc.fallback_classify("配置路径 /home/ubuntu/.hermes 端口:2222")
        self.assertEqual(result["kind"], "memory")

    def test_fallback_classify_experience(self):
        result = dc.fallback_classify("执行失败，error: connection refused")
        self.assertEqual(result["kind"], "experience")

    def test_fallback_classify_adr(self):
        result = dc.fallback_classify("决定采用方案A，因为性能更好")
        self.assertEqual(result["kind"], "adr")


# ── Classifier 测试 ───────────────────────────────────────────────────


class TestDistillClassifier(unittest.TestCase):
    """蒸馏分类器测试。"""

    def test_classify_with_rules(self):
        text = "目标：修复 SSH 端口冲突\n\n步骤：\n1. 修改 sshd_config\n2. 重启服务\n3. 验证连接\n\n文件：/etc/ssh/sshd_config"
        artifact = clf.classify_with_rules(text, "win_test_0", "claude")
        self.assertIn("kind", artifact)
        self.assertIn("title", artifact)
        self.assertIn("summary", artifact)
        self.assertGreater(len(artifact["summary"]), 50)

    def test_classify_extracts_files(self):
        text = "修改了 /etc/ssh/sshd_config 和 H:\\config\\app.py"
        artifact = clf.classify_with_rules(text)
        self.assertIn("summary", artifact)


# ── Reporter 测试 ─────────────────────────────────────────────────────


class TestDistillReporter(unittest.TestCase):
    """蒸馏报告器测试。"""

    def test_build_distill_report(self):
        artifacts = [
            {"artifact_id": "a1", "kind": "memory", "title": "测试", "confidence": 0.9,
             "requires_human_review": False, "target_kind": "hot_memory", "summary": "摘要"},
            {"artifact_id": "a2", "kind": "experience", "title": "排障", "confidence": 0.5,
             "requires_human_review": True, "target_kind": "knowledge", "summary": "排障摘要"},
        ]
        report = dr.build_distill_report(artifacts, stats={"normalized_events": 10})
        self.assertEqual(report["summary"]["total_artifacts"], 2)
        self.assertEqual(report["summary"]["hot_memory_writes"], 1)
        self.assertEqual(report["summary"]["needs_review"], 1)

    def test_build_bridge_report(self):
        artifacts = [{"artifact_id": "a1", "trace_id": "t1"}]
        bridges = dr.build_bridge_report(artifacts, workspace="/test", trace_id="t1")
        self.assertEqual(len(bridges), 1)
        self.assertTrue(bridges[0]["bridge_id"].startswith("bridge_"))

    def test_save_report(self):
        tmpdir = tempfile.mkdtemp()
        report = {"test": True, "timestamp": "2026-04-16T10:00:00Z"}
        path = dr.save_report(report, tmpdir, "distill")
        self.assertTrue(path.exists())
        loaded = json.loads(path.read_text(encoding="utf-8"))
        self.assertTrue(loaded["test"])


# ── Skill Draft Generator 测试 ────────────────────────────────────────


class TestSkillDraftGenerator(unittest.TestCase):
    """技能草稿生成器测试。"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def test_no_pattern_no_draft(self):
        artifacts = [{"kind": "memory", "title": "非 pattern", "confidence": 0.9}]
        drafts = sdg.generate_skill_draft(artifacts, self.tmpdir)
        self.assertEqual(len(drafts), 0)

    def test_generate_draft_from_pattern(self):
        artifacts = [{
            "kind": "pattern",
            "title": "SSH 端口冲突修复模式",
            "confidence": 0.8,
            "summary": "步骤:\n1. 检查端口\n2. 修改配置\n3. 重启服务",
            "rationale": "SSH 端口冲突频繁出现",
            "evidence_refs": ["claude:ses001:0"],
        }]
        drafts = sdg.generate_skill_draft(artifacts, self.tmpdir)
        self.assertEqual(len(drafts), 1)
        skill_dir = Path(drafts[0]["skill_dir"])
        self.assertTrue((skill_dir / "SKILL.md").exists())
        self.assertTrue((skill_dir / "origin.json").exists())
        # 验证 SKILL.md 内容
        content = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("SSH", content)
        self.assertIn("draft", content)

    def test_low_confidence_pattern_skipped(self):
        artifacts = [{
            "kind": "pattern",
            "title": "低置信度模式",
            "confidence": 0.3,
        }]
        drafts = sdg.generate_skill_draft(artifacts, self.tmpdir)
        self.assertEqual(len(drafts), 0)

    def test_title_to_skill_name(self):
        name = sdg._title_to_skill_name("SSH 端口冲突修复模式")
        self.assertTrue(name.replace("-", "").isalnum() or "-" in name)
        self.assertLessEqual(len(name), 64)

    def test_match_existing_skill_exact(self):
        """归一化名称互含 → 直接命中。"""
        existing = {"git-sync": Path("/fake/skills/library/git-sync/SKILL.md")}
        matched, score = sdg.match_existing_skill("git sync 自动同步模式", existing)
        self.assertEqual(matched, "git-sync")
        self.assertGreaterEqual(score, 0.9)

    def test_match_existing_skill_keyword(self):
        """关键词交集 → 模糊命中。"""
        existing = {"log-monitor": Path("/fake/skills/library/log-monitor/SKILL.md")}
        matched, score = sdg.match_existing_skill("log monitor 日志监控模式", existing, threshold=0.2)
        self.assertEqual(matched, "log-monitor")
        self.assertGreater(score, 0.2)

    def test_no_match_creates_new(self):
        """未匹配 → 新建。"""
        existing = {"git-sync": Path("/fake/skills/library/git-sync/SKILL.md")}
        matched, score = sdg.match_existing_skill("飞书机器人部署模式", existing)
        self.assertIsNone(matched)

    def test_generate_draft_updates_existing(self):
        """匹配到已有技能 → 追加更新而非新建。"""
        workspace = Path(self.tmpdir) / "ws"
        skill_dir = workspace / "skills" / "library" / "git-sync"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("# Git Sync\n已有内容", encoding="utf-8")

        artifacts = [{
            "kind": "pattern",
            "title": "git sync 自动同步模式",
            "confidence": 0.8,
            "summary": "- 定时拉取远程变更\n- 冲突自动合并",
            "rationale": "git sync 操作频繁出现",
            "evidence_refs": ["claude:ses001:0"],
            "source": "claude",
        }]
        drafts = sdg.generate_skill_draft(artifacts, self.tmpdir, workspace=workspace)
        self.assertEqual(len(drafts), 1)
        self.assertEqual(drafts[0]["action"], "update")
        self.assertEqual(drafts[0]["matched_existing"], "git-sync")
        # 验证 SKILL.md 被追加了蒸馏段落
        content = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("蒸馏补充", content)
        self.assertIn("已有内容", content)  # 原有内容保留

    def test_discover_existing_skills(self):
        """扫描已有技能。"""
        workspace = Path(self.tmpdir) / "ws"
        s1 = workspace / "skills" / "library" / "skill-a"
        s1.mkdir(parents=True)
        (s1 / "SKILL.md").write_text("# A", encoding="utf-8")
        s2 = workspace / "skills" / "library" / "skill-b"
        s2.mkdir(parents=True)
        (s2 / "SKILL.md").write_text("# B", encoding="utf-8")
        # 缺少 SKILL.md 的不算
        s3 = workspace / "skills" / "library" / "skill-c"
        s3.mkdir(parents=True)

        found = sdg.discover_existing_skills(workspace)
        self.assertIn("skill-a", found)
        self.assertIn("skill-b", found)
        self.assertNotIn("skill-c", found)

    def test_discover_from_user_home(self):
        """平台用户目录下的技能也能被发现（Windows: ~/.agents/skills/）。"""
        home = Path(self.tmpdir) / "home"
        skill_dir = home / ".agents" / "skills" / "sample-home-skill"
        skill_dir.mkdir(parents=True)
        skill_file = skill_dir / "SKILL.md"
        skill_file.write_text("# Sample Home Skill\n", encoding="utf-8")

        with mock.patch.object(sdg.Path, "home", return_value=home):
            found = sdg.discover_existing_skills()

        self.assertEqual(skill_file, found["sample-home-skill"])


if __name__ == "__main__":
    unittest.main()
