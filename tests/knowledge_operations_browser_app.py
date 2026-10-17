"""A6.2 synthetic mocked allowance pause/recovery fixture; no live services."""
import asyncio
from types import SimpleNamespace
from tests.knowledge_execution_browser_app import create_app as base
from tests.knowledge_coverage_browser_app import SYNTHETIC_OWNER
from tests.test_knowledge_coverage_pipeline import LabeledModel,Retrieval
from knowledge_audit.pipeline import CoverageEvaluator
from knowledge_audit.preparation import QueryPreparer
from utils.audit_dispatch import audit_dispatch,completion_metadata


def create_app(port):
    app=base(port);_,store,jobs=app.state.coverage_runtime
    async def factory(meta):
        dataset,redactor=store.dataset(meta['dataset_id'],SYNTHETIC_OWNER);snapshot=store.snapshot(meta['snapshot_id'],SYNTHETIC_OWNER)
        class Model(LabeledModel):
            async def call(self,role,data):
                if self.progress_callback:await self.progress_callback(role)
                async def operation():
                    await asyncio.sleep(.03)
                    return SimpleNamespace(usage=SimpleNamespace(prompt_tokens=10,completion_tokens=10))
                with completion_metadata(role,10):await audit_dispatch('completion',operation,output_tokens=20)
                return await super().call(role,data)
        return CoverageEvaluator(snapshot=snapshot,model=Model(snapshot,{'1':['a1'],'2':['a2']}),
            retrieval=Retrieval(['1','2'],['1','2']),preparer=QueryPreparer.from_answering_service(app.state.answering_service),
            redactor=redactor,dataset=dataset,entry_budget=meta['settings']['entry_budget'])
    jobs.factory=factory;return app


if __name__=='__main__':
    import argparse,uvicorn
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--port',type=int,required=True);args=parser.parse_args()
    uvicorn.run(create_app(args.port),host='127.0.0.1',port=args.port,access_log=False,log_level='critical')
