#!/usr/bin/env python3
"""A1-only local preparation export. No answering, retrieval or coverage calls."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
from pathlib import Path
import secrets
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("input", type=Path)
    p.add_argument("--directory", type=Path, required=True)
    p.add_argument("--query-column", required=True)
    for field in ("session", "timestamp", "date", "time", "role", "source-query-id"):
        p.add_argument("--" + field + "-column")
    p.add_argument("--encoding", default="utf-8-sig", choices=("utf-8-sig", "utf-8", "utf-16"))
    p.add_argument("--delimiter", default=",", choices=(",", ";", "\t", "|"))
    p.add_argument("--calendar", default="gregorian", choices=("gregorian", "jalali"))
    p.add_argument("--source-timezone")
    p.add_argument("--authoritative-source-order", action="store_true")
    p.add_argument("--model-limit", type=int, default=0)
    p.add_argument("--confirmed", action="store_true", dest="confirmed", help="confirm live audit work against the configured services")
    p.add_argument("--confirmed-staging", action="store_true", dest="confirmed", help=argparse.SUPPRESS)
    group = p.add_mutually_exclusive_group()
    group.add_argument("--capture-snapshot", action="store_true")
    group.add_argument("--snapshot", type=Path)
    return p


async def run(args):
    # Established explicit-root loader precedes configuration/service imports.
    # Diagnostic process only: suppress SDK/library content/error logging.
    logging.disable(logging.CRITICAL)
    from knowledge_audit.inputs import CsvInputAdapter, ColumnMapping, TimestampPolicy
    from knowledge_audit.privacy import AuditError, Redactor, private_directory, private_write
    from knowledge_audit.preparation import QueryPreparer, prepare_dataset
    from knowledge_audit.export import export_preparation
    from knowledge_audit.runtime import (confirm_live_run, code_identity, configuration_identity,
                                         serving_identity, live_components)
    from knowledge_audit.snapshot import capture_snapshot, load_snapshot
    from utils.concurrency import BoundedBlockingRunner
    from utils.persian_hybrid_search import PersianTextProcessor
    from utils.performance_config import PERFORMANCE_SETTINGS
    if not 0 <= args.model_limit <= 10:
        raise AuditError("invalid_model_sample_limit")
    if args.model_limit or args.capture_snapshot:
        confirm_live_run(confirmed=args.confirmed, model=bool(args.model_limit), snapshot=args.capture_snapshot)
    directory = private_directory(args.directory)
    if any(directory.iterdir()):
        raise AuditError("artifact_directory_not_empty")
    key = secrets.token_bytes(32)
    redactor = Redactor(key)
    policy = TimestampPolicy(args.calendar, args.source_timezone, args.authoritative_source_order)
    mapping = ColumnMapping(args.query_column, args.session_column, args.timestamp_column,
                            args.date_column, args.time_column, args.role_column, args.source_query_id_column)
    dataset = CsvInputAdapter(args.input, mapping, policy=policy,
                              encoding=args.encoding, delimiter=args.delimiter).load(redactor)
    private_write(directory / "privacy.key", key)
    snapshot_id = ""
    if args.capture_snapshot:
        from scripts.kb_signature import create_signature
        from knowledge_audit.snapshot import read_postgres_snapshot
        from new_architecture.app.services.history.database import DatabaseManager
        from knowledge_audit.settings import load_coverage_settings
        manifest = capture_snapshot(directory, redactor, signature_provider=create_signature,
            content_provider=lambda: read_postgres_snapshot(DatabaseManager().get_connection),
            public_contacts=load_coverage_settings().public_contacts)
        snapshot_id = manifest["snapshot_id"]
    elif args.snapshot:
        snapshot_id = load_snapshot(args.snapshot)["snapshot_id"]
    configuration = configuration_identity(policy, args.model_limit, redactor)
    version = code_identity()
    runner = BoundedBlockingRunner(1)
    rag = None
    try:
        processor = await runner.run(PersianTextProcessor, use_stemming=False)
        rewriter, classifier, serving = None, None, None
        if args.model_limit:
            import httpx
            async with httpx.AsyncClient(timeout=PERFORMANCE_SETTINGS.tei_http_read_timeout_seconds) as http:
                serving = await serving_identity(http, redactor)
                rag, rewriter, classifier = await live_components(runner, http)
                results = await prepare_dataset(dataset, QueryPreparer(processor, runner, rewriter, classifier),
                    redactor, model_limit=args.model_limit,
                    timeout_seconds=PERFORMANCE_SETTINGS.application_request_timeout_seconds)
                final_serving = await serving_identity(http, redactor)
                if serving != final_serving:
                    raise AuditError("preparation_serving_drift")
                serving["call_counts"] = rag.audit_call_counts
        else:
            results = await prepare_dataset(dataset, QueryPreparer(processor, runner), redactor)
    finally:
        if rag is not None:
            await rag.aclose()
        await runner.aclose()
    if hashlib.sha256(args.input.read_bytes()).hexdigest() != dataset.input_id:
        raise AuditError("input_changed_during_preparation")
    manifest = export_preparation(directory, dataset, results, run_id="a1_" + secrets.token_hex(16),
        configuration=configuration, code_identity=version, redactor=redactor,
        snapshot_id=snapshot_id, serving_identity=serving)
    print(json.dumps({k: manifest[k] for k in ("run_id", "export_id", "input_id", "kb_snapshot_id",
        "configuration_id", "preparation_code_id", "selected_row_count", "source_row_count",
        "preparation_status_counts", "model_prepared_count")}, sort_keys=True))
    return 0


def main(argv=None):
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env", override=False)
    from knowledge_audit.settings import require_coverage_enabled
    from knowledge_audit.privacy import AuditError
    try:
        require_coverage_enabled()
    except AuditError as error:
        print(str(error), file=sys.stderr)
        return 2
    args = parser().parse_args(argv)
    try:
        return asyncio.run(run(args))
    except AuditError as error:
        print(str(error), file=sys.stderr)
        return 2
    except Exception:
        # No exception strings, raw SDK bodies, paths or tracebacks.
        print(json.dumps({"status": "failed", "error_code": "a1_diagnostic_failed"}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
