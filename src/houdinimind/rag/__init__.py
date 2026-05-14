# ==============================================================================
# Creator: Anshul Vashist
# Email: vashistanshul.7@gmail.com
# LinkedIn: https://www.linkedin.com/in/av-0001/
# ==============================================================================
"""
HoudiniMind RAG — Package
Hybrid retrieval-augmented generation for Houdini.
"""

from .bm25 import BM25
from .eval_harness import evaluate_retriever, load_eval_cases, run_retrieval_eval
from .injector import ContextInjector
from .kb_builder import (
    _load_high_fidelity_knowledge,
    _load_houdini_python_function_knowledge,
    _load_node_chain_training_data,
    _load_vex_function_db_knowledge,
    _load_vex_jsonl_knowledge,
    build_kb,
    rebuild_kb_from_session_feedback,
)
from .rag20 import Rag20ContextInjector, create_rag20_pipeline
from .retriever import HybridRetriever, QueryAwareShardRetriever


def _runtime_entry_key(entry: dict):
    return (
        entry.get("_source"),
        entry.get("_chain_id"),
        entry.get("_asset_name"),
        entry.get("_source_path"),
        entry.get("title"),
    )


def _knowledge_base_path(data_dir: str) -> str:
    import os

    primary = os.path.join(data_dir, "knowledge", "knowledge_base.json")
    generated = os.path.join(data_dir, "knowledge", "knowledge_base.generated.json")
    if os.path.exists(generated):
        if (not os.path.exists(primary)) or os.path.getmtime(generated) >= os.path.getmtime(
            primary
        ):
            return generated
    return primary


def _ensure_knowledge_base(data_dir: str) -> str:
    import os

    kb_path = _knowledge_base_path(data_dir)
    if os.path.exists(kb_path):
        return kb_path
    try:
        build_kb(output_path=kb_path, verbose=False)
    except Exception:
        pass
    return kb_path


def _load_generated_node_entries(data_dir: str) -> list[dict]:
    import json
    import os

    generated = os.path.join(data_dir, "knowledge", "knowledge_base.generated.json")
    if not os.path.exists(generated):
        return []
    try:
        with open(generated, encoding="utf-8") as handle:
            payload = json.load(handle)
    except Exception:
        return []

    if isinstance(payload, list):
        entries = payload
    elif isinstance(payload, dict) and isinstance(payload.get("entries"), list):
        entries = payload["entries"]
    else:
        return []

    node_entries = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        category = str(entry.get("category", "") or "").lower()
        source = str(entry.get("_source", "") or entry.get("source", "")).lower()
        title = str(entry.get("title", "") or "").lower()
        if category != "nodes" and not title.startswith(("sop node:", "node:")):
            continue
        if (
            "houdini_all_sops_knowledge" not in source
            and not str(entry.get("_node_type", "") or "").strip()
        ):
            continue

        node_entry = dict(entry)
        node_type = str(node_entry.get("_node_type") or node_entry.get("title") or "").strip()
        node_entry["_id"] = f"generated_node:{node_type.lower()}"
        node_entry["category"] = "nodes"
        node_entries.append(node_entry)
    return node_entries


def _build_embed_fn(config: dict):
    cfg = config or {}
    if not cfg.get("rag_hybrid_search", True):
        return None
    shared_embed_fn = cfg.get("_shared_embed_fn")
    if callable(shared_embed_fn):
        return shared_embed_fn
    try:
        from ..agent.llm_client import OllamaClient

        client = OllamaClient(cfg)
    except Exception:
        return None

    embed_model = cfg.get("model_routing", {}).get("embedding") or cfg.get("embed_model")

    def _embed(text: str):
        return client.embed(text, model=embed_model)

    return _embed


def create_rag_pipeline(data_dir: str, config: dict | None = None) -> ContextInjector:
    """
    Factory: build the full RAG pipeline from a data directory.
    Returns a ready-to-use ContextInjector.

    Usage in AgentLoop:
        injector = create_rag_pipeline(data_dir, config)
        augmented_messages = injector.inject_into_messages(messages, user_query)
    """
    cfg = config or {}
    rag_backend = str(cfg.get("rag_backend", "") or "").strip().lower()
    if rag_backend in {"rag2", "rag2.0", "rag20", "gemini", "gemini_houdini"}:
        return create_rag20_pipeline(data_dir, cfg)

    kb_path = _ensure_knowledge_base(data_dir)
    hybrid_weight = cfg.get(
        "rag_hybrid_weight",
        0.4 if cfg.get("rag_hybrid_search", True) else 0.0,
    )
    _max_entry_chars = int(cfg.get("rag_max_entry_chars", 20000))
    if cfg.get("rag_query_routing", True):
        retriever = QueryAwareShardRetriever(
            kb_path=kb_path,
            embed_fn=_build_embed_fn(cfg),
            hybrid_weight=hybrid_weight,
            min_score=cfg.get("rag_min_score", 0.1),
            enable_rerank=cfg.get("rag_enable_rerank", True),
            max_shards_per_query=cfg.get("rag_max_shards_per_query", 3),
            shard_prefetch_embeddings=cfg.get("rag_prefetch_shard_embeddings", False),
            max_entry_chars=_max_entry_chars,
            candidate_pool_size=cfg.get("rag_candidate_pool_size", 256),
            vector_backend=cfg.get("rag_vector_backend", "auto"),
        )
    else:
        retriever = HybridRetriever(
            kb_path=kb_path,
            embed_fn=_build_embed_fn(cfg),
            hybrid_weight=hybrid_weight,
            min_score=cfg.get("rag_min_score", 0.1),
            enable_rerank=cfg.get("rag_enable_rerank", True),
            max_entry_chars=_max_entry_chars,
            candidate_pool_size=cfg.get("rag_candidate_pool_size", 256),
            vector_backend=cfg.get("rag_vector_backend", "auto"),
        )
    existing_keys = {_runtime_entry_key(entry) for entry in getattr(retriever, "_entries", [])}
    runtime_entries = []
    for entry in _load_generated_node_entries(data_dir):
        key = _runtime_entry_key(entry)
        if key not in existing_keys:
            runtime_entries.append(entry)
            existing_keys.add(key)
    for entry in _load_node_chain_training_data():
        key = _runtime_entry_key(entry)
        if key not in existing_keys:
            runtime_entries.append(entry)
            existing_keys.add(key)
    for entry in _load_high_fidelity_knowledge():
        key = _runtime_entry_key(entry)
        if key not in existing_keys:
            runtime_entries.append(entry)
            existing_keys.add(key)
    for entry in _load_houdini_python_function_knowledge(data_dir):
        key = _runtime_entry_key(entry)
        if key not in existing_keys:
            runtime_entries.append(entry)
            existing_keys.add(key)
    for entry in _load_vex_function_db_knowledge(data_dir):
        key = _runtime_entry_key(entry)
        if key not in existing_keys:
            runtime_entries.append(entry)
            existing_keys.add(key)
    for entry in _load_vex_jsonl_knowledge(data_dir):
        key = _runtime_entry_key(entry)
        if key not in existing_keys:
            runtime_entries.append(entry)
            existing_keys.add(key)
    retriever.extend_entries(runtime_entries)

    injector = ContextInjector(
        retriever=retriever,
        max_context_tokens=cfg.get("rag_max_context_tokens", 3000),
        top_k=cfg.get("rag_top_k", 4),
        min_score=cfg.get("rag_min_score", 0.1),
        model_name=cfg.get("model", ""),
    )
    return injector


__all__ = [
    "BM25",
    "ContextInjector",
    "HybridRetriever",
    "QueryAwareShardRetriever",
    "Rag20ContextInjector",
    "build_kb",
    "create_rag20_pipeline",
    "create_rag_pipeline",
    "evaluate_retriever",
    "load_eval_cases",
    "rebuild_kb_from_session_feedback",
    "run_retrieval_eval",
]
