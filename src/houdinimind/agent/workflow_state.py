"""Persistent autonomous workflow state and execution traces."""

from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid
from contextlib import contextmanager
from typing import Any


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)


def _load_json(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except Exception:
        return fallback


class WorkflowStateStore:
    """Local SQLite store for resumable goal execution traces.

    The current AgentLoop still executes synchronously, but this store gives it
    a durable run graph: goal, plan, checkpoint, tool events, verification
    events, repair events, and final status. That is the minimum substrate for
    future long-running/resumable orchestration without making the UI thread
    depend on in-memory Python objects.
    """

    def __init__(self, db_path: str):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_db()

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS workflow_runs (
                    run_id          TEXT PRIMARY KEY,
                    user_goal       TEXT NOT NULL,
                    request_mode    TEXT NOT NULL,
                    status          TEXT NOT NULL,
                    plan_json       TEXT NOT NULL DEFAULT '{}',
                    checkpoint_path TEXT NOT NULL DEFAULT '',
                    summary         TEXT NOT NULL DEFAULT '',
                    created_ts      REAL NOT NULL,
                    updated_ts      REAL NOT NULL,
                    finished_ts     REAL
                );

                CREATE INDEX IF NOT EXISTS idx_workflow_status ON workflow_runs(status);
                CREATE INDEX IF NOT EXISTS idx_workflow_updated ON workflow_runs(updated_ts DESC);

                CREATE TABLE IF NOT EXISTS workflow_events (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id          TEXT NOT NULL,
                    ts              REAL NOT NULL,
                    event_type      TEXT NOT NULL,
                    payload_json    TEXT NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES workflow_runs(run_id)
                );

                CREATE INDEX IF NOT EXISTS idx_workflow_events_run ON workflow_events(run_id, ts);
                CREATE INDEX IF NOT EXISTS idx_workflow_events_type ON workflow_events(event_type);
                """
            )

    def start_run(
        self,
        *,
        user_goal: str,
        request_mode: str,
        plan: dict | None = None,
        checkpoint_path: str = "",
    ) -> str:
        run_id = uuid.uuid4().hex[:16]
        now = time.time()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO workflow_runs
                    (run_id, user_goal, request_mode, status, plan_json, checkpoint_path,
                     created_ts, updated_ts)
                VALUES (?, ?, ?, 'running', ?, ?, ?, ?)
                """,
                (
                    run_id,
                    user_goal,
                    request_mode,
                    _json(plan or {}),
                    checkpoint_path or "",
                    now,
                    now,
                ),
            )
            conn.execute(
                """
                INSERT INTO workflow_events (run_id, ts, event_type, payload_json)
                VALUES (?, ?, 'run_started', ?)
                """,
                (
                    run_id,
                    now,
                    _json({"request_mode": request_mode, "checkpoint_path": checkpoint_path}),
                ),
            )
        return run_id

    def update_plan(self, run_id: str, plan: dict | None) -> None:
        if not run_id:
            return
        now = time.time()
        with self._conn() as conn:
            conn.execute(
                "UPDATE workflow_runs SET plan_json=?, updated_ts=? WHERE run_id=?",
                (_json(plan or {}), now, run_id),
            )
            conn.execute(
                """
                INSERT INTO workflow_events (run_id, ts, event_type, payload_json)
                VALUES (?, ?, 'plan_updated', ?)
                """,
                (run_id, now, _json({"plan": plan or {}})),
            )

    def update_checkpoint(self, run_id: str, checkpoint_path: str) -> None:
        if not run_id or not checkpoint_path:
            return
        now = time.time()
        with self._conn() as conn:
            conn.execute(
                "UPDATE workflow_runs SET checkpoint_path=?, updated_ts=? WHERE run_id=?",
                (checkpoint_path, now, run_id),
            )
            conn.execute(
                """
                INSERT INTO workflow_events (run_id, ts, event_type, payload_json)
                VALUES (?, ?, 'checkpoint', ?)
                """,
                (run_id, now, _json({"checkpoint_path": checkpoint_path})),
            )

    def append_event(self, run_id: str, event_type: str, payload: dict[str, Any]) -> None:
        if not run_id:
            return
        now = time.time()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO workflow_events (run_id, ts, event_type, payload_json)
                VALUES (?, ?, ?, ?)
                """,
                (run_id, now, event_type, _json(payload)),
            )
            conn.execute(
                "UPDATE workflow_runs SET updated_ts=? WHERE run_id=?",
                (now, run_id),
            )

    def finish_run(self, run_id: str, *, status: str, summary: str = "") -> None:
        if not run_id:
            return
        status = status if status in {"completed", "failed", "cancelled", "partial"} else "partial"
        now = time.time()
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE workflow_runs
                SET status=?, summary=?, updated_ts=?, finished_ts=?
                WHERE run_id=?
                """,
                (status, summary[:2000], now, now, run_id),
            )
            conn.execute(
                """
                INSERT INTO workflow_events (run_id, ts, event_type, payload_json)
                VALUES (?, ?, 'run_finished', ?)
                """,
                (run_id, now, _json({"status": status, "summary": summary[:2000]})),
            )

    def load_run(self, run_id: str) -> dict[str, Any] | None:
        if not run_id:
            return None
        with self._conn() as conn:
            run = conn.execute(
                "SELECT * FROM workflow_runs WHERE run_id=?",
                (run_id,),
            ).fetchone()
            if not run:
                return None
            events = conn.execute(
                """
                SELECT ts, event_type, payload_json
                FROM workflow_events
                WHERE run_id=?
                ORDER BY ts ASC, id ASC
                """,
                (run_id,),
            ).fetchall()
        return {
            "run_id": run["run_id"],
            "user_goal": run["user_goal"],
            "request_mode": run["request_mode"],
            "status": run["status"],
            "plan": _load_json(run["plan_json"], {}),
            "checkpoint_path": run["checkpoint_path"],
            "summary": run["summary"],
            "created_ts": run["created_ts"],
            "updated_ts": run["updated_ts"],
            "finished_ts": run["finished_ts"],
            "events": [
                {
                    "ts": event["ts"],
                    "event_type": event["event_type"],
                    "payload": _load_json(event["payload_json"], {}),
                }
                for event in events
            ],
        }

    def latest_runs(self, limit: int = 10) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT run_id, user_goal, request_mode, status, checkpoint_path,
                       summary, created_ts, updated_ts, finished_ts
                FROM workflow_runs
                ORDER BY updated_ts DESC
                LIMIT ?
                """,
                (max(1, int(limit)),),
            ).fetchall()
        return [
            {
                "run_id": row["run_id"],
                "user_goal": row["user_goal"],
                "request_mode": row["request_mode"],
                "status": row["status"],
                "checkpoint_path": row["checkpoint_path"],
                "summary": row["summary"],
                "created_ts": row["created_ts"],
                "updated_ts": row["updated_ts"],
                "finished_ts": row["finished_ts"],
            }
            for row in rows
        ]
