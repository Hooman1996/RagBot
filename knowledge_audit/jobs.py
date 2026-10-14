"""Tracked background pilot with protected row checkpoints and explicit recovery."""
from __future__ import annotations
import asyncio
import os

from mass_answer_jobs import MassAnswerJobManager
from knowledge_audit.privacy import AuditError
from knowledge_audit.prompts import prompt_identity
from knowledge_audit.runtime import code_identity
from utils.read_only_audit import canonical_sha256

TERMINAL = {"completed", "excluded", "needs_context", "needs_review", "invalid_input"}


def versions():
    code = code_identity()
    return {"prompts": prompt_identity(), "code": code, "code_id": canonical_sha256(code)}


class CoverageJobs:
    def __init__(self, store, factory, runner):
        self.store, self.factory, self.runner = store, factory, runner
        self.tasks = MassAnswerJobManager()
        self.serial = asyncio.Semaphore(1)
        self.closing = False

    def start(self, rid, owner):
        self.store.owned("runs", rid, owner)
        self.tasks.start(rid, lambda: self.work(rid, owner), operation_type="knowledge_coverage")

    async def work(self, rid, owner):
        lease = None
        global_lease = None
        engine = None
        active = None
        async with self.serial:
            try:
                lease = await self.runner.run(self.store.lease, rid)
                global_lease = await self.runner.run(self.store.global_lease)
                meta = await self.runner.run(self.store.owned, "runs", rid, owner)
                current_versions = versions()
                if current_versions["prompts"] != meta["versions"]["prompts"] or current_versions["code"]["file_sha256"] != meta["versions"]["code"]["file_sha256"]:
                    raise AuditError("audit_version_drift")
                meta.update(state="running", attempt=meta["attempt"] + 1, error_code="")
                await self.save_meta(meta)
                engine = await self.factory(meta)
                async def progress(stage):
                    live = await self.runner.run(self.store.owned, "runs", rid, owner)
                    if live.get("cancel_requested"):
                        raise asyncio.CancelledError()
                    await self.runner.run(self.store.update_run, rid, owner, {"stage": stage})
                engine.model.progress_callback = progress
                meta["versions"]["serving"] = engine.model.serving
                await self.save_meta(meta)
                expected_serving = dict(engine.model.serving)
                dataset = engine.dataset
                if hasattr(engine, "runtime_configuration"):
                    meta["versions"]["runtime_configuration"] = engine.runtime_configuration
                    await self.save_meta(meta)
                events = {e.source_row_id: e for e in dataset.selected}
                # Each retry checks persisted terminal rows. Completed rows do
                # not invoke models again; interrupted attempts replace one row.
                for row_id in meta["selected_row_ids"]:
                    await progress("preparation")
                    row = await self.runner.run(self.store.row, rid, row_id, owner)
                    if row["processing_status"] in TERMINAL:
                        continue
                    active = row_id
                    row.update(processing_status="running", attempt_count=row["attempt_count"] + 1)
                    await self.runner.run(self.store.save_row, rid, row, owner)
                    meta.update(active_row_id=row_id, stage="preparation")
                    await self.save_meta(meta)
                    result = await engine.evaluate(events[row_id], row)
                    result["attempt_count"] = row["attempt_count"]
                    await self.runner.run(self.store.save_row, rid, result, owner)
                    if result.get("stopping_reason") == "snapshot_mismatch":
                        raise AuditError("source_or_index_drift")
                    await engine.model.discover()
                    if engine.model.serving != expected_serving:
                        raise AuditError("audit_serving_drift")
                    all_rows = await self.runner.run(self.store.rows, rid, owner)
                    meta["completed_pilot_rows"] = sum(r["source_row_id"] in meta["selected_row_ids"] and r["processing_status"] in TERMINAL | {"failed"} for r in all_rows)
                    await self.save_meta(meta)
                    active = None
                meta.update(state="completed", active_row_id="", stage="finished")
                await self.save_meta(meta)
            except asyncio.CancelledError:
                if lease is not None:
                    await self.interrupt(rid, owner, active, "interrupted" if self.closing else "cancelled")
                raise
            except AuditError as exc:
                if lease is not None:
                    if str(exc) in {"source_or_index_drift", "audit_serving_drift", "audit_version_drift"}:
                        await self.invalidate(rid, owner, str(exc))
                    else:
                        await self.interrupt(rid, owner, active, "failed")
            except Exception:
                if lease is not None:
                    await self.interrupt(rid, owner, active, "failed")
            finally:
                if engine is not None and hasattr(engine, "aclose"):
                    await engine.aclose()
                if lease is not None:
                    os.close(lease)
                if global_lease is not None:
                    os.close(global_lease)

    async def save_meta(self, meta):
        from knowledge_audit.store import now
        meta["updated_at"] = now()
        await self.runner.run(self.store.update_run, meta["run_id"], meta["owner_id"], meta)

    async def interrupt(self, rid, owner, active, state):
        meta = await self.runner.run(self.store.owned, "runs", rid, owner)
        if active:
            row = await self.runner.run(self.store.row, rid, active, owner)
            row.update(processing_status="cancelled" if state == "cancelled" else "interrupted",
                       coverage_status="not_evaluated", outcome="pending", stopping_reason=state)
            await self.runner.run(self.store.save_row, rid, row, owner)
        meta.update(state=state, active_row_id="", stage=state, error_code="audit_failed" if state == "failed" else "")
        await self.save_meta(meta)

    async def invalidate(self, rid, owner, code):
        meta = await self.runner.run(self.store.owned, "runs", rid, owner)
        rows = await self.runner.run(self.store.rows, rid, owner)
        for row in rows:
            if row["source_row_id"] in meta["selected_row_ids"] and row["processing_status"] != "pending":
                row.update(processing_status="needs_review", coverage_status="uncertain", outcome="needs_context",
                           stopping_reason="snapshot_mismatch", evidence_visibility="snapshot_mismatch")
                await self.runner.run(self.store.save_row, rid, row, owner)
        meta.update(state="incompatible", error_code=code, active_row_id="", stage="review")
        await self.save_meta(meta)

    async def recover(self, rid, owner):
        """Explicit retry checks the OS lease; never steals an active worker."""
        lease = await self.runner.run(self.store.lease, rid)
        try:
            meta = await self.runner.run(self.store.owned, "runs", rid, owner)
            if meta["state"] == "incompatible":
                raise AuditError("incompatible_run")
            rows = await self.runner.run(self.store.rows, rid, owner)
            for row in rows:
                if row["source_row_id"] in meta["selected_row_ids"] and row["processing_status"] == "running":
                    row.update(processing_status="interrupted", stopping_reason="interrupted", outcome="pending",
                               coverage_status="not_evaluated")
                    await self.runner.run(self.store.save_row, rid, row, owner)
            meta.update(state="queued", stage="waiting", active_row_id="")
            await self.runner.run(self.store.update_run, rid, owner, {**meta, "cancel_requested": False}, False)
        finally:
            os.close(lease)
        self.start(rid, owner)

    async def inspect_state(self, rid, owner):
        meta = await self.runner.run(self.store.owned, "runs", rid, owner)
        if meta["state"] == "running" and rid not in self.tasks.active_job_ids:
            try:
                lease = await self.runner.run(self.store.lease, rid)
            except AuditError:
                return meta  # A different live process owns the run.
            try:
                current = await self.runner.run(self.store.owned, "runs", rid, owner)
                if current["state"] == "running":
                    for row in await self.runner.run(self.store.rows, rid, owner):
                        if row["source_row_id"] in current["selected_row_ids"] and row["processing_status"] == "running":
                            row.update(processing_status="interrupted", coverage_status="not_evaluated", outcome="pending", stopping_reason="interrupted")
                            await self.runner.run(self.store.save_row, rid, row, owner)
                    current.update(state="interrupted", stage="interrupted", active_row_id="")
                    await self.save_meta(current)
                    meta = current
            finally:
                os.close(lease)
        return meta

    async def cancel(self, rid, owner):
        meta = await self.runner.run(self.store.owned, "runs", rid, owner)
        if meta["state"] not in {"running", "queued"}:
            raise AuditError("run_not_active")
        await self.runner.run(self.store.update_run, rid, owner, {"cancel_requested": True})
        await self.tasks.cancel(rid)

    async def aclose(self):
        self.closing = True
        await self.tasks.aclose()
