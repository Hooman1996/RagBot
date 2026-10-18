"""F8d before/after: one 50-row mocked run with repeated-question copying off, then on.

The setting is the only variable. With it off no key is computed and nothing
is copied, so "off" is the before measurement. Synthetic text, mocked model
and retrieval only; no service is contacted.
"""
import asyncio
from collections import Counter
import json
import os
from pathlib import Path
import statistics
import sys
import tempfile
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ.update(KNOWLEDGE_COVERAGE_ENABLED='true',ENVIRONMENT='staging')
from knowledge_audit import dedupe
from knowledge_audit.jobs import CoverageJobs
from knowledge_audit.retention import artifact_access
from tests.test_answering_service import ImmediateRunner
from tests.test_coverage_dedupe import Model,build,engine_for,event,new_run
from tests.test_knowledge_coverage_pipeline import Retrieval
from tests.test_knowledge_execution_recovery import synthetic_918,create

ITERATIONS=3


def questions():
    """40 distinct history-free questions plus 10 exact repeats, each row in its own session."""
    distinct=[f'Synthetic benchmark question number {n} about approval?' for n in range(1,41)]
    texts=distinct+distinct[:10]
    return [event(n,text,n,n%60) for n,text in enumerate(texts,1)]


def measure(store,d,s,enabled):
    meta=new_run(store,d,s)
    model=Model(store.snapshot(meta['snapshot_id'],1));retrieval=Retrieval(['1'],['1'])
    async def execute():
        async def factory(_):
            engine=engine_for(store,meta,model,dedupe_enabled=enabled);engine.retrieval=retrieval
            return engine
        jobs=CoverageJobs(store,factory,ImmediateRunner());jobs.start(meta['run_id'],1)
        await asyncio.gather(*jobs.tasks._tasks.values());await jobs.aclose()
    started=time.perf_counter();asyncio.run(execute());elapsed=time.perf_counter()-started
    rows=store.rows(meta['run_id'],1)
    assert store.owned('runs',meta['run_id'],1)['state']=='completed'
    return {'model_calls':len(model.calls),'calls_by_role':dict(sorted(Counter(r for r,_ in model.calls).items())),
            'retrieval_fetches':len(retrieval.metrics),'copied_rows':sum(bool(r.get('deduplicated_from_row_id')) for r in rows),
            'wall_ms':round(elapsed*1000,3)}


def rebuild_918(root):
    store,d,s,old,_=synthetic_918(root);meta=create(store,d,s,old,'full_input')
    rows=store._path('runs',meta['run_id'])/'rows'
    # Completed rows over 40 keys, later occurrences marked as copies, so the walk registers real sources.
    first={}
    for n,row_id in enumerate(meta['processing_row_ids']):
        row=store.read(rows/(row_id+'.json'));key=f'{n%40:064x}';source=first.setdefault(key,row_id)
        row.update(processing_status='completed',dedupe_key_sha256=key,deduplicated_from_row_id='' if source==row_id else source)
        store.write(rows/(row_id+'.json'),row)
    timings=[]
    with artifact_access(store.root):
        for _ in range(ITERATIONS):
            started=time.perf_counter();sources=dedupe.source_map(store,meta);timings.append(round((time.perf_counter()-started)*1000,3))
    assert len(sources)==40
    return {'variant':'map_rebuild_918','rows':918,'sources':len(sources),'iterations':ITERATIONS,'measurements_ms':timings,'median_ms':statistics.median(timings)}


def main():
    with tempfile.TemporaryDirectory(prefix='faq-f8d-dedupe-') as directory:
        root=Path(directory)
        for name in ('runs','store918'):(root/name).mkdir(mode=0o700)
        store,d,s,_=build(root/'runs',questions())
        for name,enabled in (('dedupe_off',False),('dedupe_on',True)):
            results=[measure(store,d,s,enabled) for _ in range(ITERATIONS)]
            stable={k:v for k,v in results[0].items() if k!='wall_ms'}
            assert all({k:v for k,v in r.items() if k!='wall_ms'}==stable for r in results)
            print(json.dumps({'variant':name,'scope':'mocked_model_and_retrieval','rows':50,'distinct_questions':40,'iterations':ITERATIONS,
                              **stable,'wall_ms':[r['wall_ms'] for r in results],'median_wall_ms':statistics.median(r['wall_ms'] for r in results)},sort_keys=True))
        print(json.dumps(rebuild_918(root/'store918'),sort_keys=True))


if __name__=='__main__':main()
