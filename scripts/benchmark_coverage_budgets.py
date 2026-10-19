"""Identical 918-row mocked input, bounded filesystem-only allowance overhead."""
import json
from pathlib import Path
import statistics
import sys
import tempfile
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tests.test_knowledge_execution_recovery import synthetic_918,create
from knowledge_audit.operations import Budget,Limits
from knowledge_audit.retention import artifact_access


def main():
    root=Path(tempfile.mkdtemp(prefix='faq-a62-overhead-'));store,d,s,old,data=synthetic_918(root)
    meta=create(store,d,s,old,'full_input');rid=meta['run_id'];b=Budget(store,store._path('runs',rid),1,Limits())
    originals=[store.row(rid,key,1) for key in meta['row_ids'][:12]]
    report={'version':'a62-file-io-1','scope':'mocked_file_io_no_service_throughput','input_rows':918,'boundaries_per_iteration':12,'iterations':3,'live_dispatches':0}
    with artifact_access(store.root):
        for variant in ['checkpoint_only','checkpoint_with_allowance']:
            timings=[]
            for _ in range(3):
                started=time.perf_counter()
                for original in originals:
                    if variant=='checkpoint_with_allowance':
                        reservation=b.reserve('completion',100,'batch');b.dispatched(reservation);b.finish(reservation,usage=80)
                    row={**original,'processing_status':'completed','outcome':'excluded'}
                    store.save_row(rid,row,1);assert store.progress(rid,1)['imported_rows']==918
                timings.append(round((time.perf_counter()-started)*1000,3))
                for row in originals:store.save_row(rid,row,1)
            report[variant]={'measurements_ms':timings,'median_ms':statistics.median(timings)}
    print(json.dumps(report,sort_keys=True))


if __name__=='__main__':main()
