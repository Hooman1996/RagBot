import asyncio
import io
import json
import logging
import os
import re
import socket
import unittest
from unittest import mock

from utils.log_sanitizer import REDACTED, pseudonymize, sanitize, sanitize_body, scrub_text
from utils.request_instrumentation import (
    RequestTrace, new_request_id, reset_current_trace,
    safe_upstream_request_id, set_current_trace,
)
from utils.structured_logging import (
    JsonEventFormatter, LoggingSettings, RequestContextFilter, load_logging_settings,
    log_event, start_logging,
)


class SanitizerTests(unittest.TestCase):
    def test_secret_fields_are_case_insensitive_and_recursive(self):
        source = {
            "Password": "one", "password_hash": "hash", "Authorization": "Bearer abc",
            "Cookie": "session", "x-csrf-token": "csrf", "QDRANT_API_KEY": "key",
            "client_secret": "secret", "nested": [{"accessToken": "token"}],
        }
        original = {**source, "nested": [{"accessToken": "token"}]}
        safe = sanitize(source)
        for key in ("Password", "password_hash", "Authorization", "Cookie", "x-csrf-token", "QDRANT_API_KEY", "client_secret"):
            self.assertEqual(safe[key], REDACTED)
        self.assertEqual(safe["nested"][0]["accessToken"], REDACTED)
        self.assertEqual(source, original)

    def test_customer_identity_and_access_fields_are_redacted_without_name_false_positives(self):
        source = {
            "username": "customer-login", "full_name": "Private Person",
            "fullName": "Private Person", "display_name": "Private Person",
            "displayName": "Private Person", "job_access": "grant-all",
            "jobAccess": "grant-all", "service_name": "ragbot",
            "nested": [{"USERNAME": "nested-login", "WEB_SESSION_SECRET": "session-secret",
                        "LOG_PII_HMAC_SECRET": "hmac-secret", "refresh_token": "refresh-secret",
                        "access_token": "access-secret"}],
        }
        safe = sanitize(source)
        for key in ("username", "full_name", "fullName", "display_name", "displayName",
                    "job_access", "jobAccess"):
            self.assertEqual(safe[key], REDACTED)
        for key in ("USERNAME", "WEB_SESSION_SECRET", "LOG_PII_HMAC_SECRET",
                    "refresh_token", "access_token"):
            self.assertEqual(safe["nested"][0][key], REDACTED)
        self.assertEqual(safe["service_name"], "ragbot")
        self.assertEqual(source["username"], "customer-login")
        for raw in ("customer-login", "Private Person", "grant-all", "session-secret",
                    "hmac-secret", "refresh-secret", "access-secret", "nested-login"):
            self.assertNotIn(raw, json.dumps(safe))

    def test_query_answer_comment_free_text_redaction(self):
        source = {"query": "call 09123456789 card 4111111111111111",
                  "answer": "Sheba IR062960000000100324200001",
                  "comment": "email alice@example.com Bearer abcdefghijklmnopqrstuvwxyz"}
        safe = sanitize(source)
        for raw in ("09123456789", "4111111111111111", "IR062960000000100324200001",
                    "alice@example.com", "abcdefghijklmnopqrstuvwxyz"):
            self.assertNotIn(raw, json.dumps(safe))

    def test_pii_fields_and_deterministic_pseudonyms(self):
        secret = "logging-only-test-secret"
        first = sanitize({"national_code": "1234567891", "phone": "09123456789", "email": "a@b.com"}, hmac_secret=secret)
        second = sanitize({"nationalCode": "1234567891"}, hmac_secret=secret)
        different = sanitize({"national_code": "1234567892"}, hmac_secret=secret)
        self.assertRegex(first["national_code"], r"^pii_[0-9a-f]{24}$")
        self.assertEqual(first["national_code"], second["nationalCode"])
        self.assertNotEqual(first["national_code"], different["national_code"])
        self.assertNotIn("1234567891", json.dumps(first))
        self.assertEqual(first["phone"], REDACTED)
        self.assertEqual(first["email"], REDACTED)
        self.assertEqual(pseudonymize("1234567891", None), REDACTED)

    def test_free_text_scrubs_banking_pii_and_tokens(self):
        text = "code 1234567891 mobile 09123456789 email alice@example.com card 4111 1111 1111 1111 sheba IR062960000000100324200001 Bearer abcdefghijklmnopqrstuvwxyz abcdefghijk.abcdefghijk.abcdefghijk"
        safe = scrub_text(text, hmac_secret="logging-only-test-secret")
        for raw in ("1234567891", "09123456789", "alice@example.com", "4111 1111 1111 1111", "IR062960000000100324200001", "abcdefghijklmnopqrstuvwxyz", "abcdefghijk.abcdefghijk.abcdefghijk"):
            self.assertNotIn(raw, safe)
        self.assertIn("pii_", safe)
        self.assertIn("1234567890", scrub_text("number 1234567890"))
        self.assertIn("4111111111111112", scrub_text("ordinary 4111111111111112"))
        self.assertNotIn("my-private-password", scrub_text("password=my-private-password"))
        self.assertNotIn("short-token", scrub_text("Authorization: Bearer short-token"))
        persian_digits = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
        persian_text = " ".join(value.translate(persian_digits) for value in (
            "09123456789", "4111111111111111", "1234567891", "IR062960000000100324200001",
        ))
        persian_safe = scrub_text(persian_text)
        for value in persian_text.split():
            self.assertNotIn(value, persian_safe)

    def test_inline_customer_identity_assignments_are_scrubbed(self):
        text = ('username=private-login fullName="Private Person" '
                'display_name=PrivateName jobAccess=grant-all '
                'WEB_SESSION_SECRET=session-value LOG_PII_HMAC_SECRET=hmac-value')
        safe = scrub_text(text)
        for raw in ("private-login", "Private Person", "PrivateName", "grant-all",
                    "session-value", "hmac-value"):
            self.assertNotIn(raw, safe)

    def test_bounds_binary_cycles_and_unknown_objects(self):
        source = {"items": ["a" * 500, {"upload": b"private-file-bytes"}], "bad": object()}
        safe = sanitize(source, max_chars=32)
        self.assertIn("[TRUNCATED]", safe["items"][0])
        self.assertEqual(safe["items"][1]["upload"], {"binary_omitted": True, "size_bytes": 18})
        self.assertEqual(safe["bad"], "[UNSERIALIZABLE]")
        self.assertNotIn("private-file-bytes", json.dumps(safe))
        cyclic = []
        cyclic.append(cyclic)
        self.assertEqual(sanitize(cyclic), ["[CYCLE]"])
        body = sanitize_body("x" * 100, max_bytes=16, original_size_bytes=100)
        self.assertTrue(body["body_truncated"])
        self.assertEqual(body["original_size_bytes"], 100)
        self.assertEqual(sanitize_body(b"secret", max_bytes=1)["body"], {"binary_omitted": True, "size_bytes": 6})
        self.assertTrue(sanitize_body({"note": "x" * 100}, max_bytes=20)["body_truncated"])
        self.assertEqual(sanitize({"customerNationalCode": "1234567891"})["customerNationalCode"], REDACTED)
        long_key = "password" + "x" * 200
        self.assertEqual(sanitize({long_key: "private"})[long_key[:128]], REDACTED)

    def test_hmac_secret_is_never_emitted(self):
        secret = "very-sensitive-logging-secret"
        safe = sanitize({"LOG_PII_HMAC_SECRET": secret, "note": f"value {secret}"}, hmac_secret=secret)
        self.assertNotIn(secret, json.dumps(safe))
        self.assertEqual(safe["LOG_PII_HMAC_SECRET"], REDACTED)


class LoggerTests(unittest.TestCase):
    def setUp(self):
        self.stream = io.StringIO()
        self.runtime = start_logging(LoggingSettings(environment="test", pii_hmac_secret="logging-only-test-secret"), self.stream)
        self.logger = logging.getLogger("test.structured")

    def tearDown(self):
        self.runtime.close()

    def _events(self):
        self.runtime.close()
        return [json.loads(line) for line in self.stream.getvalue().splitlines()]

    def test_json_lines_schema_and_no_active_trace(self):
        log_event(self.logger, "first", {"status_code": 200})
        log_event(self.logger, "second", {"password": "hidden"})
        events = self._events()
        self.assertEqual(len(events), 2)
        self.assertEqual([event["event"] for event in events], ["first", "second"])
        self.assertEqual(events[0]["schema_version"], "1.0")
        self.assertEqual(events[0]["service"], "ragbot")
        self.assertEqual(events[0]["environment"], "test")
        self.assertIsNone(events[0]["request_id"])
        self.assertRegex(events[0]["@timestamp"], r"\+00:00$")
        self.assertEqual(events[1]["data"]["password"], REDACTED)

    def test_request_context_injected_and_upstream_separate(self):
        trace = RequestTrace(request_id="server-id", process_id=os.getpid(), upstream_request_id="gateway-id")
        token = set_current_trace(trace)
        try:
            log_event(self.logger, "test_event", {"total_ms": 1.2})
        finally:
            reset_current_trace(token)
        event = self._events()[0]
        self.assertEqual(event["request_id"], "server-id")
        self.assertEqual(event["upstream_request_id"], "gateway-id")
        self.assertEqual(event["data"]["total_ms"], 1.2)

    def test_upstream_id_is_defensively_scrubbed_at_formatter(self):
        for upstream in ("gateway-abc-123", "09123456789", "1234567891",
                         "abcdefghijk.abcdefghijk.abcdefghijk"):
            self.assertEqual(safe_upstream_request_id(upstream), upstream)
            trace = RequestTrace(request_id="trusted-server-id", process_id=os.getpid(),
                                 upstream_request_id=upstream)
            token = set_current_trace(trace)
            try:
                log_event(self.logger, "upstream_test", {})
            finally:
                reset_current_trace(token)
        events = self._events()
        self.assertEqual(events[0]["upstream_request_id"], "gateway-abc-123")
        self.assertTrue(all(event["request_id"] == "trusted-server-id" for event in events))
        for raw in ("09123456789", "1234567891", "abcdefghijk.abcdefghijk.abcdefghijk"):
            self.assertNotIn(raw, self.stream.getvalue())

    def test_unserializable_event_and_legacy_message_cannot_crash_or_leak(self):
        log_event(self.logger, "broken", {"object": object(), "binary": b"secretbytes"})
        self.logger.error("raw secret %s", "customer credential")
        try:
            raise ValueError("private exception detail")
        except ValueError:
            self.logger.exception("private error")
        events = self._events()
        self.assertEqual(events[0]["data"]["object"], "[UNSERIALIZABLE]")
        self.assertNotIn("secretbytes", self.stream.getvalue())
        self.assertNotIn("customer credential", self.stream.getvalue())
        self.assertEqual(events[1]["message"], REDACTED)
        self.assertEqual(events[2]["exception_type"], "ValueError")
        self.assertNotIn("private exception detail", self.stream.getvalue())

    def test_uvicorn_access_is_suppressed_only_while_runtime_is_active(self):
        access_logger = logging.getLogger("uvicorn.access")
        self.assertTrue(access_logger.disabled)
        self.runtime.close()
        self.assertEqual(access_logger.disabled, self.runtime.previous_access_disabled)

    def test_no_network_calls_and_listener_lifecycle(self):
        with mock.patch.object(socket.socket, "connect", side_effect=AssertionError("network")):
            log_event(self.logger, "offline", {"result": "ok"})
            events = self._events()
        self.assertEqual(events[0]["event"], "offline")
        self.assertIsNone(self.runtime.listener._thread)

    def test_stdout_write_failure_does_not_escape_or_print_exception(self):
        class BrokenStream:
            def write(self, _value):
                raise OSError("private failure detail")
            def flush(self):
                raise OSError("private failure detail")

        broken = start_logging(LoggingSettings(), BrokenStream())
        try:
            log_event(self.logger, "broken_stdout", {"password": "secret"})
        finally:
            broken.close()
        self.assertGreaterEqual(broken.stream_handler.write_errors, 1)
        self.assertGreaterEqual(broken.snapshot()["stdout_write_errors"], 1)

    def test_overflow_falls_back_without_dropping_event(self):
        from utils.structured_logging import LoggingRuntime
        stream = io.StringIO()
        runtime = LoggingRuntime(LoggingSettings(queue_size=1), stream)
        try:
            record = self.logger.makeRecord(self.logger.name, logging.INFO, __file__, 1, "", (), None)
            record.ragbot_event_data = {"event": "overflow", "data": {}}
            runtime.handler.handle(record)
            self.assertEqual(runtime.handler.overflow_count, 0)
            self.assertEqual(stream.getvalue(), "")
            runtime.handler.handle(record)
            self.assertEqual(runtime.handler.overflow_count, 1)
            self.assertEqual(runtime.snapshot()["overflow_count"], 1)
            self.assertEqual(runtime.snapshot()["queue_depth"], 1)
            self.assertFalse(runtime.snapshot()["listener_alive"])
            self.assertEqual(json.loads(stream.getvalue())["event"], "overflow")
        finally:
            runtime.stream_handler.close()


class ContextAndConfigTests(unittest.IsolatedAsyncioTestCase):
    async def test_async_contexts_do_not_exchange_request_ids(self):
        async def worker(request_id):
            trace = RequestTrace(request_id=request_id, process_id=1)
            token = set_current_trace(trace)
            try:
                await asyncio.sleep(0)
                record = logging.makeLogRecord({"msg": "", "levelno": logging.INFO})
                RequestContextFilter().filter(record)
                return record.ragbot_request_id
            finally:
                reset_current_trace(token)
        self.assertEqual(await asyncio.gather(worker("a"), worker("b")), ["a", "b"])

    async def test_trusted_id_helpers(self):
        self.assertRegex(new_request_id(), r"^[0-9a-f]{32}$")
        self.assertEqual(safe_upstream_request_id("gateway-123"), "gateway-123")
        self.assertIsNone(safe_upstream_request_id("bad\nvalue"))
        self.assertIsNone(safe_upstream_request_id("x" * 129))

    async def test_settings_redact_without_secret_and_reject_unsafe_switch(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            settings = load_logging_settings()
        self.assertIsNone(settings.pii_hmac_secret)
        self.assertEqual(sanitize({"national_code": "1234567891"})["national_code"], REDACTED)
        with mock.patch.dict(os.environ, {"LOG_PII_REDACTION": "false"}, clear=True):
            with self.assertRaises(ValueError):
                load_logging_settings()
        for environment, expected in (
            ({"ENVIRONMENT": "fallback"}, "fallback"),
            ({"ENVIRONMENT": "fallback", "WEB_ENVIRONMENT": "web"}, "web"),
            ({"ENVIRONMENT": "fallback", "WEB_ENVIRONMENT": "web",
              "LOG_ENVIRONMENT": "production"}, "production"),
        ):
            with mock.patch.dict(os.environ, environment, clear=True):
                self.assertEqual(load_logging_settings().environment, expected)
        with mock.patch.dict(os.environ, {"LOG_ENVIRONMENT": "unsafe/value"}, clear=True):
            with self.assertRaises(ValueError):
                load_logging_settings()
        with mock.patch.dict(os.environ, {"LOG_ENVIRONMENT": ""}, clear=True):
            with self.assertRaises(ValueError):
                load_logging_settings()
