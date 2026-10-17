"""Manual dependency-aware retention. Discovery is read-only; unknowns are held."""
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime,timezone
import fcntl
import functools
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat

from knowledge_audit.privacy import AuditError,private_directory
from utils.read_only_audit import canonical_sha256

VERSION='manual-dependency-retention-1'
_ids=re.compile(r'(?:r_|d_|rec_|rev_|rvw_|rex_|runex_)[0-9a-f]{32}|[0-9a-f]{64}')
_access=ContextVar('audit_artifact_access',default=frozenset())
CONTROLS={'retention.lock','audit-worker.lock'}


@contextmanager
def artifact_access(root,*,exclusive=False):
    root=Path(root);key=str(root.absolute())
    if key in _access.get():
        if exclusive:raise AuditError('cleanup_nested_access')
        yield;return
    private_directory(root)
    fd=os.open(root/'retention.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    token=None
    try:
        fcntl.flock(fd,(fcntl.LOCK_EX|fcntl.LOCK_NB) if exclusive else (fcntl.LOCK_SH|fcntl.LOCK_NB))
        token=_access.set(_access.get()|{key});yield
    except BlockingIOError:raise AuditError('cleanup_artifacts_busy') from None
    finally:
        if token is not None:_access.reset(token)
        os.close(fd)


def protected_method(function):
    @functools.wraps(function)
    def guarded(self,*args,**kwargs):
        root=self.store.root if hasattr(self,'store') else self.root
        with artifact_access(root):return function(self,*args,**kwargs)
    return guarded


def _references(value):
    if isinstance(value,str):return {value} if _ids.fullmatch(value) else set()
    if isinstance(value,list):return set().union(*(_references(v) for v in value)) if value else set()
    if isinstance(value,dict):return set().union(*(_references(v) for v in value.values()),*(_references(k) for k in value)) if value else set()
    return set()


def _tree(path,root):
    files=[];refs=set();aliases=set();unsafe=False;size=0
    for parent,dirs,names in os.walk(path,followlinks=False):
        for name in list(dirs)+names:
            p=Path(parent)/name;info=p.lstat()
            if stat.S_ISLNK(info.st_mode) or info.st_uid!=os.getuid() or info.st_mode&0o077:
                unsafe=True;dirs[:]=[d for d in dirs if d!=name];continue
            if p.is_file():
                blob=p.read_bytes();size+=len(blob)
                files.append([str(p.relative_to(root)),info.st_ino,info.st_size,info.st_mtime_ns,hashlib.sha256(blob).hexdigest()])
                if p.suffix=='.json':
                    try:
                        payload=json.loads(blob);refs|=_references(payload)
                        if isinstance(payload,dict):
                            aliases|={payload[k] for k in ('export_id','export_revision_id','review_revision_id') if isinstance(payload.get(k),str) and _ids.fullmatch(payload[k])}
                    except (ValueError,UnicodeDecodeError):unsafe=True
    return files,refs,aliases,unsafe,size


def _known_layout(path,kind):
    # Only versioned artifact filenames are eligible. An unexpected file holds
    # the entire unit instead of deleting an operator's unknown material.
    top={'datasets':{'meta.json','dataset.json','privacy.key','preparations.json'},
         'snapshots':{'meta.json','kb-snapshot.json','kb-snapshot-manifest.json'},
         'runs':{'meta.json','creation.json','progress.json','progress-dirty.json','budget.json','budget.lock','run.lock','execution.lock','metadata.lock','worker.lock','model-metrics.jsonl'},
         'recommendations':{'meta.json','source.json','metadata-index.json','results.json','results.final.json','latest-review.json','revision.lock','budget.json','budget.lock','model-metrics.jsonl'}}
    dirs={'runs':{'rows','attempts','exports','combined-exports','recovery-choices'},'recommendations':{'exports'}}
    for item in path.iterdir():
        if item.is_symlink():return False
        if item.is_dir() and item.name not in dirs.get(kind,set()):return False
        if item.is_file() and item.name not in top[kind] and not (kind=='recommendations' and re.fullmatch(r'rvw_[0-9a-f]{32}\.json',item.name)) and item.name not in {'.hold','HOLD'}:return False
    file_patterns={
        'runs':[r'rows/row_[0-9a-f]{32}\.json',r'attempts/row_[0-9a-f]{32}/(?:request_[0-9a-f]{32}|row-attempt-[0-9]+(?:-interruption-[0-9a-f]{16})?)\.json',
                r'recovery-choices/recovery_[0-9a-f]{32}\.json',r'exports/(?:evidence|restricted)/latest\.json',
                r'exports/(?:evidence|restricted)/rev_[0-9a-f]{32}/(?:coverage\.csv|manifest\.json)',
                r'combined-exports/(?:evidence|restricted)/runex_[0-9a-f]{32}/(?:coverage\.csv|manifest\.json)'],
        'recommendations':[r'exports/(?:evidence|restricted)/rex_[0-9a-f]{32}/(?:coverage\.csv|manifest\.json)']}
    directory_patterns={'runs':[r'rows',r'attempts(?:/row_[0-9a-f]{32})?',r'recovery-choices',
        r'exports(?:/(?:evidence|restricted)(?:/rev_[0-9a-f]{32})?)?',
        r'combined-exports(?:/(?:evidence|restricted)(?:/runex_[0-9a-f]{32})?)?'],
        'recommendations':[r'exports(?:/(?:evidence|restricted)(?:/rex_[0-9a-f]{32})?)?']}
    for item in path.rglob('*'):
        if item.is_symlink():return False
        relative=str(item.relative_to(path))
        if item.parent==path and item.is_file():continue
        patterns=directory_patterns.get(kind,[]) if item.is_dir() else file_patterns.get(kind,[])
        if not any(re.fullmatch(pattern,relative) for pattern in patterns):return False
    return True


def lease_busy(path):
    if not path.exists():return False
    if path.is_symlink():return True
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    try:
        try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);return False
        except BlockingIOError:return True
    finally:os.close(fd)


def plan_cleanup(root,owner,days,*,as_of=None):
    if not Path(root).is_dir():raise AuditError('artifact_not_found')
    root=private_directory(Path(root)) # validates; existing root is never changed
    if type(owner) is not int or owner<0 or type(days) is not int or not 1<=days<=3650:raise AuditError('invalid_cleanup_policy')
    as_of=datetime.now(timezone.utc).timestamp() if as_of is None else as_of
    nodes={};inventory=[];uncertain=False;active_work=False
    busy=str(root.absolute()) not in _access.get() and (lease_busy(root/'audit-worker.lock') or lease_busy(root/'retention.lock'))
    for group in sorted(root.iterdir()):
        if group.name in CONTROLS or re.fullmatch(r'creation-\d+\.lock',group.name):continue
        if group.is_symlink():uncertain=True;continue
        known=group.name in {'datasets','snapshots','runs','recommendations'}
        if not group.is_dir():
            uncertain=True;continue
        units=sorted(group.iterdir()) if known else [group]
        for path in units:
            if path.is_symlink() or not path.is_dir():uncertain=True;continue
            identity=path.name;kind=group.name
            files,refs,aliases,unsafe,size=_tree(path,root);inventory+=files
            reason=[];meta={}
            if busy or (str(root.absolute()) not in _access.get() and lease_busy(path/'worker.lock')):reason.append('active_lease')
            if known:
                patterns={'datasets':r'd_[0-9a-f]{32}','snapshots':r'[0-9a-f]{64}','runs':r'r_[0-9a-f]{32}','recommendations':r'rec_[0-9a-f]{32}'}
                if not re.fullmatch(patterns[kind],identity):reason.append('unknown_artifact_type')
                try:
                    if (path/'meta.json').is_symlink():raise ValueError()
                    meta=json.loads((path/'meta.json').read_bytes())
                    if not isinstance(meta,dict) or type(meta.get('owner_id')) is not int:raise ValueError()
                except (OSError,ValueError):meta={};reason.append('unknown_metadata');uncertain=True
                if not _known_layout(path,kind):reason.append('unknown_artifact_type')
            else:reason.append('protected_package_or_unknown_namespace')
            if unsafe:reason.append('unsafe_permissions_or_link');uncertain=True
            if (path/'.hold').exists() or (path/'HOLD').exists() or meta.get('retention_hold') or meta.get('protected'):reason.append('explicit_hold')
            if meta.get('owner_id')!=owner:reason.append('different_owner_or_shared')
            if len(meta.get('authorized_owners',[]))>1:reason.append('different_owner_or_shared')
            if kind in {'runs','recommendations'} and meta.get('state') in {'queued','running'}:active_work=True
            if kind in {'runs','recommendations'} and meta.get('state')!='completed':reason.append('active_or_recoverable')
            if kind=='datasets' and meta.get('preparation_status')!='ready':reason.append('preparation_not_ready')
            try:created=datetime.fromisoformat(meta['created_at']);created=created if created.tzinfo else created.replace(tzinfo=timezone.utc)
            except (KeyError,TypeError,ValueError):reason.append('unknown_age');created=datetime.fromtimestamp(as_of,timezone.utc)
            if as_of-created.timestamp()<days*86400:reason.append('not_expired')
            identity_keys={'datasets':('input_id','redacted_input_id'),'snapshots':('snapshot_id',),'runs':('run_id',),'recommendations':('recommendation_revision_id',)}
            if known:aliases|={meta[k] for k in identity_keys[kind] if isinstance(meta.get(k),str) and _ids.fullmatch(meta[k])}
            else:aliases=set()
            nodes[identity]={'path':str(path.relative_to(root)),'kind':kind,'owner_id':meta.get('owner_id'),
                'comparison_group':canonical_sha256([meta.get('owner_id'),meta.get('input_id'),meta.get('snapshot_id')]) if kind=='runs' else None,'aliases':sorted(aliases),'reasons':sorted(set(reason)),'references':sorted(refs-{identity}),'bytes':size,'inode':path.stat().st_ino}
    # A4 eligibility dynamically compares same-owner input/snapshot observations.
    # Preserve that implicit dependency; deleting an old full counterproof must
    # never make a retained possible-gap run newly eligible for drafting.
    comparison_groups={}
    for identity,node in nodes.items():
        if node['comparison_group']:comparison_groups.setdefault(node['comparison_group'],set()).add(identity)
    for identity,node in nodes.items():
        if node['comparison_group']:
            node['references']=sorted(set(node['references'])|(comparison_groups[node['comparison_group']]-{identity}))
    identities={}
    for identity,node in nodes.items():
        for alias in [identity,*node['aliases']]:identities.setdefault(alias,set()).add(identity)
    # Unknown source strings (including arbitrary hex values) are not copied
    # into a cleanup plan unless they resolve to a known artifact identity.
    for node in nodes.values():node['references']=[ref for ref in node['references'] if ref in identities]
    retained={identity for identity,node in nodes.items() if node['reasons']}
    if uncertain or active_work:retained=set(nodes)
    changed=True
    while changed:
        before=len(retained)
        for identity in list(retained):
            for reference in nodes[identity]['references']:
                retained.update(identities.get(reference,set()))
        changed=len(retained)!=before
    for identity in retained:
        if not nodes[identity]['reasons']:nodes[identity]['reasons']=['active_work_present'] if active_work else ['referenced_by_retained_artifact'] if not uncertain else ['unresolved_inventory']
    candidates=sorted(identity for identity in nodes if identity not in retained)
    value={'version':VERSION,'root_id':canonical_sha256(str(root)),'owner_id':owner,'retention_days':days,'as_of':as_of,
        'automatic_deletion':False,'inventory_sha256':canonical_sha256(sorted(inventory)),
        'inventory_file_count':len(inventory),'inventory_bytes':sum(n['bytes'] for n in nodes.values()),
        'nodes':nodes,'candidates':candidates,'unresolved_inventory':uncertain}
    value['plan_id']=canonical_sha256(value);return value


def apply_cleanup(store,plan,plan_id):
    if plan.get('version')!=VERSION or plan.get('plan_id')!=plan_id or canonical_sha256({k:v for k,v in plan.items() if k!='plan_id'})!=plan_id:
        raise AuditError('cleanup_plan_identity_mismatch')
    root=store.root
    with artifact_access(root,exclusive=True):
        current=plan_cleanup(root,plan['owner_id'],plan['retention_days'],as_of=plan['as_of'])
        if current!=plan:raise AuditError('cleanup_plan_stale')
        # Exclude work across processes even if a stale metadata state says completed.
        gate=store.global_lease()
        leases=[]
        try:
            for identity in plan['candidates']:
                if plan['nodes'][identity]['kind']=='runs':leases.append(store.lease(identity))
            if not shutil.rmtree.avoids_symlink_attacks:raise AuditError('cleanup_safe_delete_unavailable')
            # Parents/dependents first; all deletion targets were proven an
            # unreferenced candidate closure. No symlink target is traversed.
            ordered=sorted(plan['candidates'],key=lambda key:{'recommendations':0,'runs':1,'datasets':2,'snapshots':3}[plan['nodes'][key]['kind']])
            deleted=[]
            output=private_directory(root/'cleanup-outcomes');outcome_path=output/(plan_id+'.json')
            outcome={'version':VERSION,'plan_id':plan_id,'deleted_id_hashes':deleted,'deleted_count':0,'owner_id':plan['owner_id'],'state':'applying'}
            store.write(outcome_path,outcome)
            for identity in ordered:
                node=plan['nodes'][identity];path=root/node['path']
                if path.is_symlink() or path.stat().st_ino!=node['inode'] or root not in path.parents:raise AuditError('cleanup_path_changed')
                # Recheck incoming references from every artifact that remains.
                fresh=plan_cleanup(root,plan['owner_id'],plan['retention_days'],as_of=plan['as_of'])
                if fresh['unresolved_inventory'] or identity not in fresh['candidates']:raise AuditError('cleanup_new_reference')
                outcome['current_target_hash']=canonical_sha256(identity);store.write(outcome_path,outcome)
                try:shutil.rmtree(path)
                except BaseException:
                    outcome['state']='interrupted_or_failed';store.write(outcome_path,outcome);raise
                deleted.append(canonical_sha256(identity));outcome['deleted_count']=len(deleted);store.write(outcome_path,outcome)
            outcome.update(state='completed',current_target_hash='');store.write(outcome_path,outcome)
            return outcome
        finally:
            for lease in leases:os.close(lease)
            os.close(gate)
