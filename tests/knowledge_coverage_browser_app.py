"""Isolated real-browser fixture. Synthetic authentication/data; no service calls.

Run with a local browser harness, never import as the production app entrypoint.
Runtime env overrides are process-only; no root env files or user tables change.
"""
import asyncio
from contextlib import asynccontextmanager
import logging
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace

from tests.test_answering_service import Processor, Rewriter, Classifier, ImmediateRunner
from tests.test_knowledge_coverage_pipeline import LabeledModel, Retrieval
from knowledge_audit.jobs import CoverageJobs
from knowledge_audit.pipeline import CoverageEvaluator
from knowledge_audit.preparation import QueryPreparer
from knowledge_audit.settings import load_coverage_settings
from knowledge_audit.privacy import private_json
from utils.read_only_audit import canonical_sha256, text_sha256

SYNTHETIC_OWNER = 990001


def create_app(port):
    os.environ.update(KNOWLEDGE_COVERAGE_ENABLED="true", ENVIRONMENT="staging")
    logging.disable(logging.CRITICAL)
    import main
    from knowledge_audit.api import mount
    from tests.test_knowledge_coverage_access_jobs import seed
    if not any(getattr(route,"path",None)=="/knowledge-coverage" for route in main.app.routes):
        mount(main.app)
    import web_auth
    # There are no real database/authentication objects in this fixture runtime.
    user = {"id": SYNTHETIC_OWNER, "username": "planner-synthetic", "full_name": "Synthetic Planner",
            "role": "admin", "is_active": True}
    class Database:
        def get_web_user_by_id(self, uid): return dict(user) if uid == SYNTHETIC_OWNER else None
    class Authentication:
        def authenticate(self, username, password):
            return dict(user) if username == user["username"] and password == "synthetic-browser-only" else None
    main.db_manager = Database()
    main.authentication_service = Authentication()
    main.blocking_runner = ImmediateRunner()
    os.environ.update(WEB_ENVIRONMENT="development", WEB_COOKIE_MODE="local-http",
        WEB_PUBLIC_ORIGIN=f"http://127.0.0.1:{port}", WEB_SESSION_SECONDS="900",
        WEB_SESSION_SECRET="synthetic-browser-only-" + "x" * 48)
    directory = Path(tempfile.mkdtemp(prefix="faq-a21-synthetic-browser-"))
    store, d, s, meta, data, redactor, prep = seed(directory, owner=SYNTHETIC_OWNER)
    # Second fictional source supplies the cutoff, independently of the duration.
    capture = directory / "capture-two"
    capture.mkdir(mode=0o700)
    original = store.snapshot(s["snapshot_id"], SYNTHETIC_OWNER)
    original.pop("snapshot_id")
    a = original["records"][0]
    a.update(answer="Approval takes two working days.", content="question: synthetic title\nanswer: Approval takes two working days.")
    a.update(content_sha256=text_sha256(a["content"]), source_content_sha256=text_sha256(a["content"]))
    b = {**a, "chunk_id": "2", "faq_entry_id": "2", "answer": "Submission cutoff is 18:00.",
         "content": "question: synthetic cutoff\nanswer: Submission cutoff is 18:00."}
    b.update(content_sha256=text_sha256(b["content"]), source_content_sha256=text_sha256(b["content"]))
    original["records"] = [a, b]
    original["snapshot_id"] = canonical_sha256(original)
    private_json(capture / "kb-snapshot.json", original)
    import hashlib
    private_json(capture / "kb-snapshot-manifest.json", {"snapshot_id": original["snapshot_id"],
        "content_file_sha256": hashlib.sha256((capture / "kb-snapshot.json").read_bytes()).hexdigest()})
    store.register_snapshot(capture / "kb-snapshot.json", capture / "kb-snapshot-manifest.json", SYNTHETIC_OWNER)
    class SlowModel(LabeledModel):
        progress_callback = None
        async def call(self, role, payload):
            if self.progress_callback: await self.progress_callback(role)
            await asyncio.sleep(.15)
            value = await super().call(role, payload)
            if role == "batch" and "invalid citation" in payload["question"].lower():
                for support in value["supports"]:
                    support["citations"][0]["sentence_number"] = 999
            return value
    async def factory(run):
        restored, r = store.dataset(run["dataset_id"], SYNTHETIC_OWNER)
        snap = store.snapshot(run["snapshot_id"], SYNTHETIC_OWNER)
        model = SlowModel(snap, {"1": ["a1"], "2": ["a2"]})
        class Engine(CoverageEvaluator):
            async def evaluate(self, event, row):
                ids = ["1"] if "partial" in event.content.lower() else ["1", "2"]
                self.retrieval = Retrieval([] if "invalid citation" in event.content.lower() else ids, ids)
                return await super().evaluate(event, row)
        engine = Engine(snapshot=snap, model=model, retrieval=Retrieval([], []), preparer=prep,
            redactor=r, dataset=restored, entry_budget=run["settings"]["entry_budget"])
        engine.runtime_configuration = {"fixture": "synthetic-browser-1", "no_external_services": True}
        return engine
    jobs = CoverageJobs(store, factory, ImmediateRunner())
    main.app.state.coverage_runtime = (load_coverage_settings(), store, jobs)
    main.app.state.blocking_runner = ImmediateRunner()
    main.app.state.answering_service = SimpleNamespace(text_processor=Processor(),
        intent_classifier=Classifier(), history_rewriting_service=Rewriter(), blocking_runner=ImmediateRunner())
    @asynccontextmanager
    async def lifespan(app):
        yield
        await jobs.aclose()
    main.app.router.lifespan_context = lifespan
    return main.app


if __name__ == "__main__":
    import argparse
    import uvicorn
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    uvicorn.run(create_app(args.port), host="127.0.0.1", port=args.port, access_log=False, log_level="critical")
