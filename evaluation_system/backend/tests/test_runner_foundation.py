from __future__ import annotations

import asyncio
import unittest
import uuid

from evaluation_system.backend.app.services.bounded_execution import (
    bounded_for_each,
    effective_session_concurrency,
)
from evaluation_system.backend.app.services.run_planning import (
    RunPlanError,
    build_run_session_specs,
    validate_run_shape,
)


class RunnerFoundationTests(unittest.IsolatedAsyncioTestCase):
    def test_run_types_enforce_their_logical_shape(self):
        validate_run_shape("DATASET_INSPECTION", 1, [2, 1])
        validate_run_shape("STABILITY_QUERY", 2, [1])
        validate_run_shape("STABILITY_SESSION", 2, [3])
        validate_run_shape("STABILITY_DATASET", 2, [2, 1])
        with self.assertRaises(RunPlanError):
            validate_run_shape("STABILITY_QUERY", 2, [2])
        with self.assertRaises(RunPlanError):
            validate_run_shape("STABILITY_SESSION", 2, [1, 1])

    async def test_session_concurrency_is_bounded(self):
        active = 0
        maximum = 0

        async def handler(_item):
            nonlocal active, maximum
            active += 1
            maximum = max(maximum, active)
            await asyncio.sleep(0.005)
            active -= 1

        await bounded_for_each(range(20), 3, handler)
        self.assertLessEqual(maximum, 3)

    async def test_fatal_worker_error_cancels_without_hanging(self):
        async def handler(item):
            if item == 2:
                raise RuntimeError("fatal")
            await asyncio.sleep(0.01)

        with self.assertRaises(ExceptionGroup):
            await asyncio.wait_for(
                bounded_for_each(range(20), 3, handler),
                timeout=1,
            )

    async def test_turns_inside_each_session_are_sequential(self):
        observed: dict[int, list[int]] = {}

        async def session_handler(session_id):
            for turn in (1, 2, 3):
                await asyncio.sleep(0)
                observed.setdefault(session_id, []).append(turn)

        await bounded_for_each(range(4), 2, session_handler)
        self.assertTrue(all(turns == [1, 2, 3] for turns in observed.values()))

    def test_stability_forces_concurrency_one(self):
        self.assertEqual(effective_session_concurrency("STABILITY_DATASET", 8), 1)
        self.assertEqual(effective_session_concurrency("DATASET_INSPECTION", 8), 8)

    def test_repetitions_have_fresh_unique_evaluation_keys(self):
        logical = uuid.uuid4()
        specs = build_run_session_specs([logical], 4)
        self.assertEqual([item.repeat_index for item in specs], [1, 2, 3, 4])
        self.assertEqual(len({item.evaluation_session_key for item in specs}), 4)


if __name__ == "__main__":
    unittest.main()
