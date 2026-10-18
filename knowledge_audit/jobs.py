"""Explicit file-backed execution, cooperative cancellation and durable recovery."""
from __future__ import annotations
import asyncio
import copy
import os
import secrets

from mass_answer_jobs import MassAnswerJobManager
from knowledge_audit.privacy import AuditError
from knowledge_audit.settings import require_coverage_enabled
from knowledge_audit.prompts import prompt_identity
from knowledge_audit.runtime import code_identity
from knowledge_audit.execution import VERSION, TERMINAL, attempt_seed
from knowledge_audit.recovery import RowJournal, CheckpointModel, CheckpointPreparer, unknown_records, journal_summary, CheckpointRetrieval, dispatched_entries
from utils.read_only_audit import canonical_sha256
from knowledge_audit.operations import Budget, Limits, OperationalPause
from utils.audit_dispatch import observe_audit
from knowledge_audit.retention import artifact_access


def versions():
    code = code_identity()
    return {"prompts": prompt_identity(), "code": code, "code_id": canonical_sha256(code)}


class CoverageJobs:
    def __init__(self, store, factory, runner, *, access_guard=None):
        from knowledge_audit.durable_io import DurableIO
        self.store, self.factory, self.runner = store, factory, DurableIO(runner)
        self.tasks = MassAnswerJobManager()
        self.serial = asyncio.Semaphore(1)
        self.closing = False
        self.access_guard = access_guard

    def start(self, rid, owner):
        require_coverage_enabled()
        meta = self.store.owned('runs', rid, owner)
        if rid in self.tasks.active_job_ids or meta['state'] != 'queued' or meta.get('cancel_requested'):
            return
        self.tasks.start(rid, lambda: self.work(rid, owner), operation_type='knowledge_coverage')

    async def progress(self, rid, owner, stage):
        live = await self.runner.run(self.store.owned, 'runs', rid, owner)
        if live.get('cancel_requested'):
            raise asyncio.CancelledError()
        if self.access_guard and not await self.access_guard(owner):
            raise AuditError('audit_access_revoked')
        await self.runner.run(self.store.update_run, rid, owner, {'stage': stage})

    async def acquire_global(self, check):
        while True:
            await check()
            try:
                return await self.runner.run(self.store.global_lease)
            except AuditError as error:
                if str(error) != 'run_already_owned':
                    raise
                await asyncio.sleep(0.1)  # queued, cancellable; no busy/failed inference

    def check_versions(self, meta):
        current = versions()
        if current['prompts'] != meta['versions']['prompts'] or current['code']['file_sha256'] != meta['versions']['code']['file_sha256']:
            raise AuditError('audit_version_drift')

    async def work(self, rid, owner):
        lease = global_lease = engine = active = journal = monitor = budget = binding = access = deadline_monitor = None
        elapsed_expired = False
        async with self.serial:
            try:
                access=artifact_access(self.store.root);access.__enter__()
                lease = await self.runner.run(self.store.lease, rid)
                task = asyncio.current_task()
                async def watch_cancel():
                    while True:
                        await asyncio.sleep(0.1)
                        live = await self.runner.run(self.store.owned, 'runs', rid, owner)
                        if live.get('cancel_requested'):
                            # Local cancellation may already be persisting the
                            # interruption. Do not interrupt that cleanup again.
                            if not task.cancelling():
                                task.cancel()
                            return
                monitor = asyncio.create_task(watch_cancel(), name='coverage-cancellation-watch')
                meta = await self.runner.run(self.store.owned, 'runs', rid, owner)
                if meta['state'] != 'queued':
                    return
                self.check_versions(meta)
                await self.progress(rid, owner, 'waiting_for_worker')
                global_lease = await self.acquire_global(lambda: self.progress(rid, owner, 'waiting_for_worker'))
                await self.progress(rid, owner, 'identity_check')
                if meta.get('operational_policy'):
                    budget=Budget(self.store,self.store._path('runs',rid),owner,Limits.from_settings(meta['settings']),runner=self.runner)
                    await self.runner.run(budget.start);binding=observe_audit(budget);binding.__enter__()
                    remaining=budget.limits.execution_seconds-(await self.runner.run(budget.summary))['elapsed_seconds']
                    async def expire_run():
                        nonlocal elapsed_expired
                        await asyncio.sleep(max(0,remaining));elapsed_expired=True
                        if not task.cancelling():task.cancel()
                    deadline_monitor=asyncio.create_task(expire_run(),name='coverage-elapsed-budget-watch')
                engine = await self.factory(meta)
                if budget:
                    budget.token_counter=getattr(engine.model,'count_completion_tokens',None)
                observed = {'serving': copy.deepcopy(engine.model.serving),
                    'runtime_configuration': copy.deepcopy(getattr(engine, 'runtime_configuration', {'status': 'unavailable'})),
                    'audit_settings': copy.deepcopy(meta['settings'])}
                pinned = meta.get('run_identities')
                if pinned is not None and pinned != observed:
                    raise AuditError('audit_runtime_identity_drift')
                if pinned is None:
                    if meta['attempt'] and any(r['attempt_count'] for r in await self.runner.run(self.store.rows, rid, owner)):
                        raise AuditError('audit_identity_unpinned')
                    from knowledge_audit.store import now
                    meta.update(run_identities=observed, run_identity_id=canonical_sha256(observed), run_identity_captured_at=now(),
                        configuration_id=canonical_sha256({'audit_settings': observed['audit_settings'], 'runtime_configuration': observed['runtime_configuration']}))
                    meta['versions'].update(serving=observed['serving'], runtime_configuration=observed['runtime_configuration'])
                meta.update(state='running', attempt=meta['attempt'] + 1, error_code='')
                await self.save_meta(meta)
                # Reconcile once at attempt start, not on each progress poll.
                await self.runner.run(self.store.progress, rid, owner, reconcile=True)
                base_model = engine.model
                base_preparer = getattr(engine, 'preparer', None)
                base_retrieval = getattr(engine, 'retrieval', None)
                allowed_ids = list(engine.index.records) if hasattr(engine, 'index') else []
                async def callback(stage):
                    await self.progress(rid, owner, stage)
                    if budget:await self.runner.run(budget.check)
                base_model.progress_callback = callback
                events = {e.source_row_id: e for e in engine.dataset.selected}
                for row_id in meta.get('processing_row_ids', meta['selected_row_ids']):
                    await callback('preparation')
                    row = await self.runner.run(self.store.row, rid, row_id, owner)
                    # Failed rows are terminal for an ordinary start. Only explicit recovery
                    # places them back in pending; completed rows are never reset.
                    if row['processing_status'] in TERMINAL:
                        continue
                    if row_id in meta.get('skip_unknown_row_ids', []):
                        continue
                    active = row_id
                    if budget:budget.row_id=row_id
                    row = attempt_seed(row)
                    row.update(processing_status='running', coverage_status='not_evaluated', outcome='pending',
                               stopping_reason='preparation', attempt_count=row['attempt_count'] + 1)
                    await self.runner.run(self.store.save_row, rid, row, owner)
                    meta.update(active_row_id=row_id, stage='preparation')
                    await self.save_meta(meta)
                    journal = await self.runner.run(RowJournal, self.store, meta, row, self.runner)
                    engine.model = CheckpointModel(base_model, journal)
                    engine.prior_evaluated_entry_ids = await self.runner.run(lambda: dispatched_entries(journal.records()))
                    if base_retrieval is not None:
                        engine.retrieval = CheckpointRetrieval(base_retrieval, journal, allowed_ids)
                    if base_preparer is not None:
                        engine.preparer = CheckpointPreparer(base_preparer, journal)
                    result = await engine.evaluate(events[row_id], row)
                    if budget:await self.runner.run(budget.check)
                    result.update(attempt_count=row['attempt_count'], run_identity_id=meta['run_identity_id'],
                                  checkpoint_reuse_count=journal.hits,
                                  unknown_completion_count=len(await self.runner.run(journal.unknowns)))
                    prior_ids = await self.runner.run(lambda: dispatched_entries(journal.records()))
                    result['evaluated_entry_ids'] = sorted(prior_ids | set(result.get('evaluated_entry_ids', [])))
                    result['evaluated_entry_count'] = len(result['evaluated_entry_ids'])
                    result['entry_model_dispatched'] = bool(prior_ids)
                    result['model_evaluated'] = bool(row.get('model_evaluated')) or any(status=='validated' for status in result.get('question_evidence', {}).get('entry_status', {}).values())
                    result['request_journal'] = await self.runner.run(journal_summary, self.store, meta, row_id)
                    result['validated_checkpoint_count'] = sum(r['state']=='validated' for r in result['request_journal'])
                    if result.get('stopping_reason') == 'snapshot_mismatch':
                        raise AuditError('source_or_index_drift')
                    await callback('identity_check')
                    await base_model.discover()
                    if base_model.serving != observed['serving']:
                        raise AuditError('audit_serving_drift')
                    if hasattr(engine, 'observe_identities') and await engine.observe_identities() != observed:
                        raise AuditError('audit_runtime_identity_drift')
                    validated_ids = {cid for cid, status in result.get('question_evidence', {}).get('entry_status', {}).items() if status == 'validated'}
                    if result.get('outcome') in {'possible_gap', 'possible_partial_gap'} and prior_ids - validated_ids:
                        result.update(processing_status='needs_review', coverage_status='uncertain', outcome='needs_review',
                                      stopping_reason='retained_evaluation_unresolved')
                        result['review_codes'] = list(dict.fromkeys(result.get('review_codes', []) + ['retained_evaluation_unresolved']))
                    await self.runner.run(journal.archive_result, result)
                    await self.runner.run(self.store.save_row, rid, result, owner)
                    active = None
                    counters = await self.runner.run(self.store.progress, rid, owner)
                    await self.runner.run(self.store.update_run, rid, owner, {'processed_rows': counters['processed_rows'], **({'completed_pilot_rows': counters['processed_rows']} if meta.get('execution_mode', 'pilot')=='pilot' else {})})
                    journal = None
                counters = await self.runner.run(self.store.progress, rid, owner)
                state = 'interrupted' if counters['pending_rows'] else 'completed'
                await self.runner.run(self.store.update_run, rid, owner, {'state': state, 'stage': 'finished' if state == 'completed' else 'recovery_needed',
                    'active_row_id': '', 'processed_rows': counters['processed_rows'],
                    **({'completed_pilot_rows': counters['processed_rows']} if meta.get('execution_mode', 'pilot')=='pilot' else {}),
                    'completion_quality': 'incomplete' if counters['pending_rows'] else 'finished_with_errors' if counters['selected_outcome_counts'].get('error') else 'finished_requires_review',
                    'retry_unknown_authorized': False})
            except OperationalPause as pause:
                if lease is not None:
                    await self.interrupt(rid,owner,active,'paused',str(pause))
            except asyncio.CancelledError:
                if lease is not None:
                    await self.interrupt(rid,owner,active,'paused' if elapsed_expired else 'interrupted' if self.closing else 'cancelled','budget_elapsed' if elapsed_expired else '')
                raise
            except AuditError as exc:
                if lease is not None:
                    if str(exc) in {'source_or_index_drift', 'audit_serving_drift', 'audit_version_drift', 'audit_runtime_identity_drift', 'audit_identity_unpinned', 'snapshot_identity_mismatch', 'input_artifact_drift', 'candidate_snapshot_mismatch'}:
                        await self.invalidate(rid, owner, str(exc))
                    else:
                        await self.interrupt(rid, owner, active, 'failed', str(exc) if str(exc) in {'coverage_disabled', 'coverage_enabled_in_production', 'reranker_capability_unavailable', 'budget_ledger_missing', 'audit_access_revoked', 'checkpoint_identity_mismatch', 'checkpoint_content_mismatch', 'unknown_remote_completion_requires_choice', 'invalid_conflict_identity'} else 'audit_failed')
            except Exception:
                if lease is not None:
                    await self.interrupt(rid, owner, active, 'failed', 'checkpoint_or_worker_failure')
            finally:
                try:
                    if deadline_monitor is not None:
                        deadline_monitor.cancel();await asyncio.gather(deadline_monitor,return_exceptions=True)
                    if monitor is not None:
                        monitor.cancel()
                        await asyncio.gather(monitor, return_exceptions=True)
                    try:
                        if budget is not None:
                            try:await self.runner.run(budget.stop)
                            except Exception:
                                # A failed final ledger write leaves its active
                                # interval conservatively charged on restart.
                                pass
                    finally:
                        if binding is not None:binding.__exit__(None,None,None)
                        if engine is not None and hasattr(engine,'aclose'):
                            await engine.aclose()
                finally:
                    if lease is not None:os.close(lease)
                    if global_lease is not None:os.close(global_lease)
                    if access is not None:access.__exit__(None,None,None)

    async def save_meta(self, meta):
        from knowledge_audit.store import now
        # Counters belong to the progress index, not a stale worker's copy.
        payload = {k: v for k, v in meta.items() if k not in {'completed_pilot_rows', 'processed_rows'}}
        await self.runner.run(self.store.update_run, meta['run_id'], meta['owner_id'], {**payload, 'updated_at': now()})

    async def interrupt(self, rid, owner, active, state, code=''):
        meta = await self.runner.run(self.store.owned, 'runs', rid, owner)
        if active:
            row = await self.runner.run(self.store.row, rid, active, owner)
            # Completed authoritative rows survive a later metadata/disk failure.
            if row['processing_status'] == 'running':
                unknown = await self.runner.run(unknown_records, self.store, meta, active)
                row['request_journal'] = await self.runner.run(journal_summary, self.store, meta, active)
                row['validated_checkpoint_count'] = sum(r['state']=='validated' for r in row['request_journal'])
                row.update(processing_status='cancelled' if state == 'cancelled' else 'interrupted',
                    coverage_status='not_evaluated', production_reachability='unknown', outcome='pending', stopping_reason=state,
                    unknown_completion_count=len(unknown))
                await self.runner.run(self.store.save_row, rid, row, owner)
                directory = self.store._path('runs', rid) / 'attempts' / active
                if directory.exists():
                    await self.runner.run(self.store.write, directory / ('row-attempt-' + str(row['attempt_count']) + '-interruption-' + secrets.token_hex(8) + '.json'), {'result': row, 'interrupted': True})
        await self.runner.run(self.store.update_run, rid, owner, {'state': state, 'active_row_id': '', 'stage': state, 'error_code': code,
                                                                 'retry_unknown_authorized': False, 'pause_reason': code if state=='paused' else ''})

    async def invalidate(self, rid, owner, code):
        meta = await self.runner.run(self.store.owned, 'runs', rid, owner)
        for row_id in meta['selected_row_ids']:
            row = await self.runner.run(self.store.row, rid, row_id, owner)
            if row['processing_status'] != 'pending':
                row.update(processing_status='needs_review', coverage_status='uncertain', outcome='needs_review',
                           stopping_reason='snapshot_mismatch', evidence_visibility='snapshot_mismatch')
                await self.runner.run(self.store.save_row, rid, row, owner)
        await self.runner.run(self.store.update_run, rid, owner, {'state': 'incompatible', 'error_code': code, 'active_row_id': '', 'stage': 'review'})

    async def recover(self, rid, owner, *, unknown_policy='stop'):
        if unknown_policy not in {'stop', 'skip_unknown', 'retry_unknown'}:
            raise AuditError('invalid_recovery_choice')
        lease = await self.runner.run(self.store.lease, rid)
        try:
            meta = await self.runner.run(self.store.owned, 'runs', rid, owner)
            if meta.get('execution_version') != VERSION or meta['state'] == 'incompatible':
                raise AuditError('incompatible_run')
            self.check_versions(meta)
            if meta['state'] in {'queued', 'running'} and rid in self.tasks.active_job_ids:
                return
            budget_unknown_rows=[]
            if meta.get('operational_policy'):
                budget=Budget(self.store,self.store._path('runs',rid),owner,Limits.from_settings(meta['settings']),runner=self.runner)
                # Explicit choice retains every conservative charge; no allowance reset.
                try:await self.runner.run(budget.check,allow_unknown=unknown_policy in {'retry_unknown','skip_unknown'})
                except OperationalPause as pause:raise AuditError('unknown_remote_completion_requires_choice' if str(pause)=='unknown_remote_completion' else str(pause)) from None
                summary=await self.runner.run(budget.summary)
                if not summary['remaining_completions'] or not summary['remaining_tokens']:
                    raise AuditError('budget_new_run_required')
                budget_unknown_rows=await self.runner.run(budget.unknown_row_ids)
            unknown_rows = []
            for row_id in meta['selected_row_ids']:
                if row_id in budget_unknown_rows or await self.runner.run(unknown_records, self.store, meta, row_id):
                    row = await self.runner.run(self.store.row, rid, row_id, owner)
                    if row['processing_status'] not in TERMINAL - {'failed'}:
                        unknown_rows.append(row_id)
            if unknown_rows and unknown_policy == 'stop':
                raise AuditError('unknown_remote_completion_requires_choice')
            for row_id in meta['selected_row_ids']:
                row = await self.runner.run(self.store.row, rid, row_id, owner)
                if row['processing_status'] in {'failed', 'interrupted', 'cancelled', 'running'} and not (unknown_policy == 'skip_unknown' and row_id in unknown_rows):
                    row = attempt_seed(row)
                    row.update(processing_status='pending', coverage_status='not_evaluated', outcome='pending', stopping_reason='explicit_recovery')
                    await self.runner.run(self.store.save_row, rid, row, owner)
            from knowledge_audit.privacy import private_directory
            from knowledge_audit.store import now
            choices = await self.runner.run(private_directory, self.store._path('runs', rid) / 'recovery-choices')
            choice_id = 'recovery_' + secrets.token_hex(16)
            await self.runner.run(self.store.write, choices / (choice_id + '.json'), {'revision_id': choice_id, 'owner_id': owner,
                'policy': unknown_policy, 'unknown_row_ids': unknown_rows, 'created_at': now(),
                'run_identity_id': meta.get('run_identity_id', ''), 'before_attempt': meta['attempt'] + 1})
            if meta.get('operational_policy') and unknown_policy in {'retry_unknown','skip_unknown'}:
                await self.runner.run(budget.acknowledge_unknown,choice_id)
            await self.runner.run(self.store.update_run, rid, owner, {'state': 'queued', 'stage': 'waiting', 'active_row_id': '',
                'recovery_revision_id': choice_id,
                'cancel_requested': False, 'retry_unknown_authorized': unknown_policy == 'retry_unknown',
                'skip_unknown_row_ids': unknown_rows if unknown_policy == 'skip_unknown' else [],
                'recovery_choice': unknown_policy}, False)
        finally:
            os.close(lease)
        self.start(rid, owner)

    async def inspect_state(self, rid, owner):
        meta = await self.runner.run(self.store.owned, 'runs', rid, owner)
        if not meta.get('execution_version'):
            return meta
        if rid not in self.tasks.active_job_ids and (meta['state']=='running' or meta['state']=='cancelled' and meta.get('active_row_id') or meta['state']=='queued' and meta.get('stage')=='waiting_for_worker'):
            try:
                lease = await self.runner.run(self.store.lease, rid)
            except AuditError:
                return meta
            try:
                current = await self.runner.run(self.store.owned, 'runs', rid, owner)
                if current['state'] in {'running', 'queued', 'cancelled'}:
                    await self.interrupt(rid, owner, current.get('active_row_id') or None, 'cancelled' if current.get('cancel_requested') else 'interrupted')
                    await self.runner.run(self.store.progress, rid, owner, reconcile=True)
                    meta = await self.runner.run(self.store.owned, 'runs', rid, owner)
            finally:
                os.close(lease)
        return meta

    async def cancel(self, rid, owner):
        meta = await self.runner.run(self.store.owned, 'runs', rid, owner)
        if meta['state'] not in {'running', 'queued'}:
            raise AuditError('run_not_active')
        await self.runner.run(self.store.update_run, rid, owner, {'cancel_requested': True, 'state': 'cancelled', 'stage': 'cancelled'})
        task = self.tasks._tasks.get(rid)
        if task is not None:
            task.cancel()
            await asyncio.wait({task}, timeout=1.0)  # bounded HTTP-facing wait; durable cancellation already persisted

    async def aclose(self):
        self.closing = True
        await self.tasks.aclose()
