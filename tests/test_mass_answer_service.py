from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace

from mass_answer_service import MassAnswerProcessor


class FakeAnsweringService:
    def __init__(self, *, delay=0.01, failing=None, hanging=None):
        self.delay = delay
        self.failing = set(failing or [])
        self.hanging = set(hanging or [])
        self.active = 0
        self.peak_active = 0
        self.calls = []

    async def answer(self, request):
        query = request.original_query
        self.calls.append(request)
        self.active += 1
        self.peak_active = max(self.peak_active, self.active)
        try:
            if query in self.hanging:
                await asyncio.sleep(1)
            else:
                await asyncio.sleep(self.delay)
            if query in self.failing:
                raise RuntimeError("synthetic internal detail")
            return SimpleNamespace(
                answer=f"answer:{query}",
                intent="general",
                rewritten_query=f"rewrite:{query}",
                related_questions=[],
            )
        finally:
            self.active -= 1


class MassAnswerProcessorTests(unittest.IsolatedAsyncioTestCase):
    async def test_preserves_order_while_respecting_concurrency_bound(self):
        service = FakeAnsweringService()
        processor = MassAnswerProcessor(
            answering_service=service,
            row_concurrency=3,
            row_timeout_seconds=1,
        )
        results = await processor.process(
            [str(index) for index in range(12)],
            selected_documents=["General_FAQ"],
        )
        self.assertEqual([row.index for row in results], list(range(12)))
        self.assertEqual(
            [row.answer for row in results],
            [f"answer:{index}" for index in range(12)],
        )
        self.assertEqual(service.peak_active, 3)

    async def test_one_failure_does_not_cancel_other_rows_or_leak_detail(self):
        service = FakeAnsweringService(failing={"bad"})
        processor = MassAnswerProcessor(
            answering_service=service,
            row_concurrency=2,
            row_timeout_seconds=1,
        )
        results = await processor.process(
            ["ok-1", "bad", "ok-2"], selected_documents=["General_FAQ"]
        )
        self.assertEqual(
            [row.status for row in results],
            ["success", "internal_error", "success"],
        )
        self.assertNotIn("synthetic", results[1].error_message)

    async def test_timeout_and_empty_query_are_per_row(self):
        service = FakeAnsweringService(hanging={"slow"})
        processor = MassAnswerProcessor(
            answering_service=service,
            row_concurrency=2,
            row_timeout_seconds=0.02,
        )
        results = await processor.process(
            ["slow", None, "ok"], selected_documents=["General_FAQ"]
        )
        self.assertEqual(
            [row.status for row in results],
            ["timeout", "invalid_input", "success"],
        )

    async def test_batch_requests_disable_history_and_persistence(self):
        service = FakeAnsweringService()
        processor = MassAnswerProcessor(
            answering_service=service,
            row_concurrency=1,
            row_timeout_seconds=1,
        )
        await processor.process(["q"], selected_documents=["General_FAQ"])
        request = service.calls[0]
        self.assertFalse(request.use_history)
        self.assertFalse(request.persist_agent_state)
        self.assertEqual(request.channel, "mass_answer")

    async def test_creates_only_fixed_worker_task_count(self):
        service = FakeAnsweringService()
        processor = MassAnswerProcessor(
            answering_service=service,
            row_concurrency=4,
            row_timeout_seconds=1,
        )
        original_create_task = asyncio.create_task
        created = 0

        def counting_create_task(coro):
            nonlocal created
            created += 1
            return original_create_task(coro)

        asyncio.create_task = counting_create_task
        try:
            await processor.process(
                [str(index) for index in range(100)],
                selected_documents=["General_FAQ"],
            )
        finally:
            asyncio.create_task = original_create_task
        self.assertEqual(created, 5)  # one producer plus four workers

    async def test_progress_reports_complete_consistent_counts(self):
        service = FakeAnsweringService(failing={"bad"}, hanging={"slow"})
        processor = MassAnswerProcessor(
            answering_service=service,
            row_concurrency=2,
            row_timeout_seconds=0.02,
        )
        progress = []
        await processor.process(
            ["ok", "bad", "slow"],
            selected_documents=["General_FAQ"],
            batch_id="synthetic-batch",
            progress_callback=progress.append,
        )
        final = progress[-1]
        self.assertEqual(final.completed_rows, 3)
        self.assertEqual(final.successful_rows, 1)
        self.assertEqual(final.failed_rows, 2)
        self.assertEqual(final.timed_out_rows, 1)
        self.assertEqual(final.queued_rows, 0)
        self.assertEqual(final.active_rows, 0)


if __name__ == "__main__":
    unittest.main()
