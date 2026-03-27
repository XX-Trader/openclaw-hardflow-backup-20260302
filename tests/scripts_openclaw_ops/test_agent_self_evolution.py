#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_agent_self_evolution.py — Agent 自进化引擎单元测试
"""

import importlib.util
import json
import os
import sqlite3
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).resolve().parent.parent.parent / "scripts" / "openclaw-ops" / "agent_self_evolution.py"
_spec = importlib.util.spec_from_file_location("agent_self_evolution", SCRIPT_PATH)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

collect_agent_metrics = _mod.collect_agent_metrics
compute_agent_scores = _mod.compute_agent_scores
run_evolution = _mod.run_evolution
build_cli_parser = _mod.build_cli_parser
SCORING_WEIGHTS = _mod.SCORING_WEIGHTS


def _create_test_db(db_path):
    """创建测试用的 task_center.db。"""
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS task_outputs (
            id INTEGER PRIMARY KEY,
            agent_id TEXT,
            status TEXT,
            quality_score REAL,
            token_count INTEGER,
            duration_ms INTEGER,
            failure_count INTEGER DEFAULT 0,
            created_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS task_incidents (
            id INTEGER PRIMARY KEY,
            agent_id TEXT,
            incident_type TEXT,
            created_at TEXT
        )
    """)
    return conn


class TestMetricsCollection:
    """指标采集测试。"""

    def test_collect_from_empty_db(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            tmp_path = tmp.name
        try:
            conn = _create_test_db(tmp_path)
            conn.close()
            metrics = collect_agent_metrics(tmp_path)
            assert metrics == {}
        finally:
            os.unlink(tmp_path)

    def test_collect_with_data(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            tmp_path = tmp.name
        try:
            conn = _create_test_db(tmp_path)
            now_iso = datetime.now().isoformat()
            conn.executemany(
                "INSERT INTO task_outputs (agent_id, status, quality_score, token_count, duration_ms, failure_count, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    ("ops-agent", "completed", 85, 20000, 5000, 0, now_iso),
                    ("ops-agent", "completed", 90, 15000, 4000, 0, now_iso),
                    ("ops-agent", "failed", None, 30000, 8000, 1, now_iso),
                    ("tester", "completed", 70, 40000, 10000, 0, now_iso),
                ],
            )
            conn.commit()
            conn.close()

            metrics = collect_agent_metrics(tmp_path, lookback_days=1)
            assert "ops-agent" in metrics
            assert "tester" in metrics
            assert metrics["ops-agent"]["total_tasks"] == 3
            assert metrics["ops-agent"]["completed"] == 2
            assert metrics["ops-agent"]["failed"] == 1
        finally:
            os.unlink(tmp_path)

    def test_collect_nonexistent_db(self):
        metrics = collect_agent_metrics("/nonexistent/db.sqlite")
        assert metrics == {}


class TestScoring:
    """评分计算测试。"""

    def test_perfect_agent(self):
        metrics = {
            "perfect-agent": {
                "total_tasks": 100,
                "completed": 100,
                "failed": 0,
                "success_rate": 100,
                "avg_quality": 95,
                "avg_tokens": 5000,
                "avg_duration_ms": 2000,
                "max_consecutive_failures": 0,
                "incident_count": 0,
            }
        }
        scores = compute_agent_scores(metrics)
        assert "perfect-agent" in scores
        assert scores["perfect-agent"]["composite_score"] >= 85
        assert scores["perfect-agent"]["grade"] == "excellent"

    def test_poor_agent(self):
        metrics = {
            "poor-agent": {
                "total_tasks": 50,
                "completed": 10,
                "failed": 40,
                "success_rate": 20,
                "avg_quality": 30,
                "avg_tokens": 150000,
                "avg_duration_ms": 60000,
                "max_consecutive_failures": 5,
                "incident_count": 10,
            }
        }
        scores = compute_agent_scores(metrics)
        assert "poor-agent" in scores
        assert scores["poor-agent"]["composite_score"] < 50
        assert scores["poor-agent"]["grade"] in ("needs_improvement", "critical")
        assert len(scores["poor-agent"]["recommendations"]) >= 2

    def test_recommendations_generated_for_low_success(self):
        metrics = {
            "low-success": {
                "total_tasks": 20,
                "completed": 8,
                "failed": 12,
                "success_rate": 40,
                "avg_quality": 70,
                "avg_tokens": 30000,
                "avg_duration_ms": 5000,
                "max_consecutive_failures": 3,
            }
        }
        scores = compute_agent_scores(metrics)
        recommendations = scores["low-success"]["recommendations"]
        has_success_rec = any(r["area"] == "成功率" for r in recommendations)
        assert has_success_rec

    def test_weights_sum_to_one(self):
        total_weight = sum(SCORING_WEIGHTS.values())
        assert abs(total_weight - 1.0) < 0.001

    def test_empty_metrics(self):
        scores = compute_agent_scores({})
        assert scores == {}


class TestFullEvolution:
    """完整进化流程测试。"""

    def test_evolution_no_data(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            tmp_path = tmp.name
        try:
            conn = _create_test_db(tmp_path)
            conn.close()
            result = run_evolution(db_path=tmp_path, dry_run=True)
            assert result["status"] == "no_data"
        finally:
            os.unlink(tmp_path)

    def test_evolution_with_data(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            tmp_path = tmp.name
        try:
            conn = _create_test_db(tmp_path)
            now_iso = datetime.now().isoformat()
            conn.executemany(
                "INSERT INTO task_outputs (agent_id, status, quality_score, token_count, duration_ms, failure_count, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    ("agent-a", "completed", 90, 10000, 3000, 0, now_iso),
                    ("agent-b", "failed", 20, 80000, 30000, 3, now_iso),
                ],
            )
            conn.commit()
            conn.close()

            result = run_evolution(db_path=tmp_path, dry_run=True, lookback_days=1)
            assert result["agents_evaluated"] == 2
        finally:
            os.unlink(tmp_path)

    def test_evolution_writes_report(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp_db:
            db_path = tmp_db.name
        with tempfile.TemporaryDirectory() as out_dir:
            try:
                conn = _create_test_db(db_path)
                now_iso = datetime.now().isoformat()
                conn.execute(
                    "INSERT INTO task_outputs (agent_id, status, quality_score, token_count, duration_ms, failure_count, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    ("test-agent", "completed", 80, 20000, 5000, 0, now_iso),
                )
                conn.commit()
                conn.close()

                run_evolution(db_path=db_path, output_dir=out_dir, dry_run=False, lookback_days=1)
                json_files = list(Path(out_dir).glob("evolution-*.json"))
                assert len(json_files) >= 1
            finally:
                os.unlink(db_path)


class TestCliParser:
    def test_help(self):
        parser = build_cli_parser()
        with pytest.raises(SystemExit) as exc_info:
            parser.parse_args(["--help"])
        assert exc_info.value.code == 0
