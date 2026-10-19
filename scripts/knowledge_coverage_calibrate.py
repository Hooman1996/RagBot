#!/usr/bin/env python3
"""One bounded controlled A3 campaign; no customer audit or shared index writes."""
import argparse
import asyncio
from dataclasses import replace
import hashlib
import json
import logging
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


async def run(args):
    logging.disable(logging.CRITICAL)
    from knowledge_audit.settings import load_coverage_settings
    from knowledge_audit.store import CoverageStore, now
    from knowledge_audit.privacy import AuditError, Redactor, private_json
    from knowledge_audit.calibration import (load_inputs, snapshot_variant, input_dataset, ControlledCandidates,
        CalibrationArtifacts, CampaignBudget, FrozenResponsibilities)
    from utils.read_only_audit import canonical_sha256
    settings = load_coverage_settings()
    if getattr(args,"owner_id",0) < 0:
        raise AuditError("invalid_calibration_owner")
    store = CoverageStore(settings.artifact_dir)
    if args.command in {"human-template","human-import"}:
        from knowledge_audit.human_labels import template, import_labels
        if args.command == "human-template":
            from knowledge_audit.privacy import private_directory
            directory=private_directory(store.root / "human-label-templates")
            name=args.package_id+".json"
            private_json(directory / name,template(store,args.package_id))
            print(json.dumps({"template_path":str(directory / name),"status":"not_reviewed"}))
        else:
            body=store.read(args.labels)
            print(json.dumps(import_labels(store,args.package_id,body),sort_keys=True))
        return 0
    from knowledge_audit.runtime import confirm_live_run, live_components, configuration_identity, serving_identity, code_identity
    from knowledge_audit.inputs import TimestampPolicy
    from knowledge_audit.preparation import QueryPreparer
    from knowledge_audit.pipeline import CoverageEvaluator
    from knowledge_audit.model import AuditModel
    from knowledge_audit.prompts import prompt_identity
    from utils.concurrency import BoundedBlockingRunner, AdmissionLimiter
    import httpx
    confirm_live_run(confirmed=args.confirmed,model=True)
    spec, lock = load_inputs()
    artifacts=CalibrationArtifacts(store)
    lease=store.global_lease()
    runner=BoundedBlockingRunner(1)
    rag=None
    rows=[];meta=None;usage=[];wire_dispatches=0
    started=time.perf_counter()
    try:
        budget=CampaignBudget(store,artifacts.root)
        if budget.state["used"]:
            raise AuditError("a3_campaign_already_dispatched_no_automatic_rerun")
        selection=[(i,2,"") for i in spec["live_selection"]]+[(i,5,i+":2") for i in spec["batch_comparisons"]]
        meta=artifacts.create(args.owner_id,settings.manifest(),lock,[{"case_id":i,"batch_max_entries":cap} for i,cap,_ in selection])
        meta["configuration_variants"]={str(cap):replace(settings,batch_max_entries=cap).manifest() for cap in (2,5)}
        path=artifacts.path(meta["calibration_id"])
        redactor=Redactor(b"fictional-a3-calibration-only-key-12345678")
        cases={c["case_id"]:c for c in spec["cases"]}
        snapshots={}
        for ordinal,(case_id,cap,comparison) in enumerate(selection,1):
            case=cases[case_id];baseline,snapshot=snapshot_variant(spec,case)
            snapshots[baseline["snapshot_id"]]=baseline;snapshots[snapshot["snapshot_id"]]=snapshot
            rows.append({"source_row_id":"row_"+canonical_sha256([lock,case_id,cap])[:32],"case_id":case_id,
                "source_record_ordinal":ordinal,"comparison_of":comparison,"batch_max_entries":cap,"query":case["query"],
                "snapshot_id":snapshot["snapshot_id"],"baseline_snapshot_id":baseline["snapshot_id"],
                "removed_ids":case["removed_ids"],"state":"unexecuted"})
            rows[-1]["configuration_id"]=canonical_sha256(meta["configuration_variants"][str(cap)])
        private_json(path / "fixture-snapshots.json",snapshots)
        store.write(path / "rows.json",rows)
        async with httpx.AsyncClient(timeout=40) as http:
            rag,rewriter,classifier=await live_components(runner,http)
            if rag.client.max_retries != 0:
                raise AuditError("calibration_network_retries_forbidden")
            async def dispatched(request):
                nonlocal wire_dispatches
                if request.url.path.endswith("/chat/completions"):
                    wire_dispatches+=1
            rag.client._client.event_hooks["request"].append(dispatched)
            completion=rag._completion
            async def guarded(**kwargs):
                budget.reserve()
                value=await completion(**kwargs)
                usage.append({"prompt_tokens":value.usage.prompt_tokens,"completion_tokens":value.usage.completion_tokens})
                return value
            rag._completion=guarded
            model=AuditModel(rag,http,os.environ["VLLM_URL"],settings,redactor,limiter=AdmissionLimiter(1,name="calibration"))
            model.metrics_path=path / "model-metrics.jsonl"
            await model.discover()
            try:
                capability=await model.check_schema_support()
            except AuditError:
                capability={"status":"probe_failed_local_validation_still_required",
                    "failure_categories":[m.get("failure_category") for m in model.metrics if m["status"]!="validated"]}
                if any(m.get("failure_category") in {"model_http_rejection","model_connection_failure","model_service_failure"} for m in model.metrics):
                    raise AuditError("calibration_serving_unavailable")
            identities={"generation":model.serving,"serving":await serving_identity(http,redactor),
                "runtime":configuration_identity(TimestampPolicy(),12,redactor),"settings":settings.manifest(),
                "fixture_lock":lock,"code":code_identity(),"prompt_schema_identity":prompt_identity(),
                "configuration_variants":meta["configuration_variants"],"selection":meta["selection"],
                "operator_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
            meta.update(state="running",run_identities=identities,run_identity_id=canonical_sha256(identities),
                identity_captured_at=now(),capability=capability)
            store.write(path / "meta.json",meta)
            preparer=QueryPreparer(rag.search_engine.processor,runner,rewriter,classifier)
            baseline_results={}
            for row in rows:
                if budget.state["used"] >= 120:
                    row["error_code"]="a3_dispatch_budget_exhausted";continue
                case=cases[row["case_id"]]
                selected_model=model
                if row["comparison_of"]:
                    frozen=baseline_results.get(row["case_id"],{})
                    if "scope_decision" not in frozen or "aspect_checklist" not in frozen:
                        row["error_code"]="comparison_inputs_unavailable";continue
                    selected_model=FrozenResponsibilities(model,frozen)
                    row["frozen_scope_aspects_sha256"]=canonical_sha256([frozen["scope_decision"],frozen["aspect_checklist"]])
                dataset=input_dataset(case,redactor)
                snapshot=snapshots[row["snapshot_id"]]
                engine=CoverageEvaluator(snapshot=snapshot,model=selected_model,retrieval=ControlledCandidates(snapshot,case,initial_depth=settings.initial_depth),
                    preparer=preparer,redactor=redactor,dataset=dataset,batch_max_entries=row["batch_max_entries"],entry_budget=settings.max_entry_budget,
                    initial_depth=settings.initial_depth,broader_depth=settings.broader_depth,max_entry_budget=settings.max_entry_budget)
                row["prediction"]=await engine.evaluate(dataset.selected[0],{})
                row["state"]="error" if row["prediction"]["outcome"]=="error" else "completed"
                if not row["comparison_of"]:
                    baseline_results[row["case_id"]]=row["prediction"]
                else:
                    old=baseline_results[row["case_id"]];new=row["prediction"]
                    row["comparison_inputs_equal"]={k:old.get(k)==new.get(k) for k in
                        ("standalone_query_redacted","canonical_retrieval_query_redacted","requested_aspects","scope_decision")}
                await model.discover()
                if model.serving != identities["generation"] or await serving_identity(http,redactor) != identities["serving"]:
                    meta["state"]="incompatible";break
                store.write(path / "rows.json",rows)
                meta["processed_records"]=sum(r["state"]!="unexecuted" for r in rows)
                store.write(path / "meta.json",meta)
                print(json.dumps({"case_id":row["case_id"],"batch_max_entries":row["batch_max_entries"],
                    "state":row["state"],"dispatches":budget.state["used"]}),flush=True)
            # Only now load hidden labels. None of their content entered model
            # inputs, scope/aspects, candidate order, or batch-size comparisons.
            from knowledge_audit.calibration_scores import load_labels,score
            meta["summary"]=score(rows,load_labels(lock))
            meta.update(state="completed" if meta["state"]!="incompatible" else "incompatible",finished_at=now(),
                dispatches=budget.state["used"],blocked_dispatches=budget.state["blocked"],returned_completions=len(usage),
                actual_http_dispatches=wire_dispatches,unknown_server_usage_dispatches=wire_dispatches-len(usage),
                duration_ms=round((time.perf_counter()-started)*1000),
                reported_usage={k:sum(u[k] for u in usage) for k in ("prompt_tokens","completion_tokens")},
                model_status_counts={status:sum(m["status"]==status for m in model.metrics) for status in {m["status"] for m in model.metrics}})
            store.write(path / "rows.json",rows)
            store.write(path / "meta.json",meta)
            artifacts.freeze(meta,rows)
            print(json.dumps({"calibration_id":meta["calibration_id"],"dispatches":meta["dispatches"],"summary":meta["summary"]},sort_keys=True))
    except BaseException:
        if meta:
            meta.update(state="interrupted",finished_at=now(),dispatches=budget.state["used"],
                actual_http_dispatches=wire_dispatches,returned_completions=len(usage),
                unknown_server_usage_dispatches=wire_dispatches-len(usage))
            store.write(artifacts.path(meta["calibration_id"]) / "rows.json",rows)
            store.write(artifacts.path(meta["calibration_id"]) / "meta.json",meta)
            if not (artifacts.path(meta["calibration_id"]) / "evidence.manifest.json").exists():
                artifacts.freeze(meta,rows)
        raise
    finally:
        if rag:await rag.aclose()
        await runner.aclose()
        os.close(lease)
    return 0


def main():
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env", override=False)
    from knowledge_audit.settings import require_coverage_enabled
    from knowledge_audit.privacy import AuditError
    try:
        require_coverage_enabled()
    except AuditError as error:
        print(str(error), file=sys.stderr)
        return 2
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest="command",required=True)
    live=sub.add_parser("run");live.add_argument("--confirmed",action="store_true",dest="confirmed",help="confirm live audit work against the configured services");live.add_argument("--confirmed-staging",action="store_true",dest="confirmed",help=argparse.SUPPRESS)
    live.add_argument("--owner-id",type=int,default=0,help="Explicit existing owner; does not grant web access. Default operator namespace 0.")
    for name in ("human-template","human-import"):
        child=sub.add_parser(name);child.add_argument("--package-id",required=True)
        if name=="human-import":child.add_argument("--labels",type=Path,required=True)
    try:raise SystemExit(asyncio.run(run(p.parse_args())))
    except AuditError as error:
        print(str(error), file=sys.stderr)
        return 2
    except Exception:
        print('{"status":"failed","error_code":"calibration_operator_failed"}',file=sys.stderr)
        raise SystemExit(2)


if __name__ == "__main__":
    raise SystemExit(main())
