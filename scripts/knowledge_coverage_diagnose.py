#!/usr/bin/env python3
"""Bounded A2.2 operator diagnosis: two saved boundaries, no query pipeline."""
import argparse
import asyncio
import json
import logging
import os
import re
from pathlib import Path
import secrets
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
ROW_IDS = ("row_7a55dfd6fb2e3bf750d99fa30e975d30", "row_85acf8adf43bd6feb04d01f90927b68e")


def synthetic_snapshot(repeats):
    from utils.read_only_audit import canonical_sha256
    records = [{"chunk_id":str(i), "faq_entry_id":str(i), "question":"Imaginary approval terms?",
        "answer":"Imaginary approval takes two days. Submit before 18:00. " * repeats,
        "main_category":"Synthetic", "sub_category":"Synthetic", "document_revision":1,
        "redaction_changed":False} for i in range(1, 6)]
    for r in records:
        r["content_sha256"] = canonical_sha256(r)
    return {"snapshot_id":canonical_sha256(records), "records":records}


async def run(args):
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env", override=False)
    logging.disable(logging.CRITICAL)
    import httpx
    from knowledge_audit.settings import load_coverage_settings
    from knowledge_audit.store import CoverageStore
    from knowledge_audit.runtime import confirm_staging, code_identity
    from knowledge_audit.model import AuditModel
    from knowledge_audit.evidence import EvidenceIndex
    from knowledge_audit.privacy import AuditError, private_directory
    from knowledge_audit.service import standalone_components
    from knowledge_audit.telemetry import sample, gpu_sample
    from utils.concurrency import BoundedBlockingRunner, AdmissionLimiter
    from utils.read_only_audit import canonical_sha256
    settings = load_coverage_settings()
    confirm_staging(confirmed=args.confirmed_staging, model=True, snapshot=True)
    store = CoverageStore(settings.artifact_dir)
    meta = store.owned("runs", args.run_id, 0)
    _, redactor = store.dataset(meta["dataset_id"], 0)
    index = EvidenceIndex(store.snapshot(meta["snapshot_id"], 0))
    diagnostics = private_directory(store.root / "diagnostics")
    if args.followup_id:
        if not re.fullmatch(r"diag_[0-9a-f]{32}", args.followup_id):
            raise AuditError("invalid_diagnostic_id")
        directory = private_directory(diagnostics / args.followup_id)
        report = store.read(directory / "summary.json")
        if report["source_run"] != args.run_id or report["dispatches"] != 6 or not report.get("completed") or report.get("followup_started"):
            raise AuditError("diagnostic_followup_not_eligible")
        report["followup_started"] = True
        store.write(directory / "summary.json", report)
    else:
        directory = private_directory(diagnostics / ("diag_" + secrets.token_hex(16)))
        report = {"version": "boundary-diagnosis-1", "source_run": args.run_id, "snapshot_id": index.snapshot_id,
        "dispatch_budget": 12, "dispatches": 0, "experiments": [], "code": code_identity(),
        "network_retry_policy": "none", "historical_request_hash_available": False}
    runner = BoundedBlockingRunner(1)
    report.setdefault("operator_code_sha256", canonical_sha256_file(Path(__file__)))
    answering = close = None
    try:
        answering, close = await standalone_components(runner)
        rag = answering.agent_service.rag_system
        report["client_policy"] = {k: getattr(rag.client.timeout, k) for k in ("connect", "read", "write", "pool")}
        report["sdk_max_retries"] = rag.client.max_retries
        if rag.client.max_retries != 0:
            raise AuditError("diagnostic_network_retries_forbidden")
        completion = rag._completion
        policy = {"read":None}
        async def bounded(**kwargs):
            if report["dispatches"] >= report["dispatch_budget"]:
                raise AuditError("diagnostic_budget_exhausted")
            report["dispatches"] += 1
            store.write(directory / "summary.json", report)
            if policy["read"] is not None:
                kwargs["timeout"] = httpx.Timeout(connect=rag.client.timeout.connect, read=policy["read"],
                    write=rag.client.timeout.write,pool=rag.client.timeout.pool)
            return await completion(**kwargs)
        rag._completion = bounded
        async with httpx.AsyncClient(timeout=40) as http:
            model = AuditModel(rag, http, os.environ["VLLM_URL"], settings, redactor,
                               limiter=AdmissionLimiter(1, name="coverage-diagnosis"))
            await model.discover()
            model.metrics_path = directory / "model-metrics.jsonl"
            report["serving"] = model.serving
            data = {}
            for rid in ROW_IDS:
                row = store.row(args.run_id, rid, 0)
                ids = [cid for cid in row["production_context_ids"]
                       if row["question_evidence"]["entry_status"].get(cid) == "model_requested"]
                if len(ids) != 5:
                    raise AuditError("diagnostic_boundary_ambiguous")
                payload = {"question": row["standalone_query_redacted"], "aspects": row["requested_aspects"],
                           "entries": [index.entry(cid) for cid in ids]}
                tokens, _ = await model.count("batch", payload)
                old = [m for m in row["model_metrics"] if m["role"] == "batch" and m["status"] == "error"]
                if len(old) != 1 or tokens != old[0]["prompt_tokens"]:
                    raise AuditError("diagnostic_reconstruction_mismatch")
                data[rid] = payload
                report.setdefault("reconstruction", {})[rid] = {"entry_ids": ids, "prompt_tokens": tokens,
                    "historical_token_count_match": True, "payload_sha256": canonical_sha256(payload),
                    "original_prompt_schema_files_match": all(canonical_sha256_file(ROOT / p) == meta["versions"]["code"]["file_sha256"][p]
                        for p in ("knowledge_audit/prompts.py", "knowledge_audit/schemas.py"))}
            # Comparable complete fictional entries; tune only synthetic length by
            # exact served token counts. No customer/KB text enters fixtures.
            synthetic = None
            target = report["reconstruction"][ROW_IDS[0]]["prompt_tokens"]
            for repeats in range(1, 25):
                snap = synthetic_snapshot(repeats)
                synthetic = {"question": "Imaginary approval duration and cutoff?",
                    "aspects": [{"aspect_id":"a1","description":"Approval duration","conditions":[]},
                                {"aspect_id":"a2","description":"Submission cutoff","conditions":[]}],
                    "entries": [EvidenceIndex(snap).entry(str(i)) for i in range(1, 6)]}
                n, _ = await model.count("batch", synthetic)
                if n >= target * .85:
                    break
            # First requests are only the two failed boundaries. Subsequent calls
            # test warm behavior and matched synthetic work, never new CSV rows.
            schedule = [(ROW_IDS[0], "first_observed"), (ROW_IDS[1], "first_observed"),
                        ("synthetic", "first_observed"), (ROW_IDS[0], "warm_repeat"),
                        (ROW_IDS[1], "warm_repeat"), ("synthetic", "warm_repeat")]
            if args.followup_id:
                schedule = [(rid,"read_45_full_batch") for rid in ["synthetic",*ROW_IDS]] + [
                    (rid,"batch_2_read_40") for rid in ["synthetic",*ROW_IDS]]
            for rid, order in schedule:
                payload = synthetic if rid == "synthetic" else data[rid]
                if order == "batch_2_read_40":
                    payload = {**payload,"entries":payload["entries"][:2]}
                policy["read"] = 45 if order == "read_45_full_batch" else None
                before = len(model.metrics)
                item = {"row_ref": rid, "order": order, "read_timeout":policy["read"] or rag.client.timeout.read,
                        "entry_count":len(payload["entries"]),"before": await sample(http, model.origin),
                        "gpu_before": await gpu_sample(), "telemetry": []}
                async def poll():
                    while True:
                        item["telemetry"].append(await sample(http, model.origin))
                        await asyncio.sleep(1)
                task = asyncio.create_task(poll())
                started = time.perf_counter()
                try:
                    await model.call("batch", payload, purpose="bounded_diagnosis")
                    item["status"] = "validated"
                except AuditError:
                    item["status"] = "failed"
                finally:
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
                item.update(duration_ms=round((time.perf_counter() - started) * 1000, 3),
                    metrics=model.metrics[before:], after=await sample(http, model.origin), gpu_after=await gpu_sample())
                report["experiments"].append(item)
                store.write(directory / "summary.json", report)
                print(json.dumps({"experiment":len(report["experiments"]),"row_ref":rid,"status":item["status"],
                    "categories":[m["failure_category"] for m in item["metrics"]],"dispatches":report["dispatches"],
                    "duration_ms":item["duration_ms"]}), flush=True)
        report["balanced_counters"] = rag.metrics_snapshot()
        report["completed"] = True
        if args.followup_id:
            report["followup_completed"] = True
        store.write(directory / "summary.json", report)
        print(json.dumps({"diagnostic_directory":str(directory),"dispatches":report["dispatches"]}))
    finally:
        if close:
            await close()
        await runner.aclose()


def canonical_sha256_file(path):
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run-id", required=True)
    p.add_argument("--confirmed-staging", action="store_true")
    p.add_argument("--followup-id", help="Append six predeclared single-variable comparisons; same global 12-dispatch cap.")
    args = p.parse_args()
    try:
        asyncio.run(run(args))
    except Exception:
        print('{"status":"failed","error_code":"boundary_diagnosis_failed"}', file=sys.stderr)
        raise SystemExit(2)
