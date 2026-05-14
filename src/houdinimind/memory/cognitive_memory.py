"""Durable cognitive memory for autonomous Houdini agent execution.

This store complements the existing session log and recipe book:

- session_log is the raw audit trail
- recipe_book is promoted procedural knowledge
- cognitive_memory is retrieval-time working knowledge for planning, retries,
  reflection, tool routing, and failure avoidance

The implementation is intentionally local-first and dependency-light so it can
run inside Houdini's Python without a separate database service.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sqlite3
import time
from collections.abc import Callable, Iterable
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

EmbeddingFn = Callable[[str], list[float] | tuple[float, ...] | None]


_WORD_RE = re.compile(r"[a-z0-9_/#.:-]{2,}", re.IGNORECASE)
_STOPWORDS = {
    "about",
    "after",
    "again",
    "also",
    "and",
    "are",
    "because",
    "before",
    "but",
    "can",
    "could",
    "for",
    "from",
    "had",
    "has",
    "have",
    "how",
    "into",
    "not",
    "now",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "was",
    "were",
    "what",
    "when",
    "where",
    "with",
    "would",
    "you",
}


@dataclass(frozen=True)
class MemoryHit:
    id: str
    kind: str
    summary: str
    content: str
    tags: list[str]
    metadata: dict[str, Any]
    score: float
    importance: float
    confidence: float
    created_ts: float
    last_access_ts: float

    def prompt_line(self, max_chars: int = 360) -> str:
        summary = _truncate(self.summary or self.content, max_chars)
        tag_text = ""
        if self.tags:
            tag_text = " [" + ", ".join(self.tags[:4]) + "]"
        return f"- {self.kind} score={self.score:.2f}{tag_text}: {summary}"


def _truncate(value: Any, limit: int) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def _terms(text: str) -> set[str]:
    return {
        m.group(0).lower()
        for m in _WORD_RE.finditer(text or "")
        if m.group(0).lower() not in _STOPWORDS
    }


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)


def _safe_json_loads(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except Exception:
        return fallback


def _stable_id(kind: str, content: str, tags: Iterable[str]) -> str:
    digest = hashlib.sha256()
    digest.update(kind.encode("utf-8", errors="ignore"))
    digest.update(b"\0")
    digest.update(re.sub(r"\s+", " ", content).strip().lower().encode("utf-8", errors="ignore"))
    digest.update(b"\0")
    digest.update(",".join(sorted(set(tags))).encode("utf-8", errors="ignore"))
    return digest.hexdigest()[:32]


def _vector(value: Any) -> list[float]:
    if value is None:
        return []
    if isinstance(value, str):
        loaded = _safe_json_loads(value, [])
        return _vector(loaded)
    if isinstance(value, (list, tuple)):
        out: list[float] = []
        for item in value:
            try:
                out.append(float(item))
            except (TypeError, ValueError):
                return []
        return out
    return []


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    count = min(len(a), len(b))
    if count == 0:
        return 0.0
    dot = sum(a[i] * b[i] for i in range(count))
    mag_a = math.sqrt(sum(a[i] * a[i] for i in range(count)))
    mag_b = math.sqrt(sum(b[i] * b[i] for i in range(count)))
    if mag_a == 0.0 or mag_b == 0.0:
        return 0.0
    return max(0.0, min(1.0, dot / (mag_a * mag_b)))


def _lexical_score(query_terms: set[str], text: str, tags: list[str]) -> float:
    if not query_terms:
        return 0.0
    doc_terms = _terms(text + " " + " ".join(tags))
    if not doc_terms:
        return 0.0
    overlap = query_terms & doc_terms
    if not overlap:
        return 0.0
    exact = len(overlap) / math.sqrt(max(1, len(query_terms)) * max(1, len(doc_terms)))
    tag_boost = 0.08 if any(term in " ".join(tags).lower() for term in overlap) else 0.0
    return min(1.0, exact + tag_boost)


class CognitiveMemoryStore:
    """SQLite-backed memory with lexical, vector, recency, and confidence ranking."""

    VALID_KINDS = {
        "working",
        "episodic",
        "semantic",
        "procedural",
        "tool_usage",
        "failure",
        "reflection",
        "project_rule",
    }

    def __init__(self, db_path: str, max_candidates: int = 800):
        self.db_path = db_path
        self.max_candidates = max(50, int(max_candidates))
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
                CREATE TABLE IF NOT EXISTS memories (
                    id              TEXT PRIMARY KEY,
                    kind            TEXT NOT NULL,
                    content         TEXT NOT NULL,
                    summary         TEXT NOT NULL,
                    tags            TEXT NOT NULL,
                    metadata        TEXT NOT NULL,
                    importance      REAL NOT NULL DEFAULT 0.5,
                    confidence      REAL NOT NULL DEFAULT 0.7,
                    reinforcement   REAL NOT NULL DEFAULT 0.0,
                    created_ts      REAL NOT NULL,
                    updated_ts      REAL NOT NULL,
                    last_access_ts  REAL NOT NULL,
                    access_count    INTEGER NOT NULL DEFAULT 0,
                    ttl_s           REAL,
                    expires_ts      REAL,
                    embedding       TEXT,
                    source          TEXT NOT NULL DEFAULT ''
                );

                CREATE INDEX IF NOT EXISTS idx_memories_kind ON memories(kind);
                CREATE INDEX IF NOT EXISTS idx_memories_updated ON memories(updated_ts DESC);
                CREATE INDEX IF NOT EXISTS idx_memories_expires ON memories(expires_ts);

                CREATE TABLE IF NOT EXISTS tool_events (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts              REAL NOT NULL,
                    request         TEXT NOT NULL,
                    tool_name       TEXT NOT NULL,
                    args            TEXT NOT NULL,
                    status          TEXT NOT NULL,
                    message         TEXT NOT NULL,
                    result          TEXT NOT NULL,
                    duration_ms     INTEGER,
                    memory_id       TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_tool_events_tool ON tool_events(tool_name);
                CREATE INDEX IF NOT EXISTS idx_tool_events_status ON tool_events(status);
                CREATE INDEX IF NOT EXISTS idx_tool_events_ts ON tool_events(ts DESC);

                CREATE TABLE IF NOT EXISTS reflections (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts              REAL NOT NULL,
                    request         TEXT NOT NULL,
                    outcome         TEXT NOT NULL,
                    score           REAL NOT NULL,
                    lessons         TEXT NOT NULL,
                    metadata        TEXT NOT NULL,
                    memory_id       TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_reflections_ts ON reflections(ts DESC);
                """
            )

    def store_memory(
        self,
        *,
        kind: str,
        content: str,
        summary: str = "",
        tags: Iterable[str] | None = None,
        metadata: dict[str, Any] | None = None,
        importance: float = 0.5,
        confidence: float = 0.7,
        ttl_s: float | None = None,
        source: str = "",
        embed_fn: EmbeddingFn | None = None,
    ) -> str:
        kind = kind if kind in self.VALID_KINDS else "semantic"
        content = str(content or "").strip()
        if not content:
            return ""
        tag_list = sorted({str(tag).strip().lower() for tag in (tags or []) if str(tag).strip()})
        summary = _truncate(summary or content, 500)
        metadata = dict(metadata or {})
        importance = max(0.0, min(1.0, float(importance)))
        confidence = max(0.0, min(1.0, float(confidence)))
        now = time.time()
        expires_ts = now + ttl_s if ttl_s else None
        memory_id = _stable_id(kind, content, tag_list)
        embedding = None
        if embed_fn:
            try:
                vec = _vector(embed_fn(summary + "\n" + content[:2000]))
                if vec:
                    embedding = _json_dumps(vec)
            except Exception:
                embedding = None

        with self._conn() as conn:
            existing = conn.execute(
                "SELECT importance, confidence, reinforcement, access_count FROM memories WHERE id=?",
                (memory_id,),
            ).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE memories
                    SET summary=?,
                        metadata=?,
                        importance=?,
                        confidence=?,
                        reinforcement=?,
                        updated_ts=?,
                        last_access_ts=?,
                        access_count=?,
                        ttl_s=COALESCE(?, ttl_s),
                        expires_ts=COALESCE(?, expires_ts),
                        embedding=COALESCE(?, embedding),
                        source=COALESCE(NULLIF(?, ''), source)
                    WHERE id=?
                    """,
                    (
                        summary,
                        _json_dumps(metadata),
                        max(float(existing["importance"]), importance),
                        max(float(existing["confidence"]), confidence),
                        min(1.0, float(existing["reinforcement"]) + 0.08),
                        now,
                        now,
                        int(existing["access_count"]) + 1,
                        ttl_s,
                        expires_ts,
                        embedding,
                        source,
                        memory_id,
                    ),
                )
                return memory_id
            conn.execute(
                """
                INSERT INTO memories (
                    id, kind, content, summary, tags, metadata, importance,
                    confidence, reinforcement, created_ts, updated_ts,
                    last_access_ts, access_count, ttl_s, expires_ts, embedding, source
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0.0, ?, ?, ?, 0, ?, ?, ?, ?)
                """,
                (
                    memory_id,
                    kind,
                    content,
                    summary,
                    _json_dumps(tag_list),
                    _json_dumps(metadata),
                    importance,
                    confidence,
                    now,
                    now,
                    now,
                    ttl_s,
                    expires_ts,
                    embedding,
                    source,
                ),
            )
        return memory_id

    def record_tool_event(
        self,
        *,
        tool_name: str,
        args: dict[str, Any],
        result: dict[str, Any],
        request: str = "",
        embed_fn: EmbeddingFn | None = None,
    ) -> str:
        status = str((result or {}).get("status") or "unknown").lower()
        message = str((result or {}).get("message") or "")[:1000]
        duration_ms = None
        meta = (result or {}).get("_meta") or {}
        if isinstance(meta, dict) and meta.get("duration_ms") is not None:
            try:
                duration_ms = int(meta.get("duration_ms"))
            except (TypeError, ValueError):
                duration_ms = None
        kind = "failure" if status == "error" else "tool_usage"
        tags = [f"tool:{tool_name}", f"status:{status}"]
        if meta.get("cached"):
            tags.append("cached")
        if meta.get("soft_skip"):
            tags.append("soft_skip")
        correction_hint = str((result or {}).get("_correction_hint") or "")[:1000]
        content = "\n".join(
            part
            for part in (
                f"Request: {request}" if request else "",
                f"Tool: {tool_name}",
                f"Args: {_json_dumps(args)[:1200]}",
                f"Status: {status}",
                f"Message: {message}",
                f"Correction hint: {correction_hint}" if correction_hint else "",
            )
            if part
        )
        importance = 0.88 if status == "error" else 0.46
        if status in {"ok", "success"} and tool_name in {
            "create_node_chain",
            "finalize_sop_network",
            "write_vex_code",
        }:
            importance = 0.62
        summary = f"{tool_name} {status}: {_truncate(message, 180)}"
        memory_id = self.store_memory(
            kind=kind,
            content=content,
            summary=summary,
            tags=tags,
            metadata={
                "tool_name": tool_name,
                "status": status,
                "duration_ms": duration_ms,
                "correction_hint": correction_hint,
            },
            importance=importance,
            confidence=0.9,
            ttl_s=None if status == "error" else 90 * 86400,
            source="tool_event",
            embed_fn=embed_fn,
        )
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO tool_events
                    (ts, request, tool_name, args, status, message, result, duration_ms, memory_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    time.time(),
                    request or "",
                    tool_name,
                    _json_dumps(args),
                    status,
                    message,
                    _json_dumps(result),
                    duration_ms,
                    memory_id,
                ),
            )
        return memory_id

    def record_reflection(
        self,
        *,
        request: str,
        outcome: str,
        score: float,
        lessons: list[str],
        metadata: dict[str, Any] | None = None,
        embed_fn: EmbeddingFn | None = None,
    ) -> str:
        score = max(0.0, min(1.0, float(score)))
        metadata = dict(metadata or {})
        lesson_lines = [_truncate(lesson, 320) for lesson in lessons if str(lesson).strip()]
        content = "\n".join(
            [
                f"Request: {request}",
                f"Outcome: {outcome}",
                f"Score: {score:.2f}",
                "Lessons:",
                *[f"- {line}" for line in lesson_lines],
                f"Metadata: {_json_dumps(metadata)[:1600]}",
            ]
        )
        kind = "reflection" if lesson_lines else "episodic"
        status_tag = "success" if score >= 0.75 else "needs_repair" if score < 0.55 else "partial"
        memory_id = self.store_memory(
            kind=kind,
            content=content,
            summary=f"{outcome} ({score:.2f}): {_truncate(request, 180)}",
            tags=["turn_reflection", status_tag, *metadata.get("tags", [])],
            metadata=metadata,
            importance=0.85 if score < 0.75 else 0.65,
            confidence=0.84,
            source="reflection",
            embed_fn=embed_fn,
        )
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO reflections (ts, request, outcome, score, lessons, metadata, memory_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    time.time(),
                    request,
                    outcome,
                    score,
                    _json_dumps(lesson_lines),
                    _json_dumps(metadata),
                    memory_id,
                ),
            )
        return memory_id

    def retrieve(
        self,
        query: str,
        *,
        kinds: Iterable[str] | None = None,
        limit: int = 8,
        embed_fn: EmbeddingFn | None = None,
        now: float | None = None,
        min_score: float = 0.05,
    ) -> list[MemoryHit]:
        now = now if now is not None else time.time()
        kind_list = [kind for kind in (kinds or []) if kind in self.VALID_KINDS]
        params: list[Any] = [now]
        where = "(expires_ts IS NULL OR expires_ts > ?)"
        if kind_list:
            placeholders = ",".join("?" for _ in kind_list)
            where += f" AND kind IN ({placeholders})"
            params.extend(kind_list)
        params.append(self.max_candidates)
        sql = f"""
            SELECT *
            FROM memories
            WHERE {where}
            ORDER BY updated_ts DESC
            LIMIT ?
        """
        with self._conn() as conn:
            rows = conn.execute(sql, params).fetchall()

        query_terms = _terms(query)
        query_vec: list[float] = []
        if embed_fn:
            try:
                query_vec = _vector(embed_fn(query))
            except Exception:
                query_vec = []

        hits: list[MemoryHit] = []
        for row in rows:
            tags = _safe_json_loads(row["tags"], [])
            metadata = _safe_json_loads(row["metadata"], {})
            searchable_text = f"{row['summary']}\n{row['content']}"
            lexical = _lexical_score(query_terms, searchable_text, tags)
            semantic = _cosine(query_vec, _vector(row["embedding"])) if query_vec else 0.0
            age_days = max(0.0, (now - float(row["updated_ts"])) / 86400.0)
            recency = 1.0 / (1.0 + (age_days / 21.0))
            importance = float(row["importance"])
            confidence = float(row["confidence"])
            reinforcement = float(row["reinforcement"])
            decay_penalty = max(0.0, (age_days - 45.0) / 365.0) * (1.0 - importance)
            if not query_terms and not query_vec:
                score = (
                    (0.38 * importance)
                    + (0.28 * confidence)
                    + (0.24 * recency)
                    + (0.10 * reinforcement)
                )
            else:
                score = (
                    (0.42 * lexical)
                    + (0.22 * semantic)
                    + (0.14 * importance)
                    + (0.08 * confidence)
                    + (0.08 * recency)
                    + (0.06 * min(1.0, reinforcement))
                    - (0.10 * decay_penalty)
                )
            if score < min_score:
                continue
            hits.append(
                MemoryHit(
                    id=row["id"],
                    kind=row["kind"],
                    summary=row["summary"],
                    content=row["content"],
                    tags=list(tags),
                    metadata=dict(metadata),
                    score=score,
                    importance=importance,
                    confidence=confidence,
                    created_ts=float(row["created_ts"]),
                    last_access_ts=float(row["last_access_ts"]),
                )
            )

        hits.sort(key=lambda hit: hit.score, reverse=True)
        selected = hits[: max(1, int(limit))]
        self._record_access([hit.id for hit in selected], now=now)
        return selected

    def render_prompt_context(
        self,
        query: str,
        *,
        kinds: Iterable[str] | None = None,
        limit: int = 8,
        max_chars: int = 2600,
        embed_fn: EmbeddingFn | None = None,
    ) -> str:
        hits = self.retrieve(query, kinds=kinds, limit=limit, embed_fn=embed_fn)
        if not hits:
            return ""
        priority = {
            "failure": 0,
            "reflection": 1,
            "procedural": 2,
            "semantic": 3,
            "episodic": 4,
            "tool_usage": 5,
            "project_rule": 6,
            "working": 7,
        }
        hits = sorted(hits, key=lambda hit: (priority.get(hit.kind, 99), -hit.score))
        lines = [
            "[AGENT MEMORY CONTEXT]",
            "Use these durable memories as decision evidence. Prefer recent high-score failures and reflections when choosing tools or repair strategies.",
        ]
        for hit in hits:
            lines.append(hit.prompt_line())
        rendered = "\n".join(lines)
        if len(rendered) <= max_chars:
            return rendered
        kept = []
        used = 0
        for line in lines:
            projected = used + len(line) + 1
            if projected > max_chars:
                break
            kept.append(line)
            used = projected
        kept.append("... [memory context truncated]")
        return "\n".join(kept)

    def reinforce(self, memory_id: str, amount: float = 0.08) -> bool:
        if not memory_id:
            return False
        with self._conn() as conn:
            row = conn.execute(
                "SELECT reinforcement FROM memories WHERE id=?",
                (memory_id,),
            ).fetchone()
            if not row:
                return False
            conn.execute(
                "UPDATE memories SET reinforcement=?, updated_ts=? WHERE id=?",
                (min(1.0, float(row["reinforcement"]) + amount), time.time(), memory_id),
            )
        return True

    def compact(self, *, max_records: int = 5000, min_importance: float = 0.12) -> dict[str, int]:
        """Prune expired and very weak old memories without touching high-value failures."""
        now = time.time()
        deleted_expired = 0
        deleted_weak = 0
        with self._conn() as conn:
            cur = conn.execute(
                "DELETE FROM memories WHERE expires_ts IS NOT NULL AND expires_ts <= ?", (now,)
            )
            deleted_expired = int(cur.rowcount or 0)
            total = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
            overflow = max(0, int(total) - int(max_records))
            if overflow > 0:
                rows = conn.execute(
                    """
                    SELECT id FROM memories
                    WHERE kind != 'failure' AND importance < ?
                    ORDER BY reinforcement ASC, last_access_ts ASC
                    LIMIT ?
                    """,
                    (min_importance, overflow),
                ).fetchall()
                ids = [row["id"] for row in rows]
                if ids:
                    placeholders = ",".join("?" for _ in ids)
                    cur = conn.execute(f"DELETE FROM memories WHERE id IN ({placeholders})", ids)
                    deleted_weak = int(cur.rowcount or 0)
        return {"expired": deleted_expired, "weak": deleted_weak}

    def stats(self) -> dict[str, Any]:
        with self._conn() as conn:
            total = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
            by_kind = conn.execute(
                "SELECT kind, COUNT(*) FROM memories GROUP BY kind ORDER BY kind"
            ).fetchall()
            failures = conn.execute(
                "SELECT COUNT(*) FROM memories WHERE kind='failure'"
            ).fetchone()[0]
        return {
            "total_memories": int(total),
            "failure_memories": int(failures),
            "by_kind": {row[0]: int(row[1]) for row in by_kind},
        }

    def _record_access(self, memory_ids: list[str], *, now: float) -> None:
        if not memory_ids:
            return
        with self._conn() as conn:
            conn.executemany(
                """
                UPDATE memories
                SET last_access_ts=?, access_count=access_count + 1
                WHERE id=?
                """,
                [(now, memory_id) for memory_id in memory_ids],
            )
