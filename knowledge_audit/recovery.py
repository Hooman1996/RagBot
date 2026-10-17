"""Protected, hash-bound structured checkpoints and conservative dispatch journal.

A checkpoint replays validated structured data through the SAME local evidence
validators. It is not a proof merely because the schema is valid. No prompts,
raw responses or exception strings are persisted. Unknown remote work requires
an explicit operator choice; this is not exactly-once inference.
"""
from copy import deepcopy
import asyncio
import secrets

from knowledge_audit.privacy import AuditError, private_directory
from knowledge_audit.schemas import SCHEMAS
from utils.read_only_audit import canonical_sha256

VERSION = "audit-boundaries-1"
UNKNOWN = {"dispatched", "unknown", "preparation_unobserved", "retrieval_unobserved"}


class RowJournal:
    def __init__(self, store, meta, row, runner):
        self.store, self.meta, self.row, self.runner = store, meta, row, runner
        self.owner, self.rid = meta['owner_id'], meta['run_id']
        attempts = private_directory(store._path('runs', self.rid) / 'attempts')
        self.directory = private_directory(attempts / row['source_row_id'])
        self.binding = canonical_sha256({"run": self.rid, "row": row['source_row_id'],
            "input": meta['input_id'], "snapshot": meta['snapshot_id'], "identities": meta['run_identity_id'],
            "versions": meta['versions'], "policy": VERSION})
        self.current = None
        self.hits = 0

    def paths(self):
        return sorted(self.directory.glob('request_*.json'))

    def records(self):
        return [self.store.read(p) for p in self.paths()]

    def unknowns(self):
        return [r for r in self.records() if r['state'] in UNKNOWN]

    def key(self, kind, payload, phase):
        return canonical_sha256([self.binding, kind, phase, payload])

    def restored(self, key):
        for record in reversed(self.records()):
            if record['key'] != key:
                continue
            if record['binding'] != self.binding:
                raise AuditError('checkpoint_identity_mismatch')
            if record['state'] == 'validated':
                if canonical_sha256(record['result']) != record['result_sha256']:
                    raise AuditError('checkpoint_content_mismatch')
                self.hits += 1
                return deepcopy(record['result'])
        return None

    def begin(self, key, responsibility, entry_ids=()):
        # Authorization is attempt-specific; it never changes the original journal.
        if any(r['key'] == key and r['state'] in UNKNOWN for r in self.records()) and not self.meta.get('retry_unknown_authorized'):
            raise AuditError('unknown_remote_completion_requires_choice')
        from knowledge_audit.store import now
        record = {'request_id': 'request_' + secrets.token_hex(16), 'key': key, 'binding': self.binding,
                  'responsibility': responsibility, 'policy': VERSION, 'row_attempt': self.row['attempt_count'],
                  'created_at': now(), 'state': 'prepared', 'dispatches': 0, 'entry_ids': list(entry_ids),
                  'recovery_revision_id': self.meta.get('recovery_revision_id', '')}
        self.store.write(self.directory / (record['request_id'] + '.json'), record)
        self.current = record
        return record

    def update(self, **fields):
        self.current.update(fields)
        self.store.write(self.directory / (self.current['request_id'] + '.json'), self.current)

    async def event(self, state, metric=None):
        # Called BEFORE the SDK dispatch; failure to persist prevents dispatch.
        allowed = ('attempt', 'prompt_tokens', 'completion_tokens', 'finish_reason', 'failure_category',
                   'server_completion_state', 'phase_timings_ms', 'duration_ms', 'dispatched', 'schema_version', 'http_status', 'server_request_ref')
        fields = {k: metric[k] for k in allowed if metric and k in metric}
        if state == 'dispatched':
            fields['dispatches'] = self.current['dispatches'] + 1
        await self.runner.run(self.update, state=state, **fields)

    async def invoke(self, kind, payload, operation, *, phase='unknown', schema=None, precise=False):
        key = self.key(kind, payload, phase)
        restored = await self.runner.run(self.restored, key)
        if restored is not None:
            if schema is not None:
                try:
                    restored = schema.model_validate(restored).model_dump()
                except Exception:
                    raise AuditError('checkpoint_schema_mismatch') from None
            return restored
        entries = payload.get('data', {}).get('entries', []) if kind == 'batch' else []
        await self.runner.run(self.begin, key, kind, [e['chunk_id'] for e in entries])
        if not precise:
            # Preparation may call rewrite/embedding services internally. We do
            # not pretend its opaque boundary is a confirmed completion send.
            await self.event('preparation_unobserved' if kind == 'preparation' else 'retrieval_unobserved' if kind == 'retrieval' else 'dispatched')
        try:
            result = await operation()
            if schema is not None:
                result = schema.model_validate(result).model_dump()
            if kind == 'preparation' and (result.get('preparation_status') == 'failed' or result.get('rewrite_status') == 'fallback'):
                await self.event('preparation_unobserved')
                return result
            # Redaction already applies in AuditModel/QueryPreparer. Only the
            # typed structured result crosses this boundary, never response text.
            await self.runner.run(self.update, state='validated', result=result, result_sha256=canonical_sha256(result))
            return result
        except BaseException:
            if self.current['state'] in UNKNOWN:
                await self.event('unknown')
            elif self.current['state'] != 'response_received':
                await self.event('failed_before_dispatch')
            raise

    def archive_result(self, result):
        path = self.directory / ('row-attempt-' + str(self.row['attempt_count']) + '.json')
        if path.exists():
            raise AuditError('attempt_already_saved')
        self.store.write(path, {'binding': self.binding, 'attempt': self.row['attempt_count'],
                               'result_sha256': canonical_sha256(result), 'result': result})


class CheckpointModel:
    def __init__(self, model, journal):
        object.__setattr__(self, 'wrapped', model)
        object.__setattr__(self, 'journal', journal)
    def __getattr__(self, key):
        return getattr(self.wrapped, key)
    def __setattr__(self, key, value):
        setattr(self.wrapped, key, value)
    async def call(self, role, data, **kwargs):
        if getattr(self.wrapped, 'progress_callback', None):
            await self.wrapped.progress_callback(role)
        schemas = getattr(self.wrapped, 'schemas', SCHEMAS)
        precise = hasattr(self.wrapped, 'request_journal')
        if precise:
            self.wrapped.request_journal = self.journal.event
        return await self.journal.invoke(role, {'data': data, 'kwargs': kwargs},
            lambda: self.wrapped.call(role, data, **kwargs), phase=getattr(self.wrapped, 'evaluation_phase', 'unknown'),
            schema=schemas[role], precise=precise)


class CheckpointPreparer:
    def __init__(self, preparer, journal):
        self.preparer, self.journal = preparer, journal
    async def prepare(self, event, history, redactor, **kwargs):
        from dataclasses import asdict
        payload = {'event': asdict(event), 'history': history.before(event).provenance, 'options': kwargs}
        # Event/history data are hashed in memory; the saved journal holds only the digest.
        # Datetime requires the stable ISO representation.
        payload['event']['timestamp'] = event.timestamp.isoformat() if event.timestamp else None
        return await self.journal.invoke('preparation', payload,
            lambda: self.preparer.prepare(event, history, redactor, **kwargs))


def unknown_records(store, meta, row_id):
    directory = store._path('runs', meta['run_id']) / 'attempts' / row_id
    if not directory.exists():
        return []
    records = [store.read(p) for p in directory.glob('request_*.json')]
    return [r for r in records if r['state'] in UNKNOWN]


def journal_summary(store, meta, row_id):
    directory = store._path('runs', meta['run_id']) / 'attempts' / row_id
    if not directory.exists():
        return []
    allow = ('request_id', 'responsibility', 'state', 'row_attempt', 'dispatches', 'result_sha256',
             'failure_category', 'schema_version', 'prompt_tokens', 'completion_tokens', 'duration_ms', 'entry_ids', 'recovery_revision_id')
    return [{k: r[k] for k in allow if k in r} for r in
            (store.read(p) for p in sorted(directory.glob('request_*.json')))]


class CheckpointRetrieval:
    """Reuse the frozen selection, not fresh nondeterministic rerank membership.

    Live source/index checks still precede every restored selection and the final
    verdict. This is not a frozen live index or an assertion of retrieval recall.
    """
    def __init__(self, retrieval, journal, allowed_ids):
        self.wrapped, self.journal, self.allowed = retrieval, journal, set(allowed_ids)
    def __getattr__(self, key):
        return getattr(self.wrapped, key)
    async def fetch(self, query, **kwargs):
        await self.wrapped.check()
        before = len(self.wrapped.metrics)
        result = await self.journal.invoke('retrieval', {'query': query, 'options': kwargs},
                                            lambda: self.wrapped.fetch(query, **kwargs))
        candidates, selected = result.get('candidate_ids', []), result.get('selected_ids', [])
        if (len(candidates) != result.get('candidate_count') or len(set(candidates)) != len(candidates)
            or len(set(selected)) != len(selected) or not set(selected) <= set(candidates) <= self.allowed):
            raise AuditError('checkpoint_candidate_mismatch')
        if len(self.wrapped.metrics) == before:
            self.wrapped.metrics.append({**result, 'checkpoint_reused': True})
        return result


def dispatched_entries(records):
    return set(cid for record in records if record['responsibility']=='batch' and record.get('dispatches', 0)
               for cid in record.get('entry_ids', []))
