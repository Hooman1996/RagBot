"""Durable, finite allowance ledger. No prompts, responses or exception values."""
from contextlib import contextmanager
from dataclasses import asdict,dataclass
import asyncio
import fcntl
import os
import secrets
import shutil
import time

from knowledge_audit.privacy import AuditError
from utils.read_only_audit import canonical_sha256
from knowledge_audit.failures import category, TRANSPORT_CODES, VALIDATION_CODES
SAFE_ERRORS=TRANSPORT_CODES|VALIDATION_CODES|{"none","cancellation","audit_failed","schema_validation","output_length","citation_validation","semantic_validation"}

VERSION='audit-operations-1'


class OperationalPause(BaseException):
    """Control flow must bypass model/preparation error-to-result fallbacks."""


@dataclass(frozen=True)
class Limits:
    completion_attempts:int=200
    token_allowance:int=1000000
    execution_seconds:int=3600
    consecutive_failures:int=3
    min_free_bytes:int=1073741824
    pace_ms:int=500

    def __post_init__(self):
        bounds={'completion_attempts':(1,100000),'token_allowance':(1,1000000000),
            'execution_seconds':(1,604800),'consecutive_failures':(1,100),
            'min_free_bytes':(0,1099511627776),'pace_ms':(0,60000)}
        for key,(low,high) in bounds.items():
            if type(getattr(self,key)) is not int or not low<=getattr(self,key)<=high:
                raise AuditError('invalid_operational_limit')

    @classmethod
    def from_settings(cls,settings,*,recommendation=False):
        data=dict(settings.get('operational_limits',{}))
        if recommendation:data['completion_attempts']=settings.get('recommendation_max_completions',20)
        return cls(**data)


class Budget:
    def __init__(self,store,directory,owner,limits,*,token_counter=None,runner=None):
        self.store,self.path,self.owner,self.limits=store,directory/'budget.json',owner,limits
        self.token_counter,self.runner=token_counter,runner
        self.row_id=None
        with self.lock():
            if self.path.exists():
                value=self.read()
                if value['limits']!=asdict(limits) or value['owner_id']!=owner or value['version']!=VERSION:
                    raise AuditError('budget_identity_mismatch')
            else:
                if (directory/'meta.json').exists():raise AuditError('budget_ledger_missing')
                self.write({'version':VERSION,'owner_id':owner,'limits':asdict(limits),
                    'limits_id':canonical_sha256(asdict(limits)),'completion_attempts':0,'tokens_charged':0,
                    'known_tokens':0,'consecutive_failures':0,'failure_streaks':{},'elapsed_seconds':0.0,'active_since':None,
                    'pause_reason':'','requests':{},'services':{},'last_disk_free_bytes':None})

    @contextmanager
    def lock(self):
        fd=os.open(self.path.parent/'budget.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
        try:fcntl.flock(fd,fcntl.LOCK_EX);yield
        finally:os.close(fd)

    def read(self):return self.store.read(self.path)
    def write(self,value):self.store.write(self.path,value)

    def elapsed(self,value):
        return value['elapsed_seconds']+max(0,time.time()-value['active_since']) if value['active_since'] is not None else value['elapsed_seconds']

    def _reason(self,value,allow_unknown=False):
        value['last_disk_free_bytes']=shutil.disk_usage(self.path.parent).free
        value['last_disk_observed_at']=time.time()
        if not allow_unknown and any(r['state'] in {'reserved','dispatched','unknown'} and not r.get('acknowledged') for r in value['requests'].values()):return 'unknown_remote_completion'
        if value['last_disk_free_bytes']<self.limits.min_free_bytes:return 'budget_disk'
        if self.elapsed(value)>=self.limits.execution_seconds:return 'budget_elapsed'
        if value['consecutive_failures']>=self.limits.consecutive_failures:return 'budget_failures'
        return ''

    def check(self,*,allow_unknown=False):
        with self.lock():
            value=self.read();reason=self._reason(value,allow_unknown)
            if reason:value['pause_reason']=reason;self.write(value);raise OperationalPause(reason)

    def start(self):
        self.check()
        with self.lock():
            value=self.read()
            # An abandoned active interval conservatively includes downtime.
            if value['active_since'] is None:value['active_since']=time.time()
            value['pause_reason']='';self.write(value)

    def stop(self,reason=''):
        with self.lock():
            value=self.read();value['elapsed_seconds']=self.elapsed(value);value['active_since']=None
            value['artifact_bytes_at_checkpoint']=sum(p.stat().st_size for p in self.path.parent.rglob('*') if p.is_file() and not p.is_symlink())
            import resource
            value['process_max_rss_kib']=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            if reason:value['pause_reason']=reason
            self.write(value)

    def reserve(self,kind,tokens=0,responsibility='unknown'):
        if kind!='completion':raise AuditError('invalid_budget_boundary')
        if type(tokens) is not int or tokens<1:raise AuditError('invalid_token_reservation')
        with self.lock():
            value=self.read();reason=self._reason(value)
            if not reason and value['completion_attempts']>=self.limits.completion_attempts:reason='budget_completions'
            if not reason and value['tokens_charged']+tokens>self.limits.token_allowance:reason='budget_tokens'
            if reason:
                value['pause_reason']=reason;self.write(value);raise OperationalPause(reason)
            identity='allowance_'+secrets.token_hex(16)
            value['requests'][identity]={'state':'reserved','reserved_tokens':tokens,'charged_tokens':tokens,
                'known_tokens':None,'responsibility':responsibility if responsibility in {'scope','aspects','batch','reconciliation','verification','history_rewrite','gap_analysis','question_recommendation'} else 'unknown',
                'started_at':time.time(),'source_row_id':self.row_id}
            value['completion_attempts']+=1;value['tokens_charged']+=tokens
            self.write(value);return identity

    def dispatched(self,identity):
        with self.lock():
            value=self.read();value['requests'][identity]['state']='dispatched';self.write(value)

    def finish(self,identity,*,usage=None,error='none'):
        error=error if error in SAFE_ERRORS else "audit_failed"
        with self.lock():
            value=self.read();item=value['requests'][identity]
            if item['state'] in {'returned','failed_known','unknown'}:return
            known=type(usage) is int and usage>=0
            item.update(state='failed_known' if known and error!='none' else 'returned' if known else 'unknown',
                known_tokens=usage if known else None,error_category=error,
                duration_ms=round((time.time()-item['started_at'])*1000,3))
            if known:
                value['tokens_charged']+=usage-item['charged_tokens'];item['charged_tokens']=usage
                value['known_tokens']+=usage
            if item['responsibility']=='history_rewrite' or error!='none':
                key='history_rewrite' if item['responsibility']=='history_rewrite' else 'model'
                streaks=value.setdefault('failure_streaks',{})
                streaks[key]=streaks.get(key,0)+1 if error!='none' else 0
                value['consecutive_failures']=max(streaks.values(),default=0)
            if not known:value['pause_reason']='unknown_remote_completion'
            elif value['tokens_charged']>self.limits.token_allowance:value['pause_reason']='budget_tokens'
            self.write(value)

    def service(self,kind,elapsed,error=False):
        if kind not in {'embedding','reranking','tokenization','metadata','source_check'}:raise AuditError('invalid_service_counter')
        with self.lock():
            value=self.read();item=value['services'].setdefault(kind,{'attempts':0,'errors':0,'duration_ms':0.0})
            item['attempts']+=1;item['errors']+=int(error);item['duration_ms']=round(item['duration_ms']+elapsed,3)
            streaks=value.setdefault('failure_streaks',{});streaks[kind]=streaks.get(kind,0)+1 if error else 0
            value['consecutive_failures']=max(streaks.values(),default=0)
            self.write(value)

    def model_result(self,error):
        error=error if error in SAFE_ERRORS else "audit_failed"
        with self.lock():
            value=self.read();streaks=value.setdefault('failure_streaks',{})
            streaks['model']=streaks.get('model',0)+1 if error!='none' else 0
            value['consecutive_failures']=max(streaks.values(),default=0)
            self.write(value)

    def acknowledge_unknown(self,revision_id="synthetic_direct_choice"):
        with self.lock():
            value=self.read()
            for item in value['requests'].values():
                if item['state'] in {'reserved','dispatched','unknown'}:item['acknowledged']=True;item['acknowledgement_revision_id']=revision_id
            self.write(value)

    def unknown_row_ids(self):
        with self.lock():
            value=self.read()
        return sorted({r['source_row_id'] for r in value['requests'].values() if r.get('source_row_id') and r['state'] in {'reserved','dispatched','unknown'}})

    def summary(self):
        with self.lock():
            value=self.read()
        requests=value.pop('requests');value.update(elapsed_seconds=round(self.elapsed(value),3),
            unknown_reservations=sum(v['state'] in {'reserved','dispatched','unknown'} for v in requests.values()),
            unknown_reserved_tokens=sum(v['charged_tokens'] for v in requests.values() if v['state'] in {'reserved','dispatched','unknown'}),
            remaining_completions=max(0,self.limits.completion_attempts-value['completion_attempts']),
            remaining_tokens=max(0,self.limits.token_allowance-value['tokens_charged']),
            dispatched_completions=sum(v['state']!='reserved' for v in requests.values()),
            allowance_extension='unsupported_new_run_required',gpu_telemetry='unverified')
        return value

    async def io(self,fn,*args,**kwargs):
        if self.runner:return await self.runner.run(fn,*args,**kwargs)
        return fn(*args,**kwargs)

    async def bounded_operation(self,operation):
        value=await self.io(self.read)
        remaining=self.limits.execution_seconds-self.elapsed(value)
        if remaining<=0:raise OperationalPause('budget_elapsed')
        deadline=asyncio.timeout(remaining)
        try:
            async with deadline:return await operation()
        except TimeoutError:
            if deadline.expired():raise OperationalPause('budget_elapsed') from None
            raise

    async def dispatch(self,kind,operation,**metadata):
        await self.io(self.check)
        if kind!='completion':
            started=time.perf_counter();failed=True
            try:
                result=await self.bounded_operation(operation);failed=getattr(result,'status_code',200)>=400;return result
            finally:await self.io(self.service,kind,(time.perf_counter()-started)*1000,failed)
        tokens=metadata.get('prompt_tokens')
        output=metadata.get('output_tokens')
        if type(output) is not int or output<1:raise OperationalPause('budget_output_unbounded')
        if type(tokens) is not int:
            if self.token_counter is None:raise OperationalPause('budget_tokenizer_unavailable')
            tokens=await self.token_counter(metadata)
        tokens+=output
        allowance=await self.io(self.reserve,'completion',tokens,metadata.get('responsibility','history_rewrite'))
        await self.io(self.dispatched,allowance)
        callback=metadata.get('on_dispatch')
        if callback:await callback()
        try:
            response=await self.bounded_operation(operation)
        except BaseException as error:
            await self.io(self.finish,allowance,error=category(error))
            raise
        usage=getattr(response,'usage',None)
        prompt=getattr(usage,'prompt_tokens',None);completion=getattr(usage,'completion_tokens',None)
        actual=prompt+completion if type(prompt) is int and type(completion) is int else None
        await self.io(self.finish,allowance,usage=actual)
        if actual is None:raise OperationalPause('unknown_remote_completion')
        return response


from utils.concurrency import AdmissionLimiter


class AuditAdmission(AdmissionLimiter):
    """Audit-local pacing before shared admission; no shared policy mutation.

    Yield while normal waiters exist or all but one slots are occupied. With a
    capacity-one limiter only idle admission is possible. This is a courtesy,
    not a production-latency/SLA guarantee; shared workers may race admission.
    """
    def __init__(self,delegate,pace_ms):
        self.delegate,self.pace_ms=delegate,pace_ms

    async def run(self,operation,*,acquire_timeout,request_id=None):
        from utils.concurrency import run_with_limit
        started=time.monotonic()
        await asyncio.sleep(self.pace_ms/1000)
        while hasattr(self.delegate,'snapshot'):
            snapshot=self.delegate.snapshot()
            if snapshot.waiting==0 and snapshot.active<max(1,snapshot.capacity-1):break
            if time.monotonic()-started>=acquire_timeout:
                from utils.service_errors import ServiceOverloadedError
                raise ServiceOverloadedError('Audit yielded shared admission')
            await asyncio.sleep(.05)
        remaining=acquire_timeout-(time.monotonic()-started)
        if remaining<=0:
            from utils.service_errors import ServiceOverloadedError
            raise ServiceOverloadedError('Audit pacing exhausted admission allowance')
        return await run_with_limit(self.delegate,operation,acquire_timeout=remaining)
