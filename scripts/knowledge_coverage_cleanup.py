"""Trusted operator retention tool. Defaults to read-only dry-run; no path API."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def main():
    # Cleanup remains available when the audit is disabled so leftover data can be deleted.
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1]/'.env',override=False)
    from knowledge_audit.settings import load_coverage_settings
    from knowledge_audit.retention import plan_cleanup,apply_cleanup
    from knowledge_audit.store import CoverageStore
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--owner-id',type=int,required=True)
    parser.add_argument('--plan-file',type=Path)
    parser.add_argument('--apply-plan-id')
    args=parser.parse_args();settings=load_coverage_settings()
    if args.apply_plan_id:
        if not args.plan_file:parser.error('apply requires a saved plan file and exact plan ID')
        plan=json.loads(args.plan_file.read_text())
        if plan['owner_id']!=args.owner_id:parser.error('owner does not match plan')
        result=apply_cleanup(CoverageStore(settings.artifact_dir),plan,args.apply_plan_id)
    else:
        result=plan_cleanup(settings.artifact_dir,args.owner_id,settings.retention_days)
        if args.plan_file:
            from knowledge_audit.privacy import private_write
            private_write(args.plan_file,(json.dumps(result,sort_keys=True)+'\n').encode())
    print(json.dumps({'plan_id':result['plan_id'],'mode':'apply' if args.apply_plan_id else 'dry_run',
        'candidate_count':len(result.get('candidates',[])),'deleted_count':result.get('deleted_count',0),
        'inventory_files':result.get('inventory_file_count'),'unresolved_inventory':result.get('unresolved_inventory',False)}))


if __name__=='__main__':main()
