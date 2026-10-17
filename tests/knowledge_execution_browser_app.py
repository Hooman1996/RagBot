"""Isolated A6.1 Chromium fixture: synthetic account/input and mocked inference."""
import asyncio
from tests.knowledge_run_export_browser_app import create_app as base_app
from tests.knowledge_coverage_browser_app import SYNTHETIC_OWNER
from tests.test_knowledge_coverage_pipeline import LabeledModel, Retrieval
from knowledge_audit.pipeline import CoverageEvaluator
from knowledge_audit.preparation import QueryPreparer


def create_app(port):
    app=base_app(port)
    _,store,jobs=app.state.coverage_runtime
    blocked=set()
    async def factory(meta):
        dataset,redactor=store.dataset(meta['dataset_id'],SYNTHETIC_OWNER)
        snapshot=store.snapshot(meta['snapshot_id'],SYNTHETIC_OWNER)
        class Model(LabeledModel):
            async def call(self,role,data):
                if self.progress_callback:await self.progress_callback(role)
                if role=='scope' and 'interrupt synthetic' in data.get('original_question','').lower() and meta['run_id'] not in blocked:
                    blocked.add(meta['run_id']);await asyncio.sleep(60)
                await asyncio.sleep(.03)
                return await super().call(role,data)
        preparer=QueryPreparer.from_answering_service(app.state.answering_service)
        engine=CoverageEvaluator(snapshot=snapshot,model=Model(snapshot,{'1':['a1'],'2':['a2']}),
            retrieval=Retrieval(['1','2'],['1','2']),preparer=preparer,redactor=redactor,dataset=dataset,
            entry_budget=meta['settings']['entry_budget'])
        engine.runtime_configuration={'fixture':'a61-synthetic-no-service-calls'}
        return engine
    jobs.factory=factory
    return app


if __name__=='__main__':
    import argparse
    import uvicorn
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--port',type=int,required=True)
    args=parser.parse_args()
    uvicorn.run(create_app(args.port),host='127.0.0.1',port=args.port,access_log=False,log_level='critical')
