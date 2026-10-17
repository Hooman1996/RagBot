"""A5 isolated synthetic browser runtime. No model/service clients are called."""
import asyncio
import copy
from tests.knowledge_recommendation_browser_app import create_app as recommendation_app
from tests.knowledge_coverage_browser_app import SYNTHETIC_OWNER
from tests.test_knowledge_recommendations import DraftModel
from tests.test_answering_service import ImmediateRunner
from knowledge_audit.recommendation_jobs import RecommendationJobs
from knowledge_audit.recommendations import RecommendationEngine


def create_app(port):
    app = recommendation_app(port)
    _, store, coverage = app.state.coverage_runtime
    recs, _ = app.state.recommendation_runtime

    class TwoProposals(DraftModel):
        progress_callback = None
        async def call(self, role, data):
            if self.progress_callback:
                await self.progress_callback(role)
            await asyncio.sleep(.35)
            value = await super().call(role, data)
            if role == 'question_recommendation':
                value['recommendations'][0]['recommended_question'] = 'مهلت ارسال درخواست کارت آزمایشی چیست؟'
                second = copy.deepcopy(value['recommendations'][0])
                second.update(recommendation_id='q2', recommended_question='در چه بازه‌ای می‌توان درخواست آزمایشی را ارسال کرد؟')
                value['recommendations'].append(second)
            return value

    async def factory(meta):
        run = store.owned('runs', meta['source_run_id'], SYNTHETIC_OWNER)
        _, redactor = store.dataset(run['dataset_id'], SYNTHETIC_OWNER)
        return RecommendationEngine(TwoProposals(), store.snapshot(meta['snapshot_id'], SYNTHETIC_OWNER), redactor)
    app.state.recommendation_runtime = (recs, RecommendationJobs(recs, coverage, ImmediateRunner(), factory))
    return app


if __name__ == '__main__':
    import argparse
    import uvicorn
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, required=True)
    args = parser.parse_args()
    uvicorn.run(create_app(args.port), host='127.0.0.1', port=args.port, access_log=False, log_level='critical')
