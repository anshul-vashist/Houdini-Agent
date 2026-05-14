# ==============================================================================
# Creator: Anshul Vashist
# Email: vashistanshul.7@gmail.com
# LinkedIn: https://www.linkedin.com/in/av-0001/
# ==============================================================================
"""
RAG 2.0 adapter for the Gemini Houdini RAG assets.

The source script in ``src/houdinimind/agent/rag2.0`` is a CLI.  This module
uses the same local database files directly and exposes the ContextInjector
surface expected by AgentLoop.
"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any

_ASSET_DIR = Path(__file__).resolve().parents[1] / "agent" / "rag2.0"
_GENERAL_DB = _ASSET_DIR / "gemini_houdini_rag.db"
_VEX_DB = _ASSET_DIR / "vex_functions.db"
_LIVE_JSON = _ASSET_DIR / "houdini_all_parameters_live.json"

_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "do",
    "does",
    "for",
    "from",
    "how",
    "i",
    "in",
    "is",
    "it",
    "me",
    "of",
    "on",
    "or",
    "set",
    "the",
    "then",
    "this",
    "to",
    "use",
    "what",
    "with",
}

_VEX_HINT_RE = re.compile(
    r"(@[A-Za-z_]\w*|\b(vex|wrangle|attribwrangle|snippet|function|fit|noise|pcopen)\b)",
    re.IGNORECASE,
)
_LIVE_HINT_RE = re.compile(
    r"\b(sop|node|nodes|parm|parms|parameter|parameters|tube|box|sphere|grid|"
    r"polyextrude|poly\s+extrude|extrude|columns|rows|cols|primitive|primitives)\b",
    re.IGNORECASE,
)


def _tokenise(text: str) -> list[str]:
    tokens = [
        token.lower()
        for token in re.findall(r"[A-Za-z_][A-Za-z0-9_]*|\d+(?:\.\d+)?", str(text or ""))
    ]
    expanded = []
    for token in tokens:
        if token in _STOPWORDS:
            continue
        expanded.append(token)
        if token == "columns":
            expanded.append("cols")
        elif token == "cols":
            expanded.append("columns")
        elif token == "polyextrude":
            expanded.extend(["poly", "extrude"])
    return list(dict.fromkeys(expanded))


def _clip(text: str, limit: int) -> str:
    text = str(text or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "\n... [truncated]"


class Rag20ContextInjector:
    """Context injector backed by the copied Gemini Houdini RAG assets."""

    def __init__(
        self,
        asset_dir: str | Path | None = None,
        max_context_tokens: int = 3000,
        top_k: int = 5,
        model_name: str = "",
    ):
        self.asset_dir = Path(asset_dir) if asset_dir else _ASSET_DIR
        self.general_db_path = self.asset_dir / "gemini_houdini_rag.db"
        self.vex_db_path = self.asset_dir / "vex_functions.db"
        self.live_json_path = self.asset_dir / "houdini_all_parameters_live.json"
        self.max_context_tokens = int(max_context_tokens or 3000)
        self.top_k = int(top_k or 5)
        self.model_name = model_name
        self.last_context_meta: dict[str, Any] = {}
        self.debug_logger = None
        self.retriever = self
        self._live_data: dict[str, Any] | None = None

    @staticmethod
    def estimate_tokens(text: str) -> int:
        return max(1, len(str(text or "")) // 4)

    def _search_general(self, query: str, limit: int) -> list[dict]:
        if not self.general_db_path.exists():
            return []
        words = _tokenise(query)
        if not words:
            return []

        sql = (
            "SELECT source, path, content FROM knowledge "
            "WHERE knowledge MATCH ? ORDER BY rank LIMIT ?"
        )
        queries = [" AND ".join(words), " OR ".join(words), query]
        results: list[dict] = []
        seen = set()
        try:
            with sqlite3.connect(str(self.general_db_path)) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                for fts_query in queries:
                    if not fts_query:
                        continue
                    try:
                        cursor.execute(sql, (fts_query, limit))
                    except sqlite3.Error:
                        continue
                    for row in cursor.fetchall():
                        key = (row["source"], row["path"], row["content"][:120])
                        if key in seen:
                            continue
                        seen.add(key)
                        results.append(
                            {
                                "id": f"rag20:general:{len(results)}",
                                "title": f"{row['source']} - {row['path']}",
                                "category": "rag2_general",
                                "content": row["content"],
                                "_score": 1.0,
                            }
                        )
                    if results:
                        break
        except sqlite3.Error:
            return []
        return results[:limit]

    def _search_vex(self, query: str, limit: int, force: bool = False) -> list[dict]:
        if not self.vex_db_path.exists() or (not force and not _VEX_HINT_RE.search(query)):
            return []
        terms = _tokenise(query)
        raw_terms = re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", str(query or ""))
        candidates = list(dict.fromkeys([*raw_terms, *terms, query]))
        sql = """
            SELECT f.name, f.summary, f.description, f.category, f.examples,
                   GROUP_CONCAT(s.signature, ' | ') as signatures
            FROM functions f
            LEFT JOIN signatures s ON f.name = s.function_name
            WHERE f.name LIKE ? OR f.summary LIKE ? OR f.description LIKE ?
            GROUP BY f.id
            LIMIT ?
        """
        exact_sql = """
            SELECT f.name, f.summary, f.description, f.category, f.examples,
                   GROUP_CONCAT(s.signature, ' | ') as signatures
            FROM functions f
            LEFT JOIN signatures s ON f.name = s.function_name
            WHERE lower(f.name) = lower(?)
            GROUP BY f.id
            LIMIT ?
        """
        rows = []
        try:
            with sqlite3.connect(str(self.vex_db_path)) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                for candidate in candidates:
                    if not candidate or candidate.lower() in _STOPWORDS:
                        continue
                    cursor.execute(exact_sql, (candidate, limit))
                    rows = cursor.fetchall()
                    if rows:
                        break
                for candidate in candidates:
                    if rows:
                        break
                    if not candidate or candidate.lower() in _STOPWORDS:
                        continue
                    like = f"%{candidate}%"
                    cursor.execute(sql, (like, like, like, limit))
                    rows = cursor.fetchall()
                    if rows:
                        break
        except sqlite3.Error:
            return []

        results = []
        for row in rows[:limit]:
            signatures = row["signatures"].split(" | ") if row["signatures"] else []
            parts = [
                f"Name: {row['name']}",
                f"Category: {row['category'] or ''}",
                f"Summary: {row['summary'] or ''}",
                f"Description: {row['description'] or ''}",
            ]
            if signatures:
                parts.append("Signatures:\n- " + "\n- ".join(signatures[:8]))
            if row["examples"]:
                parts.append("Examples:\n" + str(row["examples"]))
            results.append(
                {
                    "id": f"rag20:vex:{row['name']}",
                    "title": f"VEX Function: {row['name']}",
                    "category": "vex",
                    "content": "\n".join(parts),
                    "_score": 1.2,
                }
            )
        return results

    def _load_live_data(self) -> dict[str, Any]:
        if self._live_data is not None:
            return self._live_data
        if not self.live_json_path.exists():
            self._live_data = {}
            return self._live_data
        try:
            with open(self.live_json_path, encoding="utf-8") as handle:
                payload = json.load(handle)
        except Exception:
            payload = {}
        self._live_data = payload if isinstance(payload, dict) else {}
        return self._live_data

    def _search_live(self, query: str, limit: int, force: bool = False) -> list[dict]:
        if not force and not _LIVE_HINT_RE.search(query):
            return []
        data = self._load_live_data()
        if not data:
            return []
        terms = _tokenise(query)
        scored: list[tuple[float, str, dict]] = []
        for key, info in data.items():
            if not isinstance(info, dict):
                continue
            params = info.get("parameters") if isinstance(info.get("parameters"), dict) else {}
            param_blob = " ".join(
                [str(name) for name in params]
                + [str(meta.get("label", "")) for meta in params.values() if isinstance(meta, dict)]
            )
            name = str(info.get("internal_name", ""))
            blob = f"{key} {name} {info.get('description', '')} {param_blob}".lower()
            score = 0.0
            for term in terms:
                if not term:
                    continue
                if term == name.lower():
                    score += 4.0
                elif term in key.lower():
                    score += 2.5
                elif re.search(r"\b" + re.escape(term) + r"\b", blob):
                    score += 1.0
                elif term in blob:
                    score += 0.4
            if score > 0:
                scored.append((score, key, info))
        scored.sort(key=lambda item: item[0], reverse=True)

        results = []
        for score, key, info in scored[:limit]:
            params = info.get("parameters") if isinstance(info.get("parameters"), dict) else {}
            param_lines = []
            for parm_name, meta in list(params.items())[:80]:
                if isinstance(meta, dict):
                    param_lines.append(
                        f"- {meta.get('label', parm_name)} ({parm_name}): {meta.get('type', '')}"
                    )
                else:
                    param_lines.append(f"- {parm_name}: {meta}")
            content = "\n".join(
                [
                    f"Node Key: {key}",
                    f"Category: {info.get('category', '')}",
                    f"Internal Name: {info.get('internal_name', '')}",
                    f"Description: {info.get('description', '')}",
                    "Parameters:",
                    *param_lines,
                ]
            )
            results.append(
                {
                    "id": f"rag20:live:{key}",
                    "title": f"Live Parameters: {key}",
                    "category": "nodes",
                    "content": content,
                    "_score": round(score, 3),
                }
            )
        return results

    def live_node_hints(self, query: str, limit: int = 3) -> list[dict[str, Any]]:
        """Return structured live node/parameter matches from RAG 2.0 assets."""
        matches = self._search_live(query, max(1, int(limit or 1)), force=True)
        data = self._load_live_data()
        hints: list[dict[str, Any]] = []
        for match in matches:
            chunk_id = str(match.get("id") or "")
            key = chunk_id.rsplit("rag20:live:", 1)[-1] if "rag20:live:" in chunk_id else ""
            info = data.get(key) if key else None
            if not isinstance(info, dict):
                continue
            params = info.get("parameters") if isinstance(info.get("parameters"), dict) else {}
            hints.append(
                {
                    "key": key,
                    "category": info.get("category", ""),
                    "internal_name": info.get("internal_name", ""),
                    "description": info.get("description", ""),
                    "parameters": params,
                    "score": match.get("_score", 0),
                }
            )
        return hints

    def live_hint_message(self, query: str, limit: int = 3, max_parameters: int = 24) -> str:
        """Render exact RAG 2.0 internal node and parameter names for the prompt."""
        hints = self.live_node_hints(query, limit=limit)
        if not hints:
            return ""
        lines = [
            "[RAG 2.0 LIVE NODE/PARAMETER NAMES]",
            "Use these exact Houdini internal names before creating nodes or setting parameters.",
        ]
        for hint in hints:
            category = str(hint.get("category") or "").strip()
            internal = str(hint.get("internal_name") or "").strip()
            description = str(hint.get("description") or "").strip()
            key = str(hint.get("key") or "").strip()
            heading = f"{key}: internal node type `{internal}`"
            if description and description.lower() != internal.lower():
                heading += f" ({description})"
            lines.append(f"- {heading}")
            params = hint.get("parameters") if isinstance(hint.get("parameters"), dict) else {}
            param_bits = []
            for parm_name, meta in list(params.items())[: max(1, int(max_parameters or 1))]:
                if isinstance(meta, dict):
                    label = str(meta.get("label") or parm_name)
                    typ = str(meta.get("type") or "")
                    param_bits.append(f"{label}=`{parm_name}`{f'/{typ}' if typ else ''}")
                else:
                    param_bits.append(f"`{parm_name}`")
            if category:
                lines.append(f"  Category: {category}")
            if param_bits:
                lines.append("  Parameters: " + ", ".join(param_bits))
        lines.append(
            "For label-based requests such as 'Uniform Scale', set the listed internal parameter name, not a guessed alias."
        )
        return "\n".join(lines)

    def retrieve(self, query: str, top_k: int = 5, **kwargs) -> list[dict]:
        category_filter = str(kwargs.get("category_filter") or "").lower()
        include_categories = {
            str(cat).lower() for cat in (kwargs.get("include_categories") or []) if str(cat).strip()
        }
        force_vex = category_filter == "vex" or "vex" in include_categories
        force_live = category_filter == "nodes" or "nodes" in include_categories
        live_limit = max(2, min(top_k, 4))
        vex_limit = max(2, min(top_k, 4))
        general_limit = max(2, top_k)
        chunks = [
            *self._search_live(query, live_limit, force=force_live),
            *self._search_vex(query, vex_limit, force=force_vex),
            *self._search_general(query, general_limit),
        ]
        deduped = []
        seen_titles = set()
        for chunk in chunks:
            key = str(chunk.get("title", "")).lower()
            if key in seen_titles:
                continue
            seen_titles.add(key)
            deduped.append(chunk)
        deduped.sort(key=lambda item: float(item.get("_score", 0.0)), reverse=True)
        return deduped[:top_k]

    def build_context_message(
        self,
        query: str,
        request_mode: str | None = None,
        live_scene_json: str | None = None,
        force_chunks: list[str] | None = None,
        include_categories: list[str] | None = None,
        exclude_categories: list[str] | None = None,
        include_memory: bool = True,
    ) -> dict | None:
        del request_mode, force_chunks, exclude_categories, include_memory
        chunks = self.retrieve(query, top_k=self.top_k, include_categories=include_categories)
        if live_scene_json:
            chunks.insert(
                0,
                {
                    "id": "live_scene",
                    "title": "Current Houdini Scene",
                    "category": "live",
                    "content": live_scene_json,
                    "_score": 2.0,
                },
            )
        if not chunks:
            self.last_context_meta = {
                "query": query,
                "backend": "rag2.0",
                "used_count": 0,
                "chunk_titles": [],
                "chunk_categories": [],
                "estimated_tokens": 0,
            }
            return None

        content = self._format_chunks(chunks)
        estimated_tokens = self.estimate_tokens(content)
        self.last_context_meta = {
            "query": query,
            "backend": "rag2.0",
            "used_count": len(chunks),
            "chunk_ids": [chunk.get("id") for chunk in chunks],
            "chunk_titles": [chunk.get("title", "") for chunk in chunks],
            "chunk_categories": [chunk.get("category", "") for chunk in chunks],
            "chunk_scores": [chunk.get("_score", 0) for chunk in chunks],
            "estimated_tokens": estimated_tokens,
            "asset_dir": str(self.asset_dir),
        }
        if self.debug_logger:
            self.debug_logger.log_rag_detail(dict(self.last_context_meta))
        return {"role": "system", "content": content}

    def inject_into_messages(self, messages: list[dict], query: str, **kwargs) -> list[dict]:
        ctx_msg = self.build_context_message(query, **kwargs)
        if ctx_msg is None:
            return messages
        return self.inject_prebuilt(messages, ctx_msg)

    def inject_prebuilt(self, messages: list[dict], prebuilt_msg: dict) -> list[dict]:
        if not prebuilt_msg or not isinstance(prebuilt_msg, dict):
            return messages
        insert_at = len(messages)
        for index in reversed(range(len(messages))):
            if messages[index].get("role") == "user":
                insert_at = index
                break
        result = list(messages)
        result.insert(insert_at, prebuilt_msg)
        return result

    def _format_chunks(self, chunks: list[dict]) -> str:
        budget_chars = max(2000, int(self.max_context_tokens * 4))
        header = (
            "# RAG 2.0 Houdini Knowledge\n"
            "Use this local RAG 2.0 context instead of the legacy HoudiniMind RAG.\n"
        )
        used = len(header)
        sections = []
        for chunk in chunks:
            title = chunk.get("title", "")
            category = chunk.get("category", "")
            body_budget = max(500, min(3500, budget_chars - used - 120))
            if body_budget <= 500:
                break
            body = _clip(str(chunk.get("content", "")), body_budget)
            section = f"## {title}\nCategory: {category}\n{body}"
            used += len(section) + 2
            sections.append(section)
            if used >= budget_chars:
                break
        return header + "\n\n".join(sections)


def create_rag20_pipeline(_data_dir: str, config: dict | None = None) -> Rag20ContextInjector:
    cfg = config or {}
    asset_dir = cfg.get("rag20_asset_dir") or cfg.get("rag2_asset_dir") or _ASSET_DIR
    injector = Rag20ContextInjector(
        asset_dir=asset_dir,
        max_context_tokens=cfg.get("rag_max_context_tokens", 3000),
        top_k=cfg.get("rag_top_k", 5),
        model_name=cfg.get("model", ""),
    )
    return injector
