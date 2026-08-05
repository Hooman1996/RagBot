from __future__ import annotations

import asyncio
import csv
import dataclasses
import importlib.util
import json
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

import httpx


MODULE_PATH = (
    Path(__file__).resolve().parents[2]
    / "benchmarks"
    / "load"
    / "mobile_talk_load_test.py"
)
SPEC = importlib.util.spec_from_file_location("mobile_talk_load_test", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
load_test = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = load_test
SPEC.loader.exec_module(load_test)


def record(
    *,
    failure_class: str = load_test.SUCCESS,
    elapsed_ms: float = 100.0,
    status: int | None = 200,
    exception_type: str | None = None,
    virtual_user: int = 1,
    wave: int = 1,
    query_text: str = "synthetic query",
    answer_text: str = "synthetic answer",
    response_schema_valid: bool = True,
    national_code: str = "stglt_reserved_001",
) -> load_test.RequestRecord:
    return load_test.RequestRecord(
        run_id="run",
        wave_number=wave,
        virtual_user_number=virtual_user,
        request_number=wave,
        scenario="fixture",
        session_id=f"00000000-0000-0000-0000-{virtual_user:012d}",
        national_code=national_code,
        national_code_hash=f"sha256:{virtual_user:016d}",
        query_text=query_text,
        request_start_timestamp="2026-07-28T00:00:00+00:00",
        request_end_timestamp="2026-07-28T00:00:01+00:00",
        start_perf_counter_ns=1_000_000_000,
        end_perf_counter_ns=1_000_000_000 + int(elapsed_ms * 1_000_000),
        client_elapsed_ms=elapsed_ms,
        http_status=status,
        failure_class=failure_class,
        exception_type=exception_type,
        answer_text=answer_text,
        answer_characters=len(answer_text),
        answer_word_count=len(answer_text.split()),
        answer_is_empty=response_schema_valid and answer_text == "",
        response_schema_valid=response_schema_valid,
    )


class StatisticsTests(unittest.TestCase):
    def test_percentile_uses_r7_linear_interpolation(self):
        values = [1.0, 2.0, 3.0, 4.0]

        self.assertEqual(load_test.percentile(values, 0), 1.0)
        self.assertEqual(load_test.percentile(values, 50), 2.5)
        self.assertAlmostEqual(load_test.percentile(values, 75), 3.25)
        self.assertEqual(load_test.percentile(values, 100), 4.0)

    def test_empty_result_handling(self):
        summary = load_test.summarize_records([], expected_attempts=5)

        self.assertEqual(summary["total_attempts"], 0)
        self.assertEqual(summary["completion_rate"], 0.0)
        self.assertIsNone(summary["successful_latency_ms"]["p95_ms"])
        self.assertEqual(summary["excluded_from_success_percentiles"], 0)

    def test_mixed_successes_and_failures_show_excluded_count(self):
        records = [
            record(elapsed_ms=100),
            record(elapsed_ms=300, virtual_user=2),
            record(
                failure_class=load_test.HTTP_5XX,
                elapsed_ms=50,
                status=500,
                virtual_user=3,
            ),
        ]

        summary = load_test.summarize_records(records, expected_attempts=4)

        self.assertEqual(summary["successful_responses"], 2)
        self.assertEqual(summary["failed_responses"], 1)
        self.assertEqual(summary["excluded_from_success_percentiles"], 1)
        self.assertEqual(summary["successful_latency_ms"]["mean_ms"], 200)
        self.assertEqual(summary["successful_latency_ms"]["maximum_ms"], 300)
        self.assertEqual(summary["all_completed_attempt_latency_ms"]["count"], 3)
        self.assertEqual(summary["completion_rate"], 0.75)
        self.assertEqual(summary["http_5xx"], 1)


class ClassificationTests(unittest.TestCase):
    def test_timeout_classification(self):
        request = httpx.Request("POST", "https://staging.example/v1/talk")

        cases = [
            (httpx.ReadTimeout("read", request=request), load_test.CLIENT_READ_TIMEOUT),
            (
                httpx.ConnectTimeout("connect", request=request),
                load_test.CLIENT_CONNECT_TIMEOUT,
            ),
            (httpx.WriteTimeout("write", request=request), load_test.CLIENT_WRITE_TIMEOUT),
            (httpx.PoolTimeout("pool", request=request), load_test.POOL_TIMEOUT),
        ]
        for exception, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(load_test.classify_exception(exception)[0], expected)

    def test_limiter_and_application_timeout_classification(self):
        limiter = httpx.Response(
            503,
            json={"errorCode": "SERVICE_BUSY"},
            request=httpx.Request("POST", "https://staging.example/v1/talk"),
        )
        deadline = httpx.Response(
            504,
            json={"errorCode": "DEPENDENCY_TIMEOUT"},
            request=httpx.Request("POST", "https://staging.example/v1/talk"),
        )

        self.assertEqual(
            load_test.classify_response(limiter),
            (load_test.LIMITER_REJECTION, "limiter"),
        )
        self.assertEqual(
            load_test.classify_response(deadline),
            (load_test.APPLICATION_DEADLINE, "application"),
        )

    def test_plain_503_is_not_misclassified_as_limiter_rejection(self):
        response = httpx.Response(
            503,
            json={"detail": "unavailable"},
            request=httpx.Request("POST", "https://staging.example/v1/talk"),
        )

        self.assertEqual(load_test.classify_response(response)[0], load_test.HTTP_5XX)


class IdentityTests(unittest.TestCase):
    def test_deterministic_unique_session_generation(self):
        first = [
            load_test.deterministic_session_id(7, "fixture", index)
            for index in range(1, 4)
        ]
        second = [
            load_test.deterministic_session_id(7, "fixture", index)
            for index in range(1, 4)
        ]

        self.assertEqual(first, second)
        self.assertEqual(len(set(first)), 3)
        self.assertTrue(all(len(value) == 36 for value in first))

    def test_checksum_validation_is_available_for_fixture_auditing(self):
        self.assertTrue(load_test.is_valid_iranian_national_code("0084575948"))
        self.assertFalse(load_test.is_valid_iranian_national_code("0084575949"))
        self.assertFalse(load_test.is_valid_iranian_national_code("1111111111"))

    def test_fixture_identity_is_never_serialized(self):
        full_code = "stglt_reserved_001"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = root / "fixture.json"
            fixture.write_text(
                json.dumps(
                    {
                        "identities": [
                            {"alias": "vu-1", "national_code": full_code}
                        ]
                    }
                ),
                encoding="utf-8",
            )
            identities, scenarios = load_test.load_fixture(fixture)
            output_record = record()
            jsonl_path = root / "requests.jsonl"
            csv_path = root / "requests.csv"
            load_test.write_jsonl(jsonl_path, [output_record])
            load_test.write_csv(csv_path, [output_record])

            self.assertEqual(identities[0].national_code, full_code)
            self.assertEqual(scenarios, {})
            self.assertNotIn(full_code, jsonl_path.read_text(encoding="utf-8"))
            self.assertNotIn(full_code, csv_path.read_text(encoding="utf-8"))

    def test_generated_national_code_mode_is_rejected(self):
        config = load_test.Config(
            base_url="https://staging.example",
            input_file=Path("fixture.json"),
            national_code_mode="iranian-checksum",
        )

        with self.assertRaises(load_test.SetupError):
            load_test.validate_config(config)

    def test_repository_fixture_has_50_unique_16_digit_codes_and_uuid_sessions(self):
        fixture_root = MODULE_PATH.parent / "fixtures"
        identities, inline_scenarios = load_test.load_fixture(
            fixture_root / "staging_synthetic_identities.json"
        )
        scenarios = load_test.load_scenario_file(
            fixture_root / "persian_banking_scenarios.json"
        )

        codes = [identity.national_code for identity in identities]
        sessions = [identity.session_id for identity in identities]
        self.assertEqual(len(identities), 50)
        self.assertEqual(len(set(codes)), 50)
        self.assertTrue(all(code.isdigit() and len(code) == 16 for code in codes))
        self.assertEqual(len(set(sessions)), 50)
        self.assertTrue(all(str(uuid.UUID(value)) == value for value in sessions))
        self.assertEqual(inline_scenarios, {})
        self.assertIn("banking-smoke", scenarios)
        self.assertIn("banking-mixed", scenarios)
        self.assertTrue(
            all(
                any("\u0600" <= character <= "\u06ff" for character in step.query)
                for steps in scenarios.values()
                for step in steps
            )
        )

    def test_fixture_session_ids_are_used_by_virtual_users(self):
        fixture = MODULE_PATH.parent / "fixtures" / "staging_synthetic_identities.json"
        identities, _ = load_test.load_fixture(fixture)
        config = load_test.Config(
            base_url="https://staging.example",
            concurrency=50,
            input_file=fixture,
        )

        users = load_test.build_virtual_users(config, identities)

        self.assertEqual(
            {user.session_id for user in users},
            {identity.session_id for identity in identities},
        )


class UrlSafetyTests(unittest.TestCase):
    def config(self, base_url: str, *, allow_http: bool = False):
        return load_test.Config(
            base_url=base_url,
            input_file=Path("fixture.json"),
            allow_http=allow_http,
        )

    def test_plain_http_requires_explicit_option(self):
        with self.assertRaisesRegex(load_test.SetupError, "--allow-http"):
            load_test.validate_config(self.config("http://127.0.0.1:7000"))

    def test_explicit_http_allows_loopback_and_staging_hosts(self):
        load_test.validate_config(
            self.config("http://127.0.0.1:7000", allow_http=True)
        )
        load_test.validate_config(
            self.config("http://localhost:7000", allow_http=True)
        )
        load_test.validate_config(
            self.config("http://ragbot-staging.internal:7000", allow_http=True)
        )

    def test_bind_addresses_remain_invalid_client_destinations(self):
        for base_url in ("http://0.0.0.0:7000", "http://[::]:7000"):
            with self.subTest(base_url=base_url):
                with self.assertRaisesRegex(load_test.SetupError, "bind addresses"):
                    load_test.validate_config(
                        self.config(base_url, allow_http=True)
                    )

    def test_production_looking_http_host_remains_forbidden(self):
        with self.assertRaisesRegex(load_test.SetupError, "production"):
            load_test.validate_config(
                self.config(
                    "http://ragbot-production-staging.example",
                    allow_http=True,
                )
            )


class WorkloadContractTests(unittest.IsolatedAsyncioTestCase):
    def test_repetitions_and_request_count_calculation(self):
        self.assertEqual(load_test.calculate_total_requests(50, 5), 250)
        self.assertEqual(
            load_test.Config(base_url="https://staging.example").total_requests,
            250,
        )

    async def test_burst_jobs_wait_until_every_job_is_ready(self):
        ready_counts: list[int] = []
        starts: list[int] = []

        async def job(index: int) -> load_test.RequestRecord:
            starts.append(index)
            self.assertEqual(ready_counts[-1], 3)
            return record(virtual_user=index)

        jobs = [lambda index=index: job(index) for index in range(1, 4)]
        results = await load_test.run_burst_wave(
            jobs, 0, ready_callback=ready_counts.append
        )

        self.assertEqual(ready_counts, [1, 2, 3])
        self.assertCountEqual(starts, [1, 2, 3])
        self.assertEqual(len(results), 3)

    async def test_mock_transport_keeps_content_in_memory_but_not_serialized(self):
        calls = 0
        full_code = "stglt_reserved_001"

        async def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            payload = json.loads(request.content)
            return httpx.Response(
                200,
                json={
                    "query_id": "7",
                    "session_id": payload["session_id"],
                    "query": payload["query"],
                    "answer": "synthetic answer",
                    "related_questions": [],
                    "feedback_needed": False,
                },
                headers={
                    "X-Request-Id": "server-7",
                    "X-Server-Receive-Time": "2026-08-05T00:00:00+00:00",
                    "X-Admission-Acquired": "true",
                    "X-Admission-Outcome": "acquired",
                    "X-Admission-Wait-Ms": "2.5",
                    "X-Permit-Hold-Ms": "100.5",
                    "X-Pipeline-Ms": "90.0",
                    "X-Post-Generation-Ms": "5.0",
                    "X-VLLM-Duration-Ms": "12.5",
                },
            )

        transport = httpx.MockTransport(handler)
        config = load_test.Config(
            base_url="https://staging.example",
            concurrency=1,
            repetitions=1,
        )
        user = load_test.VirtualUser(
            1,
            load_test.Identity("vu-1", full_code),
            load_test.deterministic_session_id(1, "test", 1),
        )
        async with httpx.AsyncClient(
            transport=transport, base_url=config.base_url
        ) as client:
            result = await load_test.perform_request(
                client,
                config,
                "run",
                user,
                1,
                1,
                load_test.BUILTIN_SCENARIOS["smoke"][0],
            )

        serialized = json.dumps(result.to_dict())
        self.assertEqual(calls, 1)
        self.assertTrue(result.success)
        self.assertEqual(result.answer_characters, len("synthetic answer"))
        self.assertEqual(result.query_text, "سلام، خوبی؟")
        self.assertEqual(result.answer_text, "synthetic answer")
        self.assertEqual(result.national_code, full_code)
        self.assertTrue(result.response_schema_valid)
        self.assertEqual(result.server_request_id, "server-7")
        self.assertEqual(result.client_request_id, "run-w1-u1-r1")
        self.assertEqual(result.submission_index, 1)
        self.assertTrue(result.admission_acquired)
        self.assertEqual(result.admission_outcome, "acquired")
        self.assertEqual(result.limiter_wait_ms, 2.5)
        self.assertEqual(result.permit_hold_ms, 100.5)
        self.assertEqual(result.pipeline_ms, 90.0)
        self.assertEqual(result.post_generation_ms, 5.0)
        self.assertEqual(result.vllm_duration_ms, 12.5)
        self.assertEqual(
            result.server_timing_values["x-vllm-duration-ms"], 12.5
        )
        self.assertNotIn(full_code, serialized)
        self.assertNotIn("synthetic answer", serialized)
        self.assertIn("query_hash", serialized)
        self.assertIn("answer_hash", serialized)

    async def test_mock_transport_timeout_is_not_retried(self):
        calls = 0

        async def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            raise httpx.ReadTimeout("synthetic timeout", request=request)

        config = load_test.Config(
            base_url="https://staging.example",
            concurrency=1,
            repetitions=1,
        )
        user = load_test.VirtualUser(
            1,
            load_test.Identity("vu-1", "stglt_reserved_001"),
            load_test.deterministic_session_id(1, "test", 1),
        )
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler), base_url=config.base_url
        ) as client:
            result = await load_test.perform_request(
                client,
                config,
                "run",
                user,
                1,
                1,
                load_test.BUILTIN_SCENARIOS["smoke"][0],
            )

        self.assertEqual(calls, 1)
        self.assertEqual(result.failure_class, load_test.CLIENT_READ_TIMEOUT)
        self.assertEqual(result.timeout_category, "read")

    async def test_closed_loop_preserves_per_user_follow_up_sessions(self):
        seen: dict[str, list[str]] = {}

        async def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content)
            seen.setdefault(payload["session_id"], []).append(payload["query"])
            await asyncio.sleep(0)
            return httpx.Response(
                200,
                json={
                    "query_id": "1",
                    "session_id": payload["session_id"],
                    "query": payload["query"],
                    "answer": "answer",
                    "related_questions": [],
                    "feedback_needed": False,
                },
            )

        config = load_test.Config(
            base_url="https://staging.example",
            concurrency=2,
            repetitions=2,
            scenario="follow-up",
            workload_mode="closed-loop",
        )
        users = [
            load_test.VirtualUser(
                number,
                load_test.Identity(f"vu-{number}", f"stglt_reserved_{number:03d}"),
                load_test.deterministic_session_id(1, "test", number),
            )
            for number in (1, 2)
        ]
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler), base_url=config.base_url
        ) as client:
            results = await load_test.execute_workload(
                client,
                config,
                "run",
                users,
                load_test.BUILTIN_SCENARIOS,
            )

        expected_queries = [
            step.query for step in load_test.BUILTIN_SCENARIOS["follow-up"]
        ]
        self.assertEqual(len(results), 4)
        self.assertEqual(set(seen), {user.session_id for user in users})
        self.assertTrue(all(queries == expected_queries for queries in seen.values()))


class ResponseRecordingTests(unittest.IsolatedAsyncioTestCase):
    async def perform(
        self,
        *,
        body: object = None,
        status: int = 200,
        raw_content: bytes | None = None,
    ) -> load_test.RequestRecord:
        query = 'متن دقیق، با "نقل قول"\nو خط دوم'

        async def handler(request: httpx.Request) -> httpx.Response:
            if raw_content is not None:
                return httpx.Response(status, content=raw_content)
            return httpx.Response(status, json=body)

        config = load_test.Config(
            base_url="https://staging.example",
            concurrency=1,
            repetitions=1,
        )
        user = load_test.VirtualUser(
            7,
            load_test.Identity("vu-7", "synthetic-national-code-7"),
            load_test.deterministic_session_id(1, "recording", 7),
        )
        step = load_test.ScenarioStep("persian-recording", query)
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler), base_url=config.base_url
        ) as client:
            return await load_test.perform_request(
                client, config, "run", user, 3, 4, step
            )

    @staticmethod
    def talk_response(answer: object) -> dict[str, object]:
        return {
            "query_id": "query-7",
            "session_id": "session-7",
            "query": "synthetic query",
            "answer": answer,
            "related_questions": [],
            "feedback_needed": False,
        }

    async def test_valid_success_records_exact_query_answer_and_persian(self):
        answer = 'پاسخ کامل، با "نقل قول"\nو خط دوم'

        result = await self.perform(body=self.talk_response(answer))

        self.assertTrue(result.success)
        self.assertTrue(result.response_schema_valid)
        self.assertEqual(result.query_text, 'متن دقیق، با "نقل قول"\nو خط دوم')
        self.assertEqual(result.answer_text, answer)
        self.assertEqual(result.answer_characters, len(answer))
        self.assertEqual(result.answer_word_count, len(answer.split()))
        self.assertFalse(result.answer_is_empty)
        self.assertEqual(result.wave_number, 3)
        self.assertEqual(result.virtual_user_number, 7)
        self.assertEqual(result.request_number, 4)
        self.assertEqual(result.scenario, "persian-recording")
        self.assertEqual(result.national_code, "synthetic-national-code-7")

    async def test_empty_answer_is_valid_success(self):
        result = await self.perform(body=self.talk_response(""))

        self.assertTrue(result.success)
        self.assertTrue(result.response_schema_valid)
        self.assertEqual(result.answer_text, "")
        self.assertEqual(result.answer_characters, 0)
        self.assertEqual(result.answer_word_count, 0)
        self.assertTrue(result.answer_is_empty)

    async def test_missing_null_and_non_string_answers_are_invalid(self):
        missing = self.talk_response("unused")
        del missing["answer"]
        cases = [
            ("missing", missing),
            ("null", self.talk_response(None)),
            ("non-string", self.talk_response(123)),
        ]

        for name, body in cases:
            with self.subTest(name=name):
                result = await self.perform(body=body)
                self.assertFalse(result.success)
                self.assertEqual(result.failure_class, load_test.INVALID_SCHEMA)
                self.assertFalse(result.response_schema_valid)
                self.assertEqual(result.answer_text, "")

    async def test_invalid_json_and_non_object_schema_are_invalid(self):
        invalid_json = await self.perform(raw_content=b"{not-json")
        invalid_object = await self.perform(body=["not", "TalkResponse"])

        for result in (invalid_json, invalid_object):
            self.assertFalse(result.success)
            self.assertEqual(result.failure_class, load_test.INVALID_SCHEMA)
            self.assertFalse(result.response_schema_valid)

    async def test_http_error_records_status_without_valid_schema(self):
        result = await self.perform(
            status=500, body={"detail": "synthetic server failure"}
        )

        self.assertFalse(result.success)
        self.assertEqual(result.http_status, 500)
        self.assertEqual(result.failure_class, load_test.HTTP_5XX)
        self.assertFalse(result.response_schema_valid)
        self.assertEqual(result.answer_text, "")


class OutputAndAcceptanceTests(unittest.TestCase):
    def test_exit_code_selection(self):
        self.assertEqual(
            load_test.exit_code_for(setup_valid=True, acceptance_passed=True), 0
        )
        self.assertEqual(
            load_test.exit_code_for(setup_valid=True, acceptance_passed=False), 1
        )
        self.assertEqual(
            load_test.exit_code_for(setup_valid=False, acceptance_passed=False), 2
        )

    def test_acceptance_pass_and_failure(self):
        passing = load_test.summarize_records([record(elapsed_ms=100)])
        passing_result = load_test.evaluate_acceptance(
            passing, load_test.AcceptanceCriteria()
        )
        failing = load_test.summarize_records(
            [
                record(
                    failure_class=load_test.APPLICATION_DEADLINE,
                    elapsed_ms=50_000,
                    status=504,
                )
            ]
        )
        failing_result = load_test.evaluate_acceptance(
            failing, load_test.AcceptanceCriteria()
        )

        self.assertTrue(passing_result["passed"])
        self.assertFalse(failing_result["passed"])
        self.assertTrue(
            any(
                item["criterion"] == "application_deadline_timeouts"
                for item in failing_result["failures"]
            )
        )

    def test_jsonl_and_csv_writing(self):
        rows = [record(), record(virtual_user=2)]
        with tempfile.TemporaryDirectory() as directory:
            jsonl_path = Path(directory) / "requests.jsonl"
            csv_path = Path(directory) / "requests.csv"

            load_test.write_jsonl(jsonl_path, rows)
            load_test.write_csv(csv_path, rows)

            json_rows = [
                json.loads(line)
                for line in jsonl_path.read_text(encoding="utf-8").splitlines()
            ]
            with csv_path.open(encoding="utf-8", newline="") as stream:
                csv_rows = list(csv.DictReader(stream))
            self.assertEqual(len(json_rows), 2)
            self.assertEqual(len(csv_rows), 2)
            self.assertEqual(json_rows[1]["virtual_user_number"], 2)
            self.assertEqual(csv_rows[1]["virtual_user_number"], "2")
            required_fields = {
                "run_id",
                "timestamp",
                "wave_number",
                "virtual_user_id",
                "request_number",
                "scenario_id",
                "client_request_id",
                "submission_index",
                "session_id_hash",
                "national_code_hash",
                "query_hash",
                "query_character_count",
                "answer_hash",
                "answer_character_count",
                "answer_word_count",
                "answer_is_empty",
                "response_schema_valid",
                "latency_ms",
                "http_status",
                "success",
                "failure_category",
                "exception_type",
                "error_message",
                "response_byte_count",
                "server_request_id",
                "server_timing_values",
            }
            self.assertLessEqual(required_fields, set(json_rows[0]))
            self.assertLessEqual(required_fields, set(csv_rows[0]))

    def test_csv_omits_persian_multiline_query_and_answer(self):
        query = 'پرسش، با "نقل قول"\nخط دوم'
        answer = 'پاسخ، با "نقل قول"\nخط دوم\nخط سوم'
        row = record(query_text=query, answer_text=answer)
        with tempfile.TemporaryDirectory() as directory:
            csv_path = Path(directory) / "requests.csv"

            load_test.write_csv(csv_path, [row])

            with csv_path.open(encoding="utf-8", newline="") as stream:
                parsed = next(csv.DictReader(stream))
            self.assertNotIn("query_text", parsed)
            self.assertNotIn("answer_text", parsed)
            self.assertNotIn(query, csv_path.read_text(encoding="utf-8"))
            self.assertNotIn(answer, csv_path.read_text(encoding="utf-8"))
            self.assertTrue(parsed["query_hash"].startswith("sha256:"))
            self.assertTrue(parsed["answer_hash"].startswith("sha256:"))

    def test_answer_quality_lengths_duplicates_and_invalid_schema(self):
        rows = [
            record(query_text="one", answer_text="same", virtual_user=1),
            record(query_text="two", answer_text="same", virtual_user=2),
            record(query_text="query", answer_text="query", virtual_user=3),
            record(query_text="empty", answer_text="", virtual_user=4),
            record(
                failure_class=load_test.INVALID_SCHEMA,
                response_schema_valid=False,
                answer_text="",
                virtual_user=5,
            ),
        ]

        quality = load_test.answer_quality_statistics(rows)

        self.assertEqual(quality["answer_count"], 4)
        self.assertEqual(quality["empty_answer_count"], 1)
        self.assertEqual(quality["empty_answer_percentage"], 25)
        self.assertEqual(quality["minimum_answer_length"], 0)
        self.assertEqual(quality["maximum_answer_length"], 5)
        self.assertEqual(quality["average_answer_length"], 3.25)
        self.assertEqual(quality["median_answer_length"], 4)
        self.assertEqual(quality["duplicate_answer_count"], 1)
        self.assertEqual(quality["duplicate_answer_percentage"], 25)
        self.assertEqual(quality["answers_identical_to_query_count"], 1)
        self.assertEqual(quality["invalid_response_schema_count"], 1)

    def test_interactions_markdown_omits_exact_full_content(self):
        query = "پرسش کامل\nخط دوم"
        answer = "پاسخ کامل\nخط دوم"
        row = record(
            query_text=query,
            answer_text=answer,
            national_code="synthetic-code",
        )

        markdown = load_test.interactions_markdown([row])

        self.assertIn("## Interaction 1", markdown)
        self.assertIn("- Scenario: fixture", markdown)
        self.assertNotIn("synthetic-code", markdown)
        self.assertNotIn(query, markdown)
        self.assertNotIn(answer, markdown)
        self.assertIn("Query hash: sha256:", markdown)
        self.assertIn("Answer hash: sha256:", markdown)

    def test_metric_explanations_include_tail_latency_and_worked_example(self):
        markdown = load_test.metric_explanations_markdown()

        self.assertIn("Averages can hide slow tail requests", markdown)
        self.assertIn("p95 is usually more useful", markdown)
        self.assertIn("p99 reveals tail latency", markdown)
        self.assertIn("Concurrency 30 does not mean throughput 30", markdown)
        self.assertIn("One repetition is not enough", markdown)
        self.assertIn("does not prove concurrency 50 will pass", markdown)
        self.assertIn("intentionally omit question and answer content", markdown)

    def test_all_required_artifacts_are_written(self):
        rows = [record()]
        config = load_test.Config(base_url="https://staging.example")
        global_summary = load_test.summarize_records(rows)
        groups = load_test.grouped_statistics(rows)
        acceptance = load_test.evaluate_acceptance(
            global_summary,
            config.criteria,
            per_wave=groups["by_wave"],
        )
        summary = {
            "configuration": load_test.environment_metadata(
                config, "run", "2026-07-28T00:00:00+00:00"
            ),
            "criteria": dataclasses.asdict(config.criteria),
            "global": global_summary,
            "groups": groups,
            "acceptance": acceptance,
        }

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            load_test.write_artifacts(
                root, rows, summary, cleanup=True
            )

            expected = {
                "requests.jsonl",
                "requests.csv",
                "summary.json",
                "report.md",
                "interactions.md",
                "cleanup-manifest.json",
            }
            self.assertEqual({path.name for path in root.iterdir()}, expected)
            parsed_summary = json.loads(
                (root / "summary.json").read_text(encoding="utf-8")
            )
            self.assertTrue(parsed_summary["acceptance"]["passed"])


if __name__ == "__main__":
    unittest.main()
