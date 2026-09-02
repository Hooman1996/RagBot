"""Bounded evaluation orchestration using the canonical AnsweringService."""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, func, select

from answering_service import AnswerRequestContext
from conversation_history import EVALUATION_EXECUTION_POLICY
from pipeline_observer import PipelineStage, PipelineStageResult
from utils.performance_config import PERFORMANCE_SETTINGS

from ..core_adapter.history import EvaluationConversationKey, EvaluationHistoryProvider
from ..db.models import DatasetTurn, Run, RunSession, RunTurn, StageResult
from ..services.divergence import ComparableTurn, analyze_stability
from ..services.events import NoOpEventBus, safe_error_code
from ..services.failures import is_infrastructure_error
from ..services.config_snapshot import build_config_snapshot
from ..services.bounded_execution import bounded_for_each, effective_session_concurrency
from ..tracing.collector import EvaluationTraceCollector


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


class EvaluationRunFailed(RuntimeError):
    """Content-free worker boundary exception safe for Celery logs."""

    def __init__(self, error_code: str):
        self.error_code = error_code
        super().__init__(f"evaluation run failed: {error_code}")


class EvaluationRunExecutor:
    def __init__(self, *, session_factory, answering_service, session_concurrency: int = 1, event_bus=None):
        if session_concurrency < 1:
            raise ValueError("session_concurrency must be positive")
        self.session_factory = session_factory
        self.answering_service = answering_service
        self.session_concurrency = session_concurrency
        self.event_bus = event_bus or NoOpEventBus()
        self.history_provider = EvaluationHistoryProvider(session_factory)

    async def execute(
        self,
        run_id: uuid.UUID,
        *,
        worker_task_id: str | None = None,
    ) -> None:
        task_id = worker_task_id or f"direct:{uuid.uuid4()}"
        run = await self._claim_run(run_id, task_id)
        if run is None:
            return
        await self.event_bus.publish(run_id, "run_started", {"run_id": str(run_id), "status": "RUNNING"})
        try:
            async with self.session_factory() as session:
                run_sessions = list(await session.scalars(
                    select(RunSession).where(
                        RunSession.run_id == run_id,
                        RunSession.status.in_(["PENDING", "RUNNING"]),
                    ).order_by(RunSession.repeat_index, RunSession.dataset_session_id)
                ))
            concurrency = effective_session_concurrency(run.run_type, self.session_concurrency)
            await bounded_for_each(
                run_sessions, concurrency,
                lambda item: self._execute_session(run, item),
            )
            final_status = await self._finish_run(run_id)
            if run.run_type.startswith("STABILITY"):
                await self._store_divergence(run_id)
            event_name = "run_cancelled" if final_status == "CANCELLED" else "run_completed"
            await self.event_bus.publish(
                run_id,
                event_name,
                {"run_id": str(run_id), "status": final_status},
            )
        except Exception as exc:
            error_code = safe_error_code(
                getattr(exc, "error_code", type(exc).__name__),
                fallback="EVALUATION_RUN_ERROR",
            )
            try:
                await self._fail_run(run_id, error_code)
            except Exception:
                pass
            await self.event_bus.publish(run_id, "run_failed", {
                "run_id": str(run_id), "status": "FAILED",
                "error_code": error_code,
            })
            raise EvaluationRunFailed(error_code) from None

    async def _claim_run(
        self, run_id: uuid.UUID, worker_task_id: str
    ) -> Run | None:
        async with self.session_factory() as session:
            run = await session.scalar(select(Run).where(Run.id == run_id).with_for_update())
            if run is None:
                return None
            if run.status == "PENDING":
                run.status = "RUNNING"
                run.started_at = now_utc()
                run.worker_task_id = worker_task_id
                selected = list(
                    (run.config_snapshot.get("retrieval") or {}).get(
                        "knowledge_sources"
                    ) or []
                )
                run.config_snapshot = build_config_snapshot(
                    answering_service=self.answering_service,
                    selected_documents=selected,
                )
                run.git_commit_sha = run.config_snapshot.get("git_commit_sha")
            elif not (
                run.status == "RUNNING"
                and run.worker_task_id == worker_task_id
            ):
                return None
            run.heartbeat_at = now_utc()
            await session.commit()
            return run

    async def _execute_session(self, run: Run, run_session: RunSession) -> None:
        async with self.session_factory() as session:
            row = await session.get(RunSession, run_session.id, with_for_update=True)
            if row.status not in {"PENDING", "RUNNING"}:
                return
            row.status = "RUNNING"
            row.started_at = row.started_at or now_utc()
            await session.commit()
        await self.event_bus.publish(run.id, "session_started", {
            "run_id": str(run.id), "run_session_id": str(run_session.id), "status": "RUNNING",
        })
        async with self.session_factory() as session:
            source_turns = list(await session.scalars(
                select(DatasetTurn).where(
                    DatasetTurn.dataset_session_id == run_session.dataset_session_id
                ).order_by(DatasetTurn.turn_index)
            ))
        fallback_count = 0
        error_count = 0
        infrastructure_error_count = 0
        total_latency = 0.0
        selected_documents = list((run.config_snapshot.get("retrieval") or {}).get("knowledge_sources") or [])
        for source in source_turns:
            if await self._cancel_requested(run.id):
                await self._cancel_session(run_session.id)
                return
            turn, should_execute = await self._claim_turn(run_session.id, source)
            if not should_execute:
                fallback_count += int(bool(turn.fallback_used))
                error_count += int(turn.status == "ERROR")
                infrastructure_error_count += int(bool(turn.infrastructure_error))
                total_latency += float(turn.total_latency_ms or 0.0)
                await self._publish_progress(run.id)
                continue
            await self.event_bus.publish(run.id, "turn_started", {
                "run_id": str(run.id), "run_session_id": str(run_session.id),
                "run_turn_id": str(turn.id), "status": "RUNNING",
            })
            collector = EvaluationTraceCollector()
            turn_failed = False
            turn_started = time.perf_counter()
            key = EvaluationConversationKey(
                run_session_id=run_session.id,
                run_turn_id=turn.id,
                turn_index=source.turn_index,
                evaluation_session_key=run_session.evaluation_session_key,
            )
            try:
                result = await self.answering_service.answer(
                    AnswerRequestContext(
                        original_query=source.query,
                        selected_documents=tuple(selected_documents),
                        session_id=None,
                        conversation_key=key,
                        channel="evaluation",
                        use_history=True,
                        persist_agent_state=True,
                        include_related_questions=True,
                        timeout_seconds=PERFORMANCE_SETTINGS.application_request_timeout_seconds,
                        apply_mobile_empty_answer_fallback=True,
                    ),
                    history_provider=self.history_provider,
                    observer=collector,
                    execution_policy=EVALUATION_EXECUTION_POLICY,
                )
                self._ensure_all_stages(collector)
                await self._complete_turn(turn.id, result, collector)
                fallback_count += bool(result.fallback_reason)
                turn_latency = result.timings_ms.get("total", 0.0)
                total_latency += turn_latency
                for stage in collector.records:
                    await self.event_bus.publish(run.id, "stage_completed", {
                        "run_id": str(run.id), "run_session_id": str(run_session.id),
                        "run_turn_id": str(turn.id), "stage_name": stage.stage.value,
                        "status": stage.status, "duration_ms": stage.duration_ms,
                        "error_code": stage.error_code,
                    })
            except Exception as exc:
                turn_failed = True
                error_count += 1
                infrastructure = is_infrastructure_error(exc)
                infrastructure_error_count += int(infrastructure)
                turn_latency = (time.perf_counter() - turn_started) * 1000
                total_latency += turn_latency
                await self._error_turn(
                    turn.id,
                    exc,
                    collector,
                    infrastructure=infrastructure,
                    total_latency_ms=turn_latency,
                )
                for stage in collector.records:
                    await self.event_bus.publish(run.id, "stage_completed", {
                        "run_id": str(run.id),
                        "run_session_id": str(run_session.id),
                        "run_turn_id": str(turn.id),
                        "stage_name": stage.stage.value,
                        "status": stage.status,
                        "duration_ms": stage.duration_ms,
                        "error_code": stage.error_code,
                    })
            await self.event_bus.publish(run.id, "turn_completed", {
                "run_id": str(run.id), "run_session_id": str(run_session.id),
                "run_turn_id": str(turn.id), "status": "ERROR" if turn_failed else "COMPLETED",
            })
            await self._publish_progress(run.id)
        async with self.session_factory() as session:
            row = await session.get(RunSession, run_session.id, with_for_update=True)
            row.status = "COMPLETED" if error_count == 0 else "FAILED"
            row.fallback_count = fallback_count
            row.error_count = error_count
            row.infrastructure_error_count = infrastructure_error_count
            row.total_latency_ms = total_latency
            row.finished_at = now_utc()
            await session.commit()
        await self._publish_progress(run.id)
        await self.event_bus.publish(run.id, "session_completed", {
            "run_id": str(run.id), "run_session_id": str(run_session.id),
            "status": "COMPLETED" if error_count == 0 else "FAILED",
            "duration_ms": total_latency,
        })

    async def _claim_turn(
        self, run_session_id: uuid.UUID, source: DatasetTurn
    ) -> tuple[RunTurn, bool]:
        async with self.session_factory() as session:
            turn = await session.scalar(
                select(RunTurn).where(
                    RunTurn.run_session_id == run_session_id,
                    RunTurn.turn_index == source.turn_index,
                ).with_for_update()
            )
            if turn is None:
                turn = RunTurn(
                    run_session_id=run_session_id, dataset_turn_id=source.id,
                    turn_index=source.turn_index, request_id=uuid.uuid4(),
                    raw_query=source.query, status="RUNNING", started_at=now_utc(),
                    metadata_json={},
                )
                session.add(turn)
            elif turn.status in {"COMPLETED", "ERROR", "CANCELLED"}:
                return turn, False
            else:
                turn.attempt_count += 1
                turn.status = "RUNNING"
                turn.started_at = now_utc()
                turn.finished_at = None
                turn.infrastructure_error = False
                turn.error_code = None
                turn.error_data = None
                turn.total_latency_ms = None
                metadata = dict(turn.metadata_json or {})
                metadata.pop("agent_state_after", None)
                turn.metadata_json = metadata
                await session.execute(
                    delete(StageResult).where(StageResult.run_turn_id == turn.id)
                )
            await session.commit()
            return turn, True

    @staticmethod
    def _ensure_all_stages(collector: EvaluationTraceCollector) -> None:
        present = {record.stage for record in collector.records}
        for stage in PipelineStage:
            if stage not in present:
                collector.record(PipelineStageResult(
                    stage=stage, status="SKIPPED", metrics={"reason": "NOT_APPLICABLE"}, duration_ms=0.0
                ))

    async def _persist_stages(self, session, turn_id: uuid.UUID, collector: EvaluationTraceCollector) -> None:
        for record in collector.records:
            session.add(StageResult(
                run_turn_id=turn_id, stage_name=record.stage.value,
                stage_order=record.stage_order, status=record.status,
                input_hash=record.input_hash, output_hash=record.output_hash,
                duration_ms=record.duration_ms, input_data=record.input_data,
                output_data=record.output_data, metrics=record.metrics,
                error_code=record.error_code, error_data=record.error_data,
            ))

    async def _complete_turn(self, turn_id, result, collector):
        context_stage = collector.get(PipelineStage.CONTEXT_SELECTION)
        state_after = await self.history_provider.pending_state(turn_id)
        async with self.session_factory() as session:
            turn = await session.get(RunTurn, turn_id, with_for_update=True)
            turn.normalized_query = result.normalized_query
            turn.history_before_hash = result.history_before_hash
            turn.history_after_hash = result.history_after_hash
            turn.actual_intent = result.intent
            turn.intent_score = result.intent_details.get("confidence")
            turn.rewritten_query = result.rewritten_query
            turn.selected_context_hash = (
                context_stage.metrics.get("selected_context_hash")
                if context_stage
                else None
            )
            turn.actual_answer = result.answer
            turn.fallback_used = bool(result.fallback_reason)
            turn.fallback_reason = result.fallback_reason
            turn.status = "COMPLETED"
            turn.total_latency_ms = result.timings_ms.get("total")
            turn.finished_at = now_utc()
            metadata = dict(turn.metadata_json or {})
            metadata["agent_state_after"] = state_after
            turn.metadata_json = metadata
            await self._persist_stages(session, turn_id, collector)
            await session.commit()
        await self.history_provider.discard_pending_state(turn_id)

    async def _error_turn(
        self,
        turn_id,
        exc,
        collector,
        *,
        infrastructure: bool,
        total_latency_ms: float,
    ):
        await self.history_provider.discard_pending_state(turn_id)
        error_code = safe_error_code(
            getattr(exc, "error_code", type(exc).__name__),
            fallback="EVALUATION_TURN_ERROR",
        )
        present = {record.stage for record in collector.records}
        failed_stage = next((stage for stage in PipelineStage if stage not in present), PipelineStage.GENERATION)
        collector.record(PipelineStageResult(
            stage=failed_stage,
            status="ERROR",
            error_code=error_code,
            error_data={"error_type": type(exc).__name__},
        ))
        self._ensure_all_stages(collector)
        async with self.session_factory() as session:
            turn = await session.get(RunTurn, turn_id, with_for_update=True)
            turn.status = "ERROR"
            turn.infrastructure_error = infrastructure
            turn.error_code = error_code
            turn.error_data = {"error_type": type(exc).__name__}
            turn.total_latency_ms = total_latency_ms
            turn.finished_at = now_utc()
            metadata = dict(turn.metadata_json or {})
            metadata.update({
                "error_code": error_code,
                "error_type": type(exc).__name__,
                "infrastructure_error": infrastructure,
            })
            turn.metadata_json = metadata
            await self._persist_stages(session, turn_id, collector)
            await session.commit()

    async def _cancel_requested(self, run_id) -> bool:
        async with self.session_factory() as session:
            run = await session.get(Run, run_id)
            return bool(run.cancel_requested_at)

    async def _cancel_session(self, run_session_id):
        async with self.session_factory() as session:
            row = await session.get(RunSession, run_session_id, with_for_update=True)
            row.status = "CANCELLED"; row.finished_at = now_utc()
            await session.commit()

    async def _finish_run(self, run_id):
        async with self.session_factory() as session:
            sessions = list(await session.scalars(select(RunSession).where(RunSession.run_id == run_id)))
            turns = list(await session.scalars(
                select(RunTurn).join(RunSession, RunTurn.run_session_id == RunSession.id).where(RunSession.run_id == run_id)
            ))
            run = await session.get(Run, run_id, with_for_update=True)
            cancelled = any(item.status == "CANCELLED" for item in sessions)
            run.status = "CANCELLED" if cancelled else "COMPLETED"
            run.completed_sessions = sum(item.status in {"COMPLETED", "FAILED"} for item in sessions)
            run.completed_turns = sum(item.status in {"COMPLETED", "ERROR"} for item in turns)
            run.fallback_count = sum(item.fallback_used for item in turns)
            run.error_count = sum(item.status == "ERROR" for item in turns)
            run.infrastructure_error_count = sum(item.infrastructure_error for item in turns)
            run.finished_at = now_utc()
            await session.commit()
            return run.status

    async def _publish_progress(self, run_id):
        async with self.session_factory() as session:
            run = await session.get(Run, run_id, with_for_update=True)
            completed_turns = await session.scalar(
                select(func.count(RunTurn.id)).join(
                    RunSession, RunTurn.run_session_id == RunSession.id
                ).where(
                    RunSession.run_id == run_id,
                    RunTurn.status.in_(["COMPLETED", "ERROR"]),
                )
            )
            completed_sessions = await session.scalar(
                select(func.count(RunSession.id)).where(
                    RunSession.run_id == run_id,
                    RunSession.status.in_(["COMPLETED", "FAILED"]),
                )
            )
            turns = list(await session.scalars(
                select(RunTurn).join(
                    RunSession, RunTurn.run_session_id == RunSession.id
                ).where(RunSession.run_id == run_id)
            ))
            run.completed_turns = int(completed_turns or 0)
            run.completed_sessions = int(completed_sessions or 0)
            run.fallback_count = sum(item.fallback_used for item in turns)
            run.error_count = sum(item.status == "ERROR" for item in turns)
            run.infrastructure_error_count = sum(item.infrastructure_error for item in turns)
            run.heartbeat_at = now_utc()
            await session.commit()
        await self.event_bus.publish(run_id, "progress", {
            "run_id": str(run_id), "status": run.status,
            "completed_turns": int(completed_turns or 0),
            "total_turns": run.total_turns,
            "completed_sessions": int(completed_sessions or 0),
            "total_sessions": run.total_sessions,
        })

    async def _fail_run(self, run_id, error_code):
        async with self.session_factory() as session:
            run = await session.get(Run, run_id, with_for_update=True)
            if run:
                run.status = "FAILED"; run.finished_at = now_utc()
                run.failure_code = error_code
                metadata = dict(run.metadata_json or {}); metadata["failure_code"] = error_code
                run.metadata_json = metadata
                await session.commit()

    async def _store_divergence(self, run_id):
        async with self.session_factory() as session:
            run_sessions = list(await session.scalars(select(RunSession).where(RunSession.run_id == run_id)))
            comparable: list[ComparableTurn] = []
            for run_session in run_sessions:
                turns = list(await session.scalars(select(RunTurn).where(RunTurn.run_session_id == run_session.id)))
                for turn in turns:
                    stages = list(await session.scalars(select(StageResult).where(StageResult.run_turn_id == turn.id)))
                    stage_hashes = {stage.stage_name: stage.output_hash for stage in stages}
                    generation_stage = next(
                        (
                            stage
                            for stage in stages
                            if stage.stage_name == "GENERATION"
                        ),
                        None,
                    )
                    prompt_stage = next(
                        (
                            stage
                            for stage in stages
                            if stage.stage_name == "PROMPT_BUILD"
                        ),
                        None,
                    )
                    comparable.append(ComparableTurn(
                        run_session_id=run_session.id,
                        logical_session_id=run_session.dataset_session_id,
                        repeat_index=run_session.repeat_index,
                        turn_index=turn.turn_index,
                        stage_outputs=stage_hashes,
                        normalized_query=turn.normalized_query,
                        intent=turn.actual_intent,
                        rewritten_query=turn.rewritten_query,
                        context_hash=turn.selected_context_hash,
                        answer_hash=(
                            (generation_stage.metrics or {}).get("answer_hash")
                            if generation_stage is not None
                            else None
                        ),
                        fallback_used=turn.fallback_used,
                        completed=turn.status == "COMPLETED",
                        prompt_hash=(
                            (prompt_stage.metrics or {}).get("prompt_hash")
                            if prompt_stage is not None
                            else None
                        ),
                    ))
            summaries = analyze_stability(comparable)
            for run_session in run_sessions:
                summary = summaries.get(run_session.dataset_session_id)
                if summary:
                    run_session.first_divergent_turn = summary.first_divergent_turn
                    run_session.first_divergent_stage = summary.first_divergent_stage
                    metadata = dict(run_session.metadata_json or {})
                    metadata["stability"] = summary.as_dict()
                    run_session.metadata_json = metadata
            await session.commit()
