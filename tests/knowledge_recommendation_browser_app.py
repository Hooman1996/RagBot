"""Isolated A4 Chromium fixture: synthetic auth/artifacts/models, no services."""
import asyncio
import os
from tests.knowledge_coverage_browser_app import create_app as coverage_app,SYNTHETIC_OWNER
from tests.test_knowledge_recommendations import DraftModel
from tests.test_answering_service import ImmediateRunner
from knowledge_audit.recommendation_jobs import RecommendationJobs
from knowledge_audit.recommendation_store import RecommendationStore
from knowledge_audit.recommendations import RecommendationEngine

SYNTHETIC_REVIEWER = 990002


def create_app(port):
    app=coverage_app(port)
    import main
    # A second fictional admin, who may approve the owner's recommendations.
    reviewer={'id':SYNTHETIC_REVIEWER,'username':'reviewer-synthetic','full_name':'Synthetic Reviewer','role':'admin','is_active':True}
    owner_db,owner_auth=main.db_manager,main.authentication_service
    class Database:
        def get_web_user_by_id(self,uid):return dict(reviewer) if uid==SYNTHETIC_REVIEWER else owner_db.get_web_user_by_id(uid)
    class Authentication:
        def authenticate(self,username,password):
            if username==reviewer['username'] and password=='synthetic-browser-only':return dict(reviewer)
            return owner_auth.authenticate(username,password)
    main.db_manager=Database();main.authentication_service=Authentication()
    _,store,coverage_jobs=app.state.coverage_runtime
    recs=RecommendationStore(store)
    class SlowDraft(DraftModel):
        progress_callback=None
        async def call(self,role,data):
            if self.progress_callback:await self.progress_callback(role)
            await asyncio.sleep(.8)
            result=await super().call(role,data)
            if role=='question_recommendation':
                for rec in result['recommendations']:
                    rec['recommended_question']='مهلت ارسال درخواست کارت آزمایشی چیست؟'
                    rec['justification']='بررسی پرسش و مسیر دسته‌بندی توسط تیم دانش لازم است.'
            return result
    async def factory(meta):
        coverage=store.owned('runs',meta['source_run_id'],SYNTHETIC_OWNER)
        _,redactor=store.dataset(coverage['dataset_id'],SYNTHETIC_OWNER)
        return RecommendationEngine(SlowDraft(),store.snapshot(meta['snapshot_id'],SYNTHETIC_OWNER),redactor)
    app.state.recommendation_runtime=(recs,RecommendationJobs(recs,coverage_jobs,ImmediateRunner(),factory))
    return app


if __name__=='__main__':
    import argparse,uvicorn
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--port',type=int,required=True)
    args=parser.parse_args();uvicorn.run(create_app(args.port),host='127.0.0.1',port=args.port,access_log=False,log_level='critical')
