#!/usr/bin/env python3
"""CLI wrapper for the bundled RAG 2.0 Houdini knowledge assets."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[3]
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from houdinimind.rag.rag20 import Rag20ContextInjector


def _print_json(payload: object) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def _search_general(injector: Rag20ContextInjector, query: str, limit: int) -> list[dict]:
    return [
        {
            "source": item.get("title", ""),
            "path": item.get("id", ""),
            "content": item.get("content", ""),
        }
        for item in injector._search_general(query, limit)
    ]


def _search_vex(injector: Rag20ContextInjector, query: str, limit: int) -> list[dict]:
    return [
        {
            "source": "vex_functions.db",
            "name": item.get("title", "").replace("VEX Function: ", ""),
            "category": item.get("category", ""),
            "content": item.get("content", ""),
        }
        for item in injector._search_vex(query, limit, force=True)
    ]


def _search_live(injector: Rag20ContextInjector, query: str, limit: int) -> list[dict]:
    return [
        {
            "source": "houdini_all_parameters_live.json",
            "category": item.get("category", ""),
            "internal_name": item.get("internal_name", ""),
            "description": item.get("description", ""),
            "parameters": item.get("parameters", {}),
            "score": item.get("score", 0),
        }
        for item in injector.live_node_hints(query, limit=limit)
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Search bundled HoudiniMind RAG 2.0 assets.")
    parser.add_argument(
        "--asset-dir",
        default=None,
        help="Directory containing gemini_houdini_rag.db, vex_functions.db, and live parameter JSON.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    for command, help_text in {
        "search": "Search general Houdini knowledge.",
        "vex": "Search VEX functions.",
        "live": "Search live SOP node and parameter metadata.",
    }.items():
        subparser = subparsers.add_parser(command, help=help_text)
        subparser.add_argument("query")
        subparser.add_argument("limit", type=int, nargs="?", default=5)

    args = parser.parse_args()
    injector = Rag20ContextInjector(asset_dir=args.asset_dir)
    limit = max(1, int(args.limit or 1))

    if args.command == "search":
        _print_json(_search_general(injector, args.query, limit))
    elif args.command == "vex":
        _print_json(_search_vex(injector, args.query, limit))
    elif args.command == "live":
        _print_json(_search_live(injector, args.query, limit))


if __name__ == "__main__":
    main()
