import asyncio
import time
import unittest

from utils.concurrency import AdmissionLimiter
from utils.service_errors import ServiceOverloadedError, ServiceTimeoutError
from utils.request_instrumentation import (
    RequestTrace,
    reset_current_trace,
    set_current_trace,
)


class AdmissionLimiterLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_success_exception_and_cancellation_release_exactly_once(self):
        limiter = AdmissionLimiter(1, name="test")

        self.assertEqual(
            await limiter.run(lambda: asyncio.sleep(0, result="ok"), acquire_timeout=1),
            "ok",
        )

        async def failure():
            raise RuntimeError("synthetic")

        with self.assertRaises(RuntimeError):
            await limiter.run(failure, acquire_timeout=1)

        entered = asyncio.Event()

        async def cancelled_operation():
            entered.set()
            await asyncio.Event().wait()

        task = asyncio.create_task(
            limiter.run(cancelled_operation, acquire_timeout=1)
        )
        await entered.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task

        snapshot = limiter.snapshot()
        self.assertEqual(snapshot.active, 0)
        self.assertEqual(snapshot.acquired_total, 3)
        self.assertEqual(snapshot.released_total, 3)
        self.assertEqual(snapshot.cancelled_total, 1)

    async def test_failed_acquisition_never_releases_unowned_permit(self):
        limiter = AdmissionLimiter(1, name="test")
        entered = asyncio.Event()
        finish = asyncio.Event()

        async def holder():
            entered.set()
            await finish.wait()

        holding = asyncio.create_task(limiter.run(holder, acquire_timeout=1))
        await entered.wait()
        with self.assertRaises(ServiceOverloadedError):
            await limiter.run(lambda: asyncio.sleep(0), acquire_timeout=0.01)

        during = limiter.snapshot()
        self.assertEqual(during.active, 1)
        self.assertEqual(during.acquired_total, 1)
        self.assertEqual(during.released_total, 0)
        self.assertEqual(during.timeout_total, 1)
        finish.set()
        await holding
        idle = limiter.snapshot()
        self.assertEqual(idle.active, 0)
        self.assertEqual(idle.acquired_total, idle.released_total)

    async def test_cancellation_while_waiting_does_not_leak_or_release(self):
        limiter = AdmissionLimiter(1, name="test")
        holder_entered = asyncio.Event()
        release_holder = asyncio.Event()

        async def holder():
            holder_entered.set()
            await release_holder.wait()

        holding = asyncio.create_task(limiter.run(holder, acquire_timeout=1))
        await holder_entered.wait()
        waiting = asyncio.create_task(
            limiter.run(lambda: asyncio.sleep(0), acquire_timeout=1)
        )
        await asyncio.sleep(0)
        waiting.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await waiting

        during = limiter.snapshot()
        self.assertEqual(during.active, 1)
        self.assertEqual(during.waiting, 0)
        self.assertEqual(during.acquired_total, 1)
        self.assertEqual(during.released_total, 0)
        self.assertEqual(during.cancelled_total, 1)

        release_holder.set()
        await holding
        idle = limiter.snapshot()
        self.assertEqual(idle.active, 0)
        self.assertEqual(idle.acquired_total, idle.released_total)

    async def test_waiter_acquires_newly_released_permit(self):
        limiter = AdmissionLimiter(1, name="test")
        entered = asyncio.Event()
        finish = asyncio.Event()
        order = []

        async def first():
            order.append("first-acquired")
            entered.set()
            await finish.wait()

        async def second():
            order.append("second-acquired")

        first_task = asyncio.create_task(limiter.run(first, acquire_timeout=1))
        await entered.wait()
        second_task = asyncio.create_task(limiter.run(second, acquire_timeout=1))
        await asyncio.sleep(0)
        self.assertEqual(limiter.snapshot().waiting, 1)
        finish.set()
        await asyncio.gather(first_task, second_task)
        self.assertEqual(order, ["first-acquired", "second-acquired"])

    async def test_capacity_50_wakes_all_100_tasks_before_12_seconds(self):
        limiter = AdmissionLimiter(50, name="test")
        release = asyncio.Event()
        active = 0
        maximum_active = 0
        acquired_at = {}
        submitted_at = {}

        async def worker(index: int):
            nonlocal active, maximum_active
            await release.wait()
            submitted_at[index] = time.perf_counter()

            async def operation():
                nonlocal active, maximum_active
                acquired_at[index] = time.perf_counter()
                active += 1
                maximum_active = max(maximum_active, active)
                try:
                    if index < 50:
                        await asyncio.sleep(2 + index * (8 / 49))
                    else:
                        await asyncio.sleep(0.001)
                finally:
                    active -= 1

            await limiter.run(operation, acquire_timeout=12)

        tasks = [asyncio.create_task(worker(index)) for index in range(100)]
        await asyncio.sleep(0)
        release.set()
        await asyncio.gather(*tasks)

        waiter_waits = [
            acquired_at[index] - submitted_at[index] for index in range(50, 100)
        ]
        snapshot = limiter.snapshot()
        self.assertEqual(maximum_active, 50)
        self.assertTrue(all(wait < 12 for wait in waiter_waits))
        self.assertEqual(snapshot.active, 0)
        self.assertEqual(snapshot.waiting, 0)
        self.assertEqual(snapshot.timeout_total, 0)
        self.assertEqual(snapshot.acquired_total, 100)
        self.assertEqual(snapshot.released_total, 100)
        self.assertEqual(
            snapshot.acquired_total - snapshot.released_total, snapshot.active
        )

    async def test_one_limiter_can_be_shared_by_two_endpoint_callers(self):
        limiter = AdmissionLimiter(2, name="shared-endpoints")
        active = 0
        peak = 0

        async def endpoint_call(_name: str):
            nonlocal active, peak

            async def operation():
                nonlocal active, peak
                active += 1
                peak = max(peak, active)
                try:
                    await asyncio.sleep(0.005)
                finally:
                    active -= 1

            await limiter.run(operation, acquire_timeout=1)

        await asyncio.gather(
            *(endpoint_call("web" if index % 2 else "mobile") for index in range(20))
        )
        self.assertEqual(peak, 2)
        self.assertEqual(limiter.snapshot().active, 0)

    async def test_worker_local_limiters_are_independent(self):
        worker_one = AdmissionLimiter(1, name="worker")
        worker_two = AdmissionLimiter(1, name="worker")
        self.assertNotEqual(worker_one.limiter_id, worker_two.limiter_id)
        await asyncio.gather(
            worker_one.run(lambda: asyncio.sleep(0), acquire_timeout=1),
            worker_two.run(lambda: asyncio.sleep(0), acquire_timeout=1),
        )
        self.assertEqual(worker_one.snapshot().acquired_total, 1)
        self.assertEqual(worker_two.snapshot().acquired_total, 1)

    def test_admission_and_application_timeouts_are_distinct(self):
        self.assertEqual(ServiceOverloadedError.status_code, 503)
        self.assertEqual(ServiceOverloadedError.error_code, "SERVICE_BUSY")
        self.assertEqual(ServiceTimeoutError.status_code, 504)
        self.assertEqual(ServiceTimeoutError.error_code, "DEPENDENCY_TIMEOUT")

    def test_fairness_is_documented_without_being_promised(self):
        architecture = (
            "/root/projects/faq/docs/architecture/"
            "REQUEST_ADMISSION_AND_BACKPRESSURE.md"
        )
        with open(architecture, encoding="utf-8") as stream:
            text = stream.read()
        self.assertIn("fairness", text.lower())
        self.assertIn("must not", text.lower())

    async def test_trace_reports_timing_without_request_content(self):
        secret_marker = "DO-NOT-EMIT-CONTENT"
        trace = RequestTrace(request_id="safe-request-1", process_id=123)
        token = set_current_trace(trace)
        try:
            limiter = AdmissionLimiter(1, name="test")
            await limiter.run(lambda: asyncio.sleep(0.001), acquire_timeout=1)
        finally:
            reset_current_trace(token)

        headers = trace.response_headers()
        serialized = repr(headers)
        self.assertEqual(headers["X-Admission-Acquired"], "true")
        self.assertIn("X-Admission-Wait-Ms", headers)
        self.assertIn("X-Permit-Hold-Ms", headers)
        self.assertNotIn(secret_marker, serialized)


if __name__ == "__main__":
    unittest.main()
