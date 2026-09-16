"""Bounded evaluation orchestration through the RagBot internal HTTP API."""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, func, select

from ..clients.ragbot import (
    EvaluationStageResponse,
    EvaluationTurnResponse,
    RagBotClientError,
)
from ..db.models import DatasetTurn, Run, RunSession, RunTurn, StageResult
from ..services.divergence import ComparableTurn, analyze_stability
from ..services.error_codes import safe_error_code
from ..services.bounded_execution import bounded_for_each, effective_session_concurrency
from ..services.history_state import exact_agent_state_from_turns
from ..services.pipeline_contract import CANONICAL_STAGE_NAMES, STAGE_ORDER


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


class EvaluationRunFailed(RuntimeError):
    """Content-free worker boundary exception safe for worker logs."""

    def __init__(self, error_code: str):
        self.error_code = error_code
        super().__init__(f"evaluation run failed: {error_code}")


class EvaluationRunExecutor:
    def __init__(
        self,
        *,
        session_factory,
        ragbot_client=None,
        session_concurrency: int = 1,
    ):
        if session_concurrency < 1:
            raise ValueError("session_concurrency must be positive")
        if ragbot_client is None:
            raise ValueError("ragbot_client is required")
        self.session_factory = session_factory
        self.ragbot_client = ragbot_client
        self.session_concurrency = session_concurrency

    async def execute(
        self,
        run_id: uuid.UUID,
        *,
        worker_task_id: str | None = None,
    ) -> None:
        task_id = worker_task_id or f"direct:{uuid.uuid4()}"
        try:
            run = await self._claim_run(run_id, task_id)
            if run is None:
                return
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
            await self._finish_run(run_id)
            if run.run_type.startswith("STABILITY"):
                await self._store_divergence(run_id)
        except Exception as exc:
            error_code = safe_error_code(
                getattr(exc, "error_code", type(exc).__name__),
                fallback="EVALUATION_RUN_ERROR",
            )
            try:
                await self._fail_run(run_id, error_code, task_id)
            except Exception:
                pass
            raise EvaluationRunFailed(error_code) from None

    async def _claim_run(
        self, run_id: uuid.UUID, worker_task_id: str
    ) -> Run | None:
        selected: list[str] = []
        snapshot_pending = False
        async with self.session_factory() as session:
            run = await session.scalar(select(Run).where(Run.id == run_id).with_for_update())
            if run is None:
                return None
            if run.status == "PENDING":
                run.status = "RUNNING"
                run.started_at = run.started_at or now_utc()
                run.worker_task_id = worker_task_id
            elif not (
                run.status == "RUNNING"
                and run.worker_task_id == worker_task_id
            ):
                return None
            snapshot_pending = bool(
                (run.config_snapshot or {}).get("runtime_snapshot_pending")
            )
            if snapshot_pending:
                selected = list(
                    ((run.config_snapshot or {}).get("retrieval") or {}).get(
                        "knowledge_sources"
                    ) or []
                )
            run.heartbeat_at = now_utc()
            await session.commit()

        if not snapshot_pending:
            return run

        # Remote I/O happens after the ownership transaction has committed.
        snapshot = await self.ragbot_client.runtime_snapshot(selected)
        async with self.session_factory() as session:
            run = await session.scalar(
                select(Run).where(Run.id == run_id).with_for_update()
            )
            if not (
                run is not None
                and run.status == "RUNNING"
                and run.worker_task_id == worker_task_id
            ):
                return None
            run.config_snapshot = snapshot.config_snapshot
            run.git_commit_sha = snapshot.git_commit_sha
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
                await self._update_progress(run.id)
                continue
            turn_started = time.perf_counter()
            try:
                state_before = await self._state_before(
                    run_session.id, source.turn_index
                )
                result = await self._evaluate_remote_turn(
                    run_session, turn, source, selected_documents, state_before
                )
                observed_latency = (time.perf_counter() - turn_started) * 1000
                turn_latency = float(result.timings_ms.get("total", observed_latency))
                total_latency += turn_latency
                if result.status == "COMPLETED":
                    await self._complete_turn(turn.id, result)
                    fallback_count += bool(result.fallback_reason)
                else:
                    error_count += 1
                    infrastructure_error_count += int(result.infrastructure_error)
                    await self._structured_error_turn(
                        turn.id, result=result, total_latency_ms=turn_latency
                    )
            except Exception as exc:
                error_count += 1
                infrastructure = bool(
                    getattr(exc, "infrastructure_error", True)
                )
                infrastructure_error_count += int(infrastructure)
                turn_latency = (time.perf_counter() - turn_started) * 1000
                total_latency += turn_latency
                stages = self._transport_error_stages(exc)
                await self._transport_error_turn(
                    turn.id,
                    exc,
                    stages,
                    infrastructure=infrastructure,
                    total_latency_ms=turn_latency,
                )
            await self._update_progress(run.id)
        async with self.session_factory() as session:
            row = await session.get(RunSession, run_session.id, with_for_update=True)
            row.status = "COMPLETED" if error_count == 0 else "FAILED"
            row.fallback_count = fallback_count
            row.error_count = error_count
            row.infrastructure_error_count = infrastructure_error_count
            row.total_latency_ms = total_latency
            row.finished_at = now_utc()
            await session.commit()
        await self._update_progress(run.id)

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

    async def _state_before(
        self, run_session_id: uuid.UUID, turn_index: int
    ) -> dict | None:
        async with self.session_factory() as session:
            turns = list(await session.scalars(
                select(RunTurn).where(
                    RunTurn.run_session_id == run_session_id,
                    RunTurn.turn_index < turn_index,
                    RunTurn.status == "COMPLETED",
                ).order_by(RunTurn.turn_index)
            ))
        return exact_agent_state_from_turns(turns)

    async def _evaluate_remote_turn(
        self, run_session, turn, source, selected_documents, state_before
    ) -> EvaluationTurnResponse:
        return await self.ragbot_client.evaluate_turn(
            evaluation_session_key=run_session.evaluation_session_key,
            evaluation_turn_id=turn.id,
            turn_index=source.turn_index,
            query=source.query,
            documents=selected_documents,
            agent_state_before=state_before,
        )

    async def _persist_stages(
        self,
        session,
        turn_id: uuid.UUID,
        stages: list[EvaluationStageResponse],
    ) -> None:
        for record in stages:
            session.add(StageResult(
                run_turn_id=turn_id, stage_name=record.stage_name,
                stage_order=record.stage_order, status=record.status,
                input_hash=record.input_hash, output_hash=record.output_hash,
                duration_ms=record.duration_ms, input_data=record.input_data,
                output_data=record.output_data, metrics=record.metrics,
                error_code=record.error_code, error_data=record.error_data,
            ))

    async def _complete_turn(self, turn_id, result: EvaluationTurnResponse):
        context_stage = next(
            (stage for stage in result.stages if stage.stage_name == "CONTEXT_SELECTION"),
            None,
        )
        if result.agent_state_after is None:
            raise RagBotClientError("RAGBOT_INVALID_RESPONSE", "missing_success_state")
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
            metadata["agent_state_after"] = result.agent_state_after
            turn.metadata_json = metadata
            await self._persist_stages(session, turn_id, result.stages)
            await session.commit()

    async def _structured_error_turn(
        self,
        turn_id,
        *,
        result: EvaluationTurnResponse,
        total_latency_ms: float,
    ):
        error_code = safe_error_code(
            result.error_code,
            fallback="EVALUATION_TURN_ERROR",
        )
        async with self.session_factory() as session:
            turn = await session.get(RunTurn, turn_id, with_for_update=True)
            turn.status = "ERROR"
            turn.infrastructure_error = result.infrastructure_error
            turn.error_code = error_code
            turn.error_data = result.error_data
            turn.total_latency_ms = total_latency_ms
            turn.finished_at = now_utc()
            metadata = dict(turn.metadata_json or {})
            metadata.pop("agent_state_after", None)
            metadata.update({
                "error_code": error_code,
                "infrastructure_error": result.infrastructure_error,
            })
            turn.metadata_json = metadata
            await self._persist_stages(session, turn_id, result.stages)
            await session.commit()

    @staticmethod
    def _transport_error_stages(exc: Exception) -> list[EvaluationStageResponse]:
        error_code = safe_error_code(
            getattr(exc, "error_code", None), fallback="EVALUATION_TURN_ERROR"
        )
        error_data = getattr(exc, "error_data", {"failure_kind": "worker_boundary"})
        return [
            EvaluationStageResponse(
                stage_name=name,
                stage_order=STAGE_ORDER[name],
                status="ERROR" if index == 1 else "SKIPPED",
                input_hash=None,
                output_hash=None,
                duration_ms=0.0,
                input_data=None,
                output_data=None,
                metrics={} if index == 1 else {"reason": "RAGBOT_TRANSPORT_FAILURE"},
                error_code=error_code if index == 1 else None,
                error_data=error_data if index == 1 else None,
            )
            for index, name in enumerate(CANONICAL_STAGE_NAMES, start=1)
        ]

    async def _transport_error_turn(
        self,
        turn_id,
        exc,
        stages: list[EvaluationStageResponse],
        *,
        infrastructure: bool,
        total_latency_ms: float,
    ) -> None:
        error_code = safe_error_code(
            getattr(exc, "error_code", None), fallback="EVALUATION_TURN_ERROR"
        )
        error_data = getattr(exc, "error_data", {"failure_kind": "worker_boundary"})
        async with self.session_factory() as session:
            turn = await session.get(RunTurn, turn_id, with_for_update=True)
            turn.status = "ERROR"
            turn.infrastructure_error = infrastructure
            turn.error_code = error_code
            turn.error_data = error_data
            turn.total_latency_ms = total_latency_ms
            turn.finished_at = now_utc()
            metadata = dict(turn.metadata_json or {})
            metadata.pop("agent_state_after", None)
            metadata.update({
                "error_code": error_code,
                "infrastructure_error": infrastructure,
            })
            turn.metadata_json = metadata
            await self._persist_stages(session, turn_id, stages)
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

    async def _update_progress(self, run_id):
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

    async def _fail_run(self, run_id, error_code, worker_task_id=None):
        async with self.session_factory() as session:
            run = await session.get(Run, run_id, with_for_update=True)
            if run and run.status == "RUNNING" and (
                worker_task_id is None or run.worker_task_id == worker_task_id
            ):
                run.status = "FAILED"; run.finished_at = now_utc()
                run.failure_code = error_code
                metadata = dict(run.metadata_json or {}); metadata["failure_code"] = error_code
                run.metadata_json = metadata
                await session.commit()
                return True
            return False

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
