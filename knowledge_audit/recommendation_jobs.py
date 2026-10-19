"""Existing tracked tasks, admission and global lease; no new infrastructure."""
import asyncio
import os
from knowledge_audit.privacy import AuditError
from knowledge_audit.settings import require_coverage_enabled
from knowledge_audit.recommendation_store import recommendation_versions
from knowledge_audit.failures import category
from knowledge_audit.operations import Budget,Limits,OperationalPause,AuditAdmission
from utils.audit_dispatch import observe_audit
from knowledge_audit.retention import artifact_access


class RecommendationJobs:
    def __init__(self,store,coverage_jobs,runner,factory):
        self.store=store;self.coverage=coverage_jobs;self.runner=coverage_jobs.runner;self.factory=factory

    def start(self,rid,owner):
        require_coverage_enabled()
        self.store.owned(rid,owner)
        self.coverage.tasks.start(rid,lambda:self.work(rid,owner),operation_type='knowledge_recommendation')

    async def work(self,rid,owner):
        lease=None;engine=None;meta=None;results=None;budget=None;binding=None;access=None;deadline_monitor=None;elapsed_expired=False
        async with self.coverage.serial:
            try:
                access=artifact_access(self.store.store.root);access.__enter__()
                meta=await self.runner.run(self.store.owned,rid,owner)
                results=await self.runner.run(self.store.results,rid,owner)
                async def queued_check():
                    live=await self.runner.run(self.store.owned,rid,owner)
                    if live.get('cancel_requested'):raise asyncio.CancelledError()
                lease=await self.coverage.acquire_global(queued_check)
                # A competing worker may have completed/cancelled this revision
                # while we waited. Never replay its model work or final bytes.
                live=await self.runner.run(self.store.owned,rid,owner)
                if live['state']!='queued' or live.get('cancel_requested'):
                    meta=None
                    return
                meta=live
                results=await self.runner.run(self.store.results,rid,owner)
                if meta['versions']!=recommendation_versions():raise AuditError('audit_version_drift')
                source=await self.runner.run(self.store.source,rid,owner)
                if meta.get('operational_policy'):
                    budget=Budget(self.store.store,self.store.path(rid),owner,Limits.from_settings(meta['operational_settings'],recommendation=True),runner=self.runner)
                    await self.runner.run(budget.start);binding=observe_audit(budget);binding.__enter__()
                    remaining=budget.limits.execution_seconds-(await self.runner.run(budget.summary))['elapsed_seconds'];task=asyncio.current_task()
                    async def expire():
                        nonlocal elapsed_expired
                        await asyncio.sleep(max(0,remaining));elapsed_expired=True
                        if not task.cancelling():task.cancel()
                    deadline_monitor=asyncio.create_task(expire())
                engine=await self.factory(meta)
                if budget:budget.token_counter=getattr(engine.model,'count_completion_tokens',None)
                async def fresh_eligibility(row,source_meta):
                    return await self.runner.run(self.store.effective_eligibility,rid,owner,row)
                engine.eligibility_provider=fresh_eligibility
                meta.update(state='running',phase='starting',serving_identity=dict(engine.model.serving),runtime_settings=engine.model.settings.manifest())
                async def progress(role):
                    if (await self.runner.run(self.store.owned,rid,owner))['cancel_requested']:raise asyncio.CancelledError()
                    meta['phase']=role
                    await self.runner.run(self.store.save_progress,rid,owner,meta,results)
                engine.model.progress_callback=progress
                await self.runner.run(self.store.save_progress,rid,owner,meta,results)
                for row in source['rows']:
                    if row['source_row_id'] not in meta['selected_row_ids']:continue
                    if budget:budget.row_id=row['source_row_id']
                    observations=await self.runner.run(self.store.observations,source['manifest'],row,owner)
                    results[row['source_row_id']]=await engine.draft(row,source['manifest'],observations)
                    await engine.model.discover()
                    if engine.model.serving!=meta['serving_identity']:raise AuditError('audit_serving_drift')
                    await self.runner.run(self.store.save_progress,rid,owner,meta,results)
                meta.update(state='completed',phase='finished')
            except OperationalPause as pause:
                if meta is not None:meta.update(state='paused',phase='paused',pause_reason=str(pause),error_code=str(pause))
            except asyncio.CancelledError:
                if meta is not None:
                    meta.update(state='paused' if elapsed_expired else 'cancelled',phase='paused' if elapsed_expired else 'cancelled',pause_reason='budget_elapsed' if elapsed_expired else '')
                    for value in results.values():
                        if value['recommendation_status']=='pending':value.update(recommendation_status='interrupted',error_code='cancellation')
                raise
            except Exception as error:
                if meta is not None:
                    code=str(error) if isinstance(error,AuditError) and str(error) in {'audit_version_drift','audit_serving_drift','recommendation_source_drift','run_already_owned'} else category(error)
                    meta.update(state='failed',phase='failed',error_code=code)
                    for value in results.values():
                        if value['recommendation_status'] in {'pending','drafted'}:value.update(recommendation_status='error',error_code=code,recommendations=[])
            finally:
                try:
                    if deadline_monitor is not None:
                        deadline_monitor.cancel();await asyncio.gather(deadline_monitor,return_exceptions=True)
                    if budget:
                        try:await self.runner.run(budget.stop)
                        except Exception:pass
                    if binding:binding.__exit__(None,None,None)
                    if meta is not None:
                        if meta['state']=='paused':await self.runner.run(self.store.save_progress,rid,owner,meta,results)
                        else:await self.runner.run(self.store.finish,rid,owner,meta,results)
                finally:
                    try:
                        if engine is not None and hasattr(engine,'aclose'):await engine.aclose()
                    finally:
                        if lease is not None:os.close(lease)
                        if access is not None:access.__exit__(None,None,None)

    async def cancel(self,rid,owner):
        meta=self.store.owned(rid,owner)
        if meta['state'] not in {'queued','running'}:raise AuditError('recommendation_not_active')
        # Keep state mutation inside the new artifact lock, never coverage files.
        with self.store.lock(rid):
            live=self.store.owned(rid,owner);live['cancel_requested']=True
            self.store.store.write(self.store.path(rid)/'meta.json',live)
        await self.coverage.tasks.cancel(rid)
        if not (self.store.path(rid)/'results.final.json').exists():
            meta=self.store.owned(rid,owner);results=self.store.results(rid,owner)
            meta.update(state='cancelled',phase='cancelled')
            for value in results.values():
                if value['recommendation_status']=='pending':value.update(recommendation_status='interrupted',error_code='cancellation')
            self.store.finish(rid,owner,meta,results)


async def build_recommendation_engine(request,store,meta):
    import httpx
    from knowledge_audit.api import runtime
    from knowledge_audit.model import AuditModel
    from knowledge_audit.recommendations import RecommendationEngine
    from knowledge_audit.recommendation_schemas import SCHEMAS
    from knowledge_audit.recommendation_prompts import messages
    from knowledge_audit.runtime import confirm_live_run
    from utils.performance_config import PERFORMANCE_SETTINGS
    confirm_live_run(confirmed=True,model=True)
    settings,coverage_store,_=runtime(request)
    if meta.get("operational_policy") and settings.manifest()!=meta["operational_settings"]:raise AuditError("audit_runtime_identity_drift")
    old=await request.app.state.blocking_runner.run(coverage_store.owned,'runs',meta['source_run_id'],meta['owner_id'])
    _,redactor=await request.app.state.blocking_runner.run(coverage_store.dataset,old['dataset_id'],meta['owner_id'])
    snapshot=await request.app.state.blocking_runner.run(coverage_store.snapshot,meta['snapshot_id'],meta['owner_id'])
    http=httpx.AsyncClient(timeout=PERFORMANCE_SETTINGS.vllm_http_read_timeout_seconds)
    try:
        rag=request.app.state.answering_service.agent_service.rag_system
        model=AuditModel(rag,http,os.environ['VLLM_URL'],settings,redactor,limiter=AuditAdmission(request.app.state.request_limiter,settings.operational_limits.pace_ms),
            schemas=SCHEMAS,message_builder=messages,identity_fields={'related_faq_ids','equivalent_faq_ids','taxonomy_path_id'})
        await model.discover()
        model.metrics_path=store.path(meta['recommendation_revision_id'])/'model-metrics.jsonl'
        engine=RecommendationEngine(model,snapshot,redactor);engine.aclose=http.aclose
        return engine
    except BaseException:
        await http.aclose();raise
