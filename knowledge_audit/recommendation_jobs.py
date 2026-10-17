"""Existing tracked tasks, admission and global lease; no new infrastructure."""
import asyncio
import os
from knowledge_audit.privacy import AuditError
from knowledge_audit.recommendation_store import recommendation_versions
from knowledge_audit.failures import category


class RecommendationJobs:
    def __init__(self,store,coverage_jobs,runner,factory):
        self.store=store;self.coverage=coverage_jobs;self.runner=coverage_jobs.runner;self.factory=factory

    def start(self,rid,owner):
        self.store.owned(rid,owner)
        self.coverage.tasks.start(rid,lambda:self.work(rid,owner),operation_type='knowledge_recommendation')

    async def work(self,rid,owner):
        lease=None;engine=None;meta=None;results=None
        async with self.coverage.serial:
            try:
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
                engine=await self.factory(meta)
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
                    observations=await self.runner.run(self.store.observations,source['manifest'],row,owner)
                    results[row['source_row_id']]=await engine.draft(row,source['manifest'],observations)
                    await engine.model.discover()
                    if engine.model.serving!=meta['serving_identity']:raise AuditError('audit_serving_drift')
                    await self.runner.run(self.store.save_progress,rid,owner,meta,results)
                meta.update(state='completed',phase='finished')
            except asyncio.CancelledError:
                if meta is not None:
                    meta.update(state='cancelled',phase='cancelled')
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
                    if meta is not None:
                        await self.runner.run(self.store.finish,rid,owner,meta,results)
                finally:
                    try:
                        if engine is not None and hasattr(engine,'aclose'):await engine.aclose()
                    finally:
                        if lease is not None:os.close(lease)

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
    from knowledge_audit.runtime import confirm_staging
    from utils.performance_config import PERFORMANCE_SETTINGS
    confirm_staging(confirmed=True,model=True)
    settings,coverage_store,_=runtime(request)
    old=await request.app.state.blocking_runner.run(coverage_store.owned,'runs',meta['source_run_id'],meta['owner_id'])
    _,redactor=await request.app.state.blocking_runner.run(coverage_store.dataset,old['dataset_id'],meta['owner_id'])
    snapshot=await request.app.state.blocking_runner.run(coverage_store.snapshot,meta['snapshot_id'],meta['owner_id'])
    http=httpx.AsyncClient(timeout=PERFORMANCE_SETTINGS.vllm_http_read_timeout_seconds)
    try:
        rag=request.app.state.answering_service.agent_service.rag_system
        model=AuditModel(rag,http,os.environ['VLLM_URL'],settings,redactor,limiter=request.app.state.request_limiter,
            schemas=SCHEMAS,message_builder=messages,identity_fields={'related_faq_ids','equivalent_faq_ids','taxonomy_path_id'})
        await model.discover()
        model.metrics_path=store.path(meta['recommendation_revision_id'])/'model-metrics.jsonl'
        engine=RecommendationEngine(model,snapshot,redactor);engine.aclose=http.aclose
        return engine
    except BaseException:
        await http.aclose();raise
