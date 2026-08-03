from __future__ import annotations

import asyncio
import unittest

from mass_answer_jobs import MassAnswerJobManager


class MassAnswerJobManagerTests(unittest.IsolatedAsyncioTestCase):
    async def test_tracks_job_until_completion(self):
        manager = MassAnswerJobManager()
        release = asyncio.Event()
        completed = asyncio.Event()

        async def operation():
            await release.wait()
            completed.set()

        manager.start("job-1", operation)
        self.assertEqual(manager.active_job_ids, {"job-1"})
        manager.set_progress("job-1", {"completed": 2})
        self.assertEqual(manager.get_progress("job-1"), {"completed": 2})
        release.set()
        await completed.wait()
        await asyncio.sleep(0)
        self.assertEqual(manager.active_job_ids, set())
        self.assertIsNone(manager.get_progress("job-1"))
        await manager.aclose()

    async def test_cancel_is_scoped_and_waits_for_cleanup(self):
        manager = MassAnswerJobManager()
        cancelled = asyncio.Event()

        async def operation():
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        manager.start("job-1", operation)
        await asyncio.sleep(0)
        self.assertTrue(await manager.cancel("job-1"))
        self.assertTrue(cancelled.is_set())
        self.assertEqual(manager.active_job_ids, set())
        await manager.aclose()

    async def test_shutdown_cancels_all_tracked_jobs(self):
        manager = MassAnswerJobManager()
        cleaned = []

        async def operation(job_id):
            try:
                await asyncio.Event().wait()
            finally:
                cleaned.append(job_id)

        manager.start("one", lambda: operation("one"))
        manager.start("two", lambda: operation("two"))
        await asyncio.sleep(0)
        await manager.aclose()
        self.assertEqual(set(cleaned), {"one", "two"})
        self.assertEqual(manager.active_job_ids, set())


if __name__ == "__main__":
    unittest.main()
