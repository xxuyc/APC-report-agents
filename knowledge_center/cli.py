#!/usr/bin/env python3
"""CLI for the Feishu multi-project knowledge center."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .documents import search_documents
from .listener import listen_forever

from .core import (
    KnowledgeError,
    build_knowledge_snapshot,
    build_retrieval_plan,
    resolve_project,
    repository_from_options,
    search_structured,
    writeback_run,
)


def emit(value):
    print(json.dumps(value, ensure_ascii=False, indent=2))


def repository(args):
    return repository_from_options(args.store, allow_empty=False)


def project_and_plan(args):
    repo = repository(args)
    target = resolve_project(repo, args.project_id, args.project_name, args.input or [], args.create_pending)
    plan = build_retrieval_plan(repo, target, args.agent_type, args.query, args.intent or [], args.reference_project_id or [])
    return repo, target, plan


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", help="本地七表 JSON；不提供时连接飞书 Base")
    sub = parser.add_subparsers(dest="command", required=True)

    def routing(name):
        p = sub.add_parser(name)
        p.add_argument("--project-id")
        p.add_argument("--project-name")
        p.add_argument("--input", action="append")
        p.add_argument("--create-pending", action="store_true")
        return p

    p = routing("resolve-project")
    p = routing("plan-retrieval")
    p.add_argument("--agent-type", required=True)
    p.add_argument("--query")
    p.add_argument("--intent", action="append")
    p.add_argument("--reference-project-id", action="append")
    p = routing("search-structured")
    p.add_argument("--agent-type", required=True); p.add_argument("--query"); p.add_argument("--intent", action="append"); p.add_argument("--reference-project-id", action="append")
    p = routing("search-documents")
    p.add_argument("--agent-type", required=True); p.add_argument("--query"); p.add_argument("--intent", action="append"); p.add_argument("--reference-project-id", action="append")
    p = routing("validate-reference")
    p.add_argument("--agent-type", required=True); p.add_argument("--query"); p.add_argument("--intent", action="append"); p.add_argument("--reference-project-id", action="append")
    p = routing("build-knowledge-snapshot")
    p.add_argument("--agent-type", required=True); p.add_argument("--query"); p.add_argument("--intent", action="append"); p.add_argument("--reference-project-id", action="append"); p.add_argument("--output", required=True)
    p = sub.add_parser("writeback")
    p.add_argument("--run", required=True, help="Agent run JSON")
    p = sub.add_parser("sync")
    p.add_argument("--output", required=True)
    sub.add_parser("listen")

    args = parser.parse_args(argv)
    try:
        if args.command == "resolve-project":
            emit(resolve_project(repository(args), args.project_id, args.project_name, args.input or [], args.create_pending)); return 0
        if args.command == "sync":
            repo = repository(args); data = {name: repo.list(name) for name in ("projects", "sources", "knowledge", "metrics", "requirements", "runs", "changes")}
            output = Path(args.output); output.parent.mkdir(parents=True, exist_ok=True); output.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"); emit({"output": str(output.resolve())}); return 0
        if args.command == "listen":
            listen_forever(lambda event: emit({"event": "bitable_record_changed", "payload": event})); return 0
        if args.command == "writeback":
            emit(writeback_run(repository(args), json.loads(Path(args.run).read_text(encoding="utf-8")))); return 0
        repo, target, plan = project_and_plan(args)
        if args.command == "plan-retrieval": emit(plan)
        elif args.command == "search-structured": emit(search_structured(repo, plan))
        elif args.command == "search-documents": emit(search_documents(repo, plan))
        elif args.command == "validate-reference": emit({"valid": not search_structured(repo, plan)["excluded_references"], "results": search_structured(repo, plan)})
        else:
            snapshot = build_knowledge_snapshot(repo, plan)
            output = Path(args.output); output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8"); emit({"output": str(output.resolve()), "sha256": snapshot["sha256"]})
        return 0
    except KnowledgeError as exc:
        emit(exc.as_dict()); return 3


if __name__ == "__main__":
    raise SystemExit(main())
