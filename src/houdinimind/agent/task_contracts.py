# ==============================================================================
# Creator: Anshul Vashist
# Email: vashistanshul.7@gmail.com
# LinkedIn: https://www.linkedin.com/in/av-0001/
# ==============================================================================
"""Compatibility shim for the retired task-contract system.

Task-specific contracts used to encode Houdini domain rules in Python. That
conflicts with the anti-hardcoding policy because it makes backend code decide
which node families, terms, or workflows satisfy a user request. Verification is
now handled by generic scene checks plus LLM/RAG-driven review in AgentLoop.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TaskContract:
    contract_id: str
    title: str
    domains: tuple[str, ...] = ()
    rag_categories: tuple[str, ...] = ()
    acceptance: tuple[str, ...] = ()
    repair_hint: str = ""


def build_task_contract(query: str) -> TaskContract | None:
    """Return no hardcoded task contract for every request."""
    _ = query
    return None


def task_contract_rag_categories(contract: TaskContract | None) -> list[str]:
    _ = contract
    return []


def format_task_contract_guidance(contract: TaskContract | None) -> str | None:
    _ = contract
    return None


def verify_task_contract(
    contract: TaskContract | None,
    before_snapshot: dict[str, Any] | None,
    after_snapshot: dict[str, Any] | None,
    parent_paths: list[str],
    outputs: list[str],
) -> list[dict[str, Any]]:
    _ = contract, before_snapshot, after_snapshot, parent_paths, outputs
    return []
