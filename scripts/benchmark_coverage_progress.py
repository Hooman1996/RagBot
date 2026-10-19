"""A6.1 isolated 918-row file-I/O comparison; no service/model calls."""
import argparse
import json
from pathlib import Path
import statistics
import tempfile
import time
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests.test_knowledge_execution_recovery import synthetic_918, create


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--iterations',type=int,default=5)
    args=parser.parse_args()
    if not 1<=args.iterations<=10:parser.error('iterations must be 1–10')
    root=Path(tempfile.mkdtemp(prefix='faq-a61-progress-'))
    store,d,s,old,dataset=synthetic_918(root)
    meta=create(store,d,s,old,'full_input');rid=meta['run_id']
    counts={'row':0,'metadata':0,'index':0};read=store.read
    def counted(path):
        category='row' if path.parent.name=='rows' else 'index' if path.name=='progress.json' else 'metadata'
        counts[category]+=1
        return read(path)
    store.read=counted
    report={'scope':'synthetic_file_io_only','rows':918,'iterations':args.iterations,'model_dispatches':0}
    for variant in ('baseline_full_rows','indexed'):
        latencies=[]
        counts.update(row=0,metadata=0,index=0)
        for n in range(args.iterations):
            started=time.perf_counter()
            if variant=='baseline_full_rows':
                rows=store.rows(rid,1)
                assert len(rows)==918
            else:
                assert store.progress(rid,1)['imported_rows']==918
            latencies.append((time.perf_counter()-started)*1000)
        report[variant+'_poll']={'median_ms':round(statistics.median(latencies),3),'reads':dict(counts)}
        latencies=[];counts.update(row=0,metadata=0,index=0)
        for row_id in meta['row_ids'][:args.iterations]:
            row=store.row(rid,row_id,1);row.update(processing_status='completed',outcome='excluded')
            started=time.perf_counter()
            if variant=='baseline_full_rows':
                with store.run_lock(rid):store.write(store._path('runs',rid)/'rows'/(row_id+'.json'),row)
                rows=store.rows(rid,1)
                assert len(rows)==918
            else:
                store.save_row(rid,row,1);assert store.progress(rid,1)['imported_rows']==918
            latencies.append((time.perf_counter()-started)*1000)
        report[variant+'_checkpoint_and_progress']={'median_ms':round(statistics.median(latencies),3),'reads':dict(counts)}
        # Restore identical state before the other implementation measurement.
        for row_id in meta['row_ids'][:args.iterations]:
            row=store.row(rid,row_id,1);row.update(processing_status='pending',outcome='pending')
            store.write(store._path('runs',rid)/'rows'/(row_id+'.json'),row)
        store.progress(rid,1,reconcile=True)
    print(json.dumps(report,sort_keys=True))


if __name__=='__main__':main()
