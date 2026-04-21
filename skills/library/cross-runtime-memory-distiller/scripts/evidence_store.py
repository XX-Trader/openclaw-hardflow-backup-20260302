#!/usr/bin/env python3
"""证据存储层：SQLite 初始化、归一化事件落盘、增量游标管理、FTS 检索。

evidence_store 是蒸馏流水线的持久化核心，所有归一化事件、候选窗口、
控制面桥接记录都存储在这里。它提供：
- 数据库 schema 初始化与迁移
- 归一化事件幂等写入
- 增量游标读写
- FTS 全文检索
- 候选窗口管理
- 桥接记录管理
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

logger = logging.getLogger("evidence_store")

# ── Schema DDL ────────────────────────────────────────────────────────

SCHEMA_SQL = """
PRAGMA encoding = "UTF-8";
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- 归一化事件表
CREATE TABLE IF NOT EXISTS normalized_events (
    event_id      TEXT PRIMARY KEY,
    source        TEXT NOT NULL,
    host          TEXT NOT NULL,
    project       TEXT NOT NULL,
    session_id    TEXT NOT NULL,
    role          TEXT NOT NULL,
    content       TEXT NOT NULL,
    timestamp     TEXT NOT NULL,
    metadata_json TEXT DEFAULT '{}',
    created_at    TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_events_source ON normalized_events(source, timestamp);
CREATE INDEX IF NOT EXISTS idx_events_session ON normalized_events(session_id);

-- 增量游标表
CREATE TABLE IF NOT EXISTS ingest_cursors (
    source       TEXT NOT NULL,
    host         TEXT NOT NULL,
    project      TEXT NOT NULL,
    cursor_type  TEXT NOT NULL DEFAULT 'mtime+offset',
    cursor_value TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    PRIMARY KEY (source, host, project)
);

-- 候选窗口表
CREATE TABLE IF NOT EXISTS candidate_windows (
    candidate_id  TEXT PRIMARY KEY,
    event_ids     TEXT NOT NULL,
    source        TEXT NOT NULL,
    host          TEXT NOT NULL,
    window_text   TEXT NOT NULL,
    score         REAL NOT NULL DEFAULT 0,
    status        TEXT NOT NULL DEFAULT 'pending',
    artifact_id   TEXT,
    created_at    TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_candidates_status ON candidate_windows(status, score);

-- 蒸馏产物表
CREATE TABLE IF NOT EXISTS distill_artifacts (
    artifact_id       TEXT PRIMARY KEY,
    kind              TEXT NOT NULL,
    title             TEXT NOT NULL,
    summary           TEXT NOT NULL DEFAULT '',
    rationale         TEXT NOT NULL DEFAULT '',
    evidence_refs     TEXT NOT NULL DEFAULT '[]',
    confidence        REAL NOT NULL DEFAULT 0,
    target_kind       TEXT NOT NULL DEFAULT 'knowledge',
    trace_id          TEXT,
    task_id           TEXT,
    run_id            TEXT,
    agent_id          TEXT,
    workspace         TEXT,
    requires_human_review INTEGER NOT NULL DEFAULT 0,
    created_at        TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_artifacts_kind ON distill_artifacts(kind, confidence);

-- 控制面桥接表
CREATE TABLE IF NOT EXISTS control_plane_bridge (
    bridge_id           TEXT PRIMARY KEY,
    artifact_id         TEXT NOT NULL,
    trace_id            TEXT,
    task_id             TEXT,
    run_id              TEXT,
    benchmark_run_id    TEXT,
    workspace           TEXT,
    root_cause_hints    TEXT DEFAULT '[]',
    source_report_paths TEXT DEFAULT '[]',
    created_at          TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_bridge_trace ON control_plane_bridge(trace_id);
CREATE INDEX IF NOT EXISTS idx_bridge_task ON control_plane_bridge(task_id, run_id);

-- 去重指纹表
CREATE TABLE IF NOT EXISTS dedup_fingerprints (
    fingerprint   TEXT PRIMARY KEY,
    artifact_id   TEXT NOT NULL,
    created_at    TEXT DEFAULT (datetime('now'))
);

-- ID 计数器表
CREATE TABLE IF NOT EXISTS id_counters (
    counter_type TEXT NOT NULL,
    date_key     TEXT NOT NULL,
    seq          INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (counter_type, date_key)
);

-- FTS 全文检索
CREATE VIRTUAL TABLE IF NOT EXISTS events_fts USING fts5(
    content,
    source,
    session_id,
    project,
    content='normalized_events',
    content_rowid='rowid'
);

CREATE TRIGGER IF NOT EXISTS events_fts_insert AFTER INSERT ON normalized_events BEGIN
    INSERT INTO events_fts(rowid, content, source, session_id, project)
    VALUES (new.rowid, new.content, new.source, new.session_id, new.project);
END;
"""


class EvidenceStore:
    """SQLite 证据存储层的统一入口。"""

    def __init__(self, db_path: str | Path) -> None:
        """初始化存储层。

        Args:
            db_path: distill.db 文件路径
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None
        self._initialize_db()

    def _connect(self) -> sqlite3.Connection:
        """获取或创建数据库连接。"""
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.execute("PRAGMA encoding = 'UTF-8'")
            self._conn.execute("PRAGMA journal_mode = WAL")
            self._conn.execute("PRAGMA foreign_keys = ON")
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def _initialize_db(self) -> None:
        """初始化数据库 schema。"""
        conn = self._connect()
        conn.executescript(SCHEMA_SQL)
        conn.commit()
        logger.debug("db_initialized:path=%s", self.db_path)

    def close(self) -> None:
        """关闭数据库连接。"""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    # ── ID 生成 ───────────────────────────────────────────────────────

    def next_id(self, counter_type: str) -> str:
        """生成带日期的递增 ID。

        Args:
            counter_type: counter 类型（cand / artifact / bridge / bundle）

        Returns:
            格式: {type}_{YYYYMMDD}_{seq:04d}
        """
        today = datetime.now().strftime("%Y%m%d")
        conn = self._connect()
        with conn:
            row = conn.execute(
                "SELECT seq FROM id_counters WHERE counter_type = ? AND date_key = ?",
                (counter_type, today),
            ).fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO id_counters (counter_type, date_key, seq) VALUES (?, ?, 1)",
                    (counter_type, today),
                )
                seq = 1
            else:
                seq = row["seq"] + 1
                conn.execute(
                    "UPDATE id_counters SET seq = ? WHERE counter_type = ? AND date_key = ?",
                    (seq, counter_type, today),
                )
        return f"{counter_type}_{today}_{seq:04d}"

    # ── 归一化事件 ────────────────────────────────────────────────────

    def upsert_events(self, events: Sequence[dict[str, Any]]) -> int:
        """批量写入归一化事件（幂等 upsert）。

        Args:
            events: NormalizedEvent 字典列表

        Returns:
            实际插入或更新的行数
        """
        conn = self._connect()
        count = 0
        for ev in events:
            try:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO normalized_events
                        (event_id, source, host, project, session_id, role, content, timestamp, metadata_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        ev["event_id"],
                        ev["source"],
                        ev["host"],
                        ev["project"],
                        ev["session_id"],
                        ev["role"],
                        ev["content"],
                        ev["timestamp"],
                        json.dumps(ev.get("metadata", {}), ensure_ascii=False),
                    ),
                )
                count += 1
            except (KeyError, sqlite3.IntegrityError) as exc:
                logger.warning("event_upsert_skip:id=%s err=%s", ev.get("event_id", "?"), exc)
        conn.commit()
        return count

    def query_events(
        self,
        source: str | None = None,
        session_id: str | None = None,
        since: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """查询归一化事件。"""
        conn = self._connect()
        clauses: list[str] = []
        params: list[Any] = []
        if source:
            clauses.append("source = ?")
            params.append(source)
        if session_id:
            clauses.append("session_id = ?")
            params.append(session_id)
        if since:
            clauses.append("timestamp >= ?")
            params.append(since)
        where = " AND ".join(clauses) if clauses else "1=1"
        rows = conn.execute(
            f"SELECT * FROM normalized_events WHERE {where} ORDER BY timestamp DESC LIMIT ?",
            (*params, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    # ── 增量游标 ──────────────────────────────────────────────────────

    def get_cursor(self, source: str, host: str, project: str) -> dict[str, Any] | None:
        """读取增量游标。

        Returns:
            游标值字典，不存在时返回 None
        """
        conn = self._connect()
        row = conn.execute(
            "SELECT cursor_type, cursor_value FROM ingest_cursors WHERE source=? AND host=? AND project=?",
            (source, host, project),
        ).fetchone()
        if row is None:
            return None
        return {"cursor_type": row["cursor_type"], "cursor_value": json.loads(row["cursor_value"])}

    def set_cursor(self, source: str, host: str, project: str, cursor_value: dict[str, Any]) -> None:
        """写入增量游标。"""
        conn = self._connect()
        conn.execute(
            """
            INSERT OR REPLACE INTO ingest_cursors (source, host, project, cursor_type, cursor_value, updated_at)
            VALUES (?, ?, ?, 'mtime+offset', ?, ?)
            """,
            (source, host, project, json.dumps(cursor_value, ensure_ascii=False), datetime.now().isoformat()),
        )
        conn.commit()

    # ── 候选窗口 ──────────────────────────────────────────────────────

    def upsert_candidate(self, candidate: dict[str, Any]) -> None:
        """写入候选窗口。"""
        conn = self._connect()
        conn.execute(
            """
            INSERT OR REPLACE INTO candidate_windows
                (candidate_id, event_ids, source, host, window_text, score, status, artifact_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                candidate["candidate_id"],
                json.dumps(candidate.get("event_ids", []), ensure_ascii=False),
                candidate["source"],
                candidate["host"],
                candidate["window_text"],
                candidate.get("score", 0),
                candidate.get("status", "pending"),
                candidate.get("artifact_id"),
            ),
        )
        conn.commit()

    def get_pending_candidates(self, min_score: float = 0.7, limit: int = 50) -> list[dict[str, Any]]:
        """获取待处理的高分候选窗口。"""
        conn = self._connect()
        rows = conn.execute(
            "SELECT * FROM candidate_windows WHERE status = 'pending' AND score >= ? ORDER BY score DESC LIMIT ?",
            (min_score, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    # ── 蒸馏产物 ──────────────────────────────────────────────────────

    def upsert_artifact(self, artifact: dict[str, Any]) -> None:
        """写入蒸馏产物。"""
        conn = self._connect()
        conn.execute(
            """
            INSERT OR REPLACE INTO distill_artifacts
                (artifact_id, kind, title, summary, rationale, evidence_refs,
                 confidence, target_kind, trace_id, task_id, run_id,
                 agent_id, workspace, requires_human_review)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                artifact["artifact_id"],
                artifact["kind"],
                artifact["title"],
                artifact.get("summary", ""),
                artifact.get("rationale", ""),
                json.dumps(artifact.get("evidence_refs", []), ensure_ascii=False),
                artifact.get("confidence", 0),
                artifact.get("target_kind", "knowledge"),
                artifact.get("trace_id"),
                artifact.get("task_id"),
                artifact.get("run_id"),
                artifact.get("agent_id"),
                artifact.get("workspace"),
                1 if artifact.get("requires_human_review") else 0,
            ),
        )
        conn.commit()

    # ── 桥接记录 ──────────────────────────────────────────────────────

    def upsert_bridge(self, bridge: dict[str, Any]) -> None:
        """写入控制面桥接记录。"""
        conn = self._connect()
        conn.execute(
            """
            INSERT OR REPLACE INTO control_plane_bridge
                (bridge_id, artifact_id, trace_id, task_id, run_id,
                 benchmark_run_id, workspace, root_cause_hints, source_report_paths)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                bridge["bridge_id"],
                bridge["artifact_id"],
                bridge.get("trace_id"),
                bridge.get("task_id"),
                bridge.get("run_id"),
                bridge.get("benchmark_run_id"),
                bridge.get("workspace"),
                json.dumps(bridge.get("root_cause_hints", []), ensure_ascii=False),
                json.dumps(bridge.get("source_report_paths", []), ensure_ascii=False),
            ),
        )
        conn.commit()

    # ── FTS 检索 ──────────────────────────────────────────────────────

    def search(
        self,
        query: str,
        sources: list[str] | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """全文检索归一化事件。

        Args:
            query: 搜索关键词
            sources: 限定数据源列表
            limit: 最大结果数

        Returns:
            命中事件列表，每个包含 rank 与正文
        """
        conn = self._connect()
        fts_query = query.replace('"', '""')
        sql = """
            SELECT e.event_id, e.source, e.session_id, e.content, e.timestamp,
                   e.metadata_json, rank
            FROM events_fts f
            JOIN normalized_events e ON e.rowid = f.rowid
            WHERE events_fts MATCH ?
        """
        params: list[Any] = [f'"{fts_query}"']
        if sources:
            placeholders = ",".join("?" for _ in sources)
            sql += f" AND e.source IN ({placeholders})"
            params.extend(sources)
        sql += " ORDER BY rank LIMIT ?"
        params.append(limit)

        try:
            rows = conn.execute(sql, params).fetchall()
        except sqlite3.OperationalError as exc:
            logger.warning("fts_search_failed:query=%s err=%s", query, exc)
            return []

        results: list[dict[str, Any]] = []
        for r in rows:
            results.append({
                "event_id": r[0],
                "source": r[1],
                "session_id": r[2],
                "content": r[3][:300],  # 截取摘要
                "timestamp": r[4],
                "metadata": json.loads(r[5]),
                "rank": r[6],
            })
        return results

    # ── 统计 ──────────────────────────────────────────────────────────

    def stats(self) -> dict[str, int]:
        """返回各表的行数统计。"""
        conn = self._connect()
        tables = ["normalized_events", "ingest_cursors", "candidate_windows",
                  "distill_artifacts", "control_plane_bridge", "dedup_fingerprints"]
        result: dict[str, int] = {}
        for t in tables:
            try:
                row = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()
                result[t] = row[0]
            except sqlite3.OperationalError:
                result[t] = 0
        return result
