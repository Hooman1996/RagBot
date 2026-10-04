"""Offline ASGI contract tests for the structured HTTP transaction pair."""

import asyncio
import io
import json
import logging
import tempfile
from pathlib import Path
import unittest
from unittest import mock

import httpx
from starlette.responses import FileResponse

from utils.http_logging_middleware import HttpLoggingMiddleware, route_log_policy
from utils.request_instrumentation import current_trace
from utils.structured_logging import LoggingSettings, start_logging


async def exchange(app, *, path="/api/query", method="POST", body=b"", media="application/json",
                   headers=(), chunks=None, send_hook=None):
    raw_headers = [(b"content-type", media.encode()), (b"content-length", str(len(body)).encode())]
    raw_headers.extend((key.lower().encode(), value.encode()) for key, value in headers)
    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
        "scheme": "http", "method": method, "path": path, "raw_path": path.encode(),
        "query_string": b"raw-secret=do-not-log", "headers": raw_headers,
        "client": ("127.0.0.1", 1000), "server": ("test", 80),
    }
    parts = chunks if chunks is not None else [body]
    incoming = [
        {"type": "http.request", "body": part, "more_body": i < len(parts) - 1}
        for i, part in enumerate(parts)
    ]
    sent = []

    async def receive():
        if incoming:
            return incoming.pop(0)
        return {"type": "http.disconnect"}

    async def send(message):
        if send_hook is not None:
            await send_hook(message)
        sent.append(message)

    await app(scope, receive, send)
    return sent


async def echo_app(scope, receive, send):
    body = bytearray()
    while True:
        message = await receive()
        body.extend(message.get("body", b""))
        if not message.get("more_body", False):
            break
    trace = current_trace()
    trace.add_duration("embedding", 2.5)
    response = json.dumps({"answer": body.decode("utf-8", errors="replace")}, ensure_ascii=False).encode()
    await send({"type": "http.response.start", "status": 200,
                "headers": [(b"content-type", b"application/json"),
                            (b"x-custom", b"preserved"),
                            (b"x-request-id", b"untrusted-app-value")]})
    await send({"type": "http.response.body", "body": response, "more_body": False})


class HttpLoggingMiddlewareTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.stream = io.StringIO()
        self.settings = LoggingSettings(environment="test", pii_hmac_secret="dedicated-test-key", body_max_bytes=2048)
        self.runtime = start_logging(self.settings, self.stream)

    async def asyncTearDown(self):
        self.runtime.close()

    def events(self):
        self.runtime.close()
        return [json.loads(line) for line in self.stream.getvalue().splitlines()]

    async def test_pair_trusted_id_headers_json_and_timing(self):
        body = json.dumps({"query": "hello", "password": "do-not-log-me"}).encode()
        sent = await exchange(
            HttpLoggingMiddleware(echo_app, self.settings), body=body,
            headers=(("X-Request-Id", "gateway-abc-123"), ("Authorization", "Bearer hidden"),
                     ("Cookie", "session=hidden"), ("X-CSRF-Token", "hidden")),
        )
        events = self.events()
        self.assertEqual([event["event"] for event in events], ["request_received", "response_completed"])
        request, response = events
        request_id = request["request_id"]
        self.assertRegex(request_id, r"^[0-9a-f]{32}$")
        self.assertNotEqual(request_id, "gateway-abc-123")
        self.assertEqual(response["request_id"], request_id)
        self.assertEqual(request["upstream_request_id"], "gateway-abc-123")
        self.assertEqual(response["upstream_request_id"], "gateway-abc-123")
        header_map = dict(sent[0]["headers"])
        self.assertEqual(header_map[b"x-request-id"].decode(), request_id)
        self.assertEqual(header_map[b"x-custom"], b"preserved")
        for name in (b"x-server-receive-time", b"x-admission-acquired", b"x-admission-outcome",
                     b"x-endpoint-processing-ms", b"x-embedding-duration-ms"):
            self.assertIn(name, header_map)
        self.assertEqual(request["data"]["request"]["body"]["query"], "hello")
        self.assertEqual(request["data"]["request"]["body"]["password"], "[REDACTED]")
        self.assertEqual(response["data"]["http"]["status_code"], 200)
        self.assertIn("answer", response["data"]["response"]["body"])
        timing = response["data"]["timing"]
        self.assertGreaterEqual(timing["total_ms"], 0)
        self.assertIn("+00:00", timing["started_at"])
        self.assertIn("+00:00", timing["completed_at"])
        self.assertEqual(timing["durations_ms"]["embedding"], 2.5)
        output = self.stream.getvalue()
        for secret in ("do-not-log-me", "Bearer hidden", "session=hidden", "raw-secret=do-not-log"):
            self.assertNotIn(secret, output)

    async def test_no_upstream_unread_get_emits_one_correlated_pair(self):
        async def no_read(scope, receive, send):
            await send({"type": "http.response.start", "status": 204, "headers": []})
            await send({"type": "http.response.body", "body": b"", "more_body": False})

        sent = await exchange(HttpLoggingMiddleware(no_read, self.settings),
                              path="/api/health", method="GET")
        events = self.events()
        self.assertEqual([event["event"] for event in events],
                         ["request_received", "response_completed"])
        request, response = events
        self.assertEqual(request["request_id"], response["request_id"])
        self.assertEqual(dict(sent[0]["headers"])[b"x-request-id"].decode(),
                         request["request_id"])
        self.assertIsNone(request["upstream_request_id"])
        self.assertIsNone(response["upstream_request_id"])
        self.assertEqual(request["data"]["request"]["received_at"],
                         response["data"]["timing"]["started_at"])

    async def test_ordinary_application_log_inherits_server_id(self):
        async def application(scope, receive, send):
            logging.getLogger("domain.example").info("credential %s", "raw-private-value")
            await send({"type": "http.response.start", "status": 200,
                        "headers": [(b"content-type", b"application/json")]})
            await send({"type": "http.response.body", "body": b'{}', "more_body": False})

        await exchange(HttpLoggingMiddleware(application, self.settings), method="GET")
        events = self.events()
        ids = {event["request_id"] for event in events}
        self.assertEqual(len(ids), 1)
        self.assertEqual({event["event"] for event in events},
                         {"request_received", "response_completed", "application_log"})
        self.assertNotIn("raw-private-value", self.stream.getvalue())

    async def test_bad_upstream_id_is_ignored_and_cannot_fail_request(self):
        await exchange(HttpLoggingMiddleware(echo_app, self.settings), body=b"{}",
                       headers=(("X-Request-Id", "x" * 129),))
        events = self.events()
        self.assertIsNone(events[0]["upstream_request_id"])
        self.assertRegex(events[0]["request_id"], r"^[0-9a-f]{32}$")

    async def test_mobile_pii_and_answer_echo_are_sanitized_before_enqueue(self):
        payload = {"session_id": "session-1", "query": "call 09123456789 and code 1234567891",
                   "national_code": "1234567891"}
        sent = await exchange(HttpLoggingMiddleware(echo_app, self.settings),
                              path="/api/mobile/v1/talk", body=json.dumps(payload).encode())
        events = self.events()
        request_body = events[0]["data"]["request"]["body"]
        answer = events[1]["data"]["response"]["body"]["answer"]
        self.assertRegex(request_body["national_code"], r"^pii_[0-9a-f]{24}$")
        self.assertNotIn("09123456789", request_body["query"])
        self.assertNotIn("1234567891", request_body["query"])
        self.assertNotIn("09123456789", answer)
        self.assertNotIn("1234567891", answer)
        self.assertEqual(sent[1]["body"].decode(), json.dumps({"answer": json.dumps(payload)}, ensure_ascii=False))

    async def test_sensitive_nested_json_is_safe_in_both_http_events(self):
        payload = {
            "password": "private-password", "password_hash": "private-hash",
            "Authorization": "Bearer secret-authorization", "Cookie": "private-cookie",
            "csrf_token": "private-csrf", "access_token": "private-access",
            "refresh_token": "private-refresh", "api_key": "private-api-key",
            "WEB_SESSION_SECRET": "private-web-secret",
            "LOG_PII_HMAC_SECRET": "private-hmac-secret",
            "national_code": "1234567891", "phone": "09123456789",
            "email": "alice@example.com", "username": "private-username",
            "full_name": "Private Person", "displayName": "Private Display",
            "job_access": "private-job-access",
            "query": "09123456789 4111111111111111 IR062960000000100324200001",
            "nested": [{"comment": "Bearer abcdefghijklmnopqrstuvwxyz"}],
        }

        async def json_echo(scope, receive, send):
            body = (await receive())["body"]
            await send({"type": "http.response.start", "status": 200,
                        "headers": [(b"content-type", b"application/json")]})
            await send({"type": "http.response.body", "body": body, "more_body": False})

        settings = LoggingSettings(environment="test", pii_hmac_secret="dedicated-test-key",
                                   body_max_bytes=4096)
        await exchange(HttpLoggingMiddleware(json_echo, settings), body=json.dumps(payload).encode())
        events = [event for event in self.events() if event["event"] in
                  {"request_received", "response_completed"}]
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["data"]["request"]["body"]["username"], "[REDACTED]")
        self.assertEqual(events[1]["data"]["response"]["body"]["displayName"], "[REDACTED]")
        self.assertRegex(events[0]["data"]["request"]["body"]["national_code"],
                         r"^pii_[0-9a-f]{24}$")
        output = self.stream.getvalue()
        for raw in ("private-password", "private-hash", "secret-authorization",
                    "private-cookie", "private-csrf", "private-access", "private-refresh",
                    "private-api-key", "private-web-secret", "private-hmac-secret",
                    "1234567891", "09123456789", "alice@example.com",
                    "private-username", "Private Person", "Private Display",
                    "private-job-access", "4111111111111111",
                    "IR062960000000100324200001", "abcdefghijklmnopqrstuvwxyz"):
            self.assertNotIn(raw, output)

    async def test_missing_hmac_key_redacts_mobile_identity(self):
        settings = LoggingSettings(environment="test", body_max_bytes=2048)
        body = json.dumps({"national_code": "1234567891"}).encode()
        await exchange(HttpLoggingMiddleware(echo_app, settings), path="/api/mobile/v1/talk", body=body)
        events = self.events()
        # The emitter's defensive policy can still pseudonymize with its own
        # key; the middleware must redact before enqueue when its key is absent.
        self.assertEqual(events[0]["data"]["request"]["body"]["national_code"], "[REDACTED]")

    async def test_body_limits_and_binary_upload_policy(self):
        settings = LoggingSettings(environment="test", body_max_bytes=32)
        big = json.dumps({"password": "super-secret-" + "x" * 100}).encode()
        await exchange(HttpLoggingMiddleware(echo_app, settings), body=big, chunks=[big[:20], big[20:]])
        await exchange(HttpLoggingMiddleware(echo_app, settings), body=b"PDF PRIVATE BYTES",
                       media="application/pdf", path="/api/ocr/extract")
        await exchange(HttpLoggingMiddleware(echo_app, settings), body=b"MULTIPART PRIVATE BYTES",
                       media="multipart/form-data", path="/api/ocr/extract")
        events = self.events()
        self.assertEqual(len(events), 6)
        first = events[0]["data"]["request"]
        self.assertTrue(first["body_truncated"])
        self.assertEqual(first["original_size_bytes"], len(big))
        self.assertEqual(first["body"], "[TRUNCATED]")
        self.assertTrue(events[1]["data"]["response"]["body_truncated"])
        for index in (2, 4):
            self.assertTrue(events[index]["data"]["request"]["body_omitted"])
        output = self.stream.getvalue()
        self.assertNotIn("super-secret", output)
        self.assertNotIn("PDF PRIVATE BYTES", output)
        self.assertNotIn("MULTIPART PRIVATE BYTES", output)

    async def test_streaming_chunks_forward_unchanged_and_no_body_buffering(self):
        chunks = [b"first-", b"second-", b"third"]
        observed = []

        async def streaming(scope, receive, send):
            await send({"type": "http.response.start", "status": 200,
                        "headers": [(b"content-type", b"text/event-stream")]})
            for index, chunk in enumerate(chunks):
                observed.append(index)
                if index == 1:
                    await asyncio.sleep(0.01)
                await send({"type": "http.response.body", "body": chunk,
                            "more_body": index < len(chunks) - 1})

        sent = await exchange(HttpLoggingMiddleware(streaming, self.settings), method="GET", body=b"")
        events = self.events()
        self.assertEqual(observed, [0, 1, 2])
        self.assertEqual([message["body"] for message in sent[1:]], chunks)
        self.assertEqual([message["more_body"] for message in sent[1:]], [True, True, False])
        self.assertTrue(events[1]["data"]["response"]["body_omitted"])
        self.assertEqual(events[1]["data"]["response"]["observed_size_bytes"], sum(map(len, chunks)))
        self.assertTrue(events[1]["data"]["response"]["complete"])
        self.assertGreater(events[1]["data"]["timing"]["total_ms"], 8)

    async def test_file_response_bytes_are_forwarded_but_not_logged(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "private.bin"
            path.write_bytes(b"FILE RESPONSE PRIVATE BYTES")

            async def file_app(scope, receive, send):
                await FileResponse(path, media_type="application/octet-stream")(
                    scope, receive, send
                )

            sent = await exchange(HttpLoggingMiddleware(file_app, self.settings),
                                  path="/api/sessions/123/download", method="GET")
        self.assertEqual(b"".join(message.get("body", b"") for message in sent[1:]),
                         b"FILE RESPONSE PRIVATE BYTES")
        events = self.events()
        self.assertTrue(events[1]["data"]["response"]["body_omitted"])
        self.assertNotIn("FILE RESPONSE PRIVATE BYTES", self.stream.getvalue())

    async def test_disabled_flags_avoid_body_sanitizer(self):
        settings = LoggingSettings(environment="test", request_body=False, response_body=False)
        with mock.patch("utils.http_logging_middleware.sanitize_body", side_effect=AssertionError("body work")):
            sent = await exchange(HttpLoggingMiddleware(echo_app, settings), body=b"{}")
        events = self.events()
        self.assertEqual(sent[0]["status"], 200)
        self.assertTrue(events[0]["data"]["request"]["body_omitted"])
        self.assertTrue(events[1]["data"]["response"]["body_omitted"])

    async def test_statuses_unhandled_error_and_logging_failure(self):
        async def status_app(scope, receive, send):
            path = scope["path"]
            if path == "/raise":
                raise RuntimeError("private exception detail")
            status = int(path.rsplit("/", 1)[-1])
            await send({"type": "http.response.start", "status": status,
                        "headers": [(b"content-type", b"application/json")]})
            await send({"type": "http.response.body", "body": b'{}', "more_body": False})

        middleware = HttpLoggingMiddleware(status_app, self.settings)
        for status in (200, 400, 401, 403, 404, 422, 500):
            await exchange(middleware, path=f"/status/{status}", method="GET")
        with self.assertRaisesRegex(RuntimeError, "private exception detail"):
            await exchange(middleware, path="/raise", method="GET")
        with mock.patch("utils.http_logging_middleware.sanitize_body", side_effect=RuntimeError("logging failure")):
            sent = await exchange(middleware, path="/status/200", method="GET")
        self.assertEqual(sent[0]["status"], 200)
        with mock.patch("utils.http_logging_middleware.log_event", side_effect=RuntimeError("logger failed")):
            still_ok = await exchange(middleware, path="/status/200", method="GET")
        self.assertEqual(still_ok[0]["status"], 200)
        events = self.events()
        completions = [event for event in events if event["event"] == "response_completed"]
        self.assertEqual([event["data"]["http"]["status_code"] for event in completions], [200, 400, 401, 403, 404, 422, 500, 500, 200])
        self.assertEqual(completions[7]["data"]["error"]["type"], "RuntimeError")
        self.assertNotIn("private exception detail", self.stream.getvalue())

    async def test_static_skips_events_but_keeps_trace_header(self):
        sent = await exchange(HttpLoggingMiddleware(echo_app, self.settings),
                              path="/static/app.js", method="GET", body=b"{}")
        self.assertRegex(dict(sent[0]["headers"])[b"x-request-id"].decode(), r"^[0-9a-f]{32}$")
        self.assertEqual(self.events(), [])
        self.assertFalse(route_log_policy("/static/file.css").emit_events)
        self.assertFalse(route_log_policy("/api/health").request_body)

    async def test_raw_sensitive_body_is_sanitized_before_enqueue(self):
        payload = json.dumps({"password": "raw-password-secret", "national_code": "1234567891",
                              "query": "Bearer abcdefghijklmnop"}).encode()
        captured = []

        def collect(_logger, event, data):
            captured.append((event, data))

        with mock.patch("utils.http_logging_middleware.log_event", side_effect=collect):
            await exchange(HttpLoggingMiddleware(echo_app, self.settings), body=payload)
        self.assertEqual([event for event, _ in captured], ["request_received", "response_completed"])
        queued = json.dumps(captured, ensure_ascii=False)
        for raw in ("raw-password-secret", "1234567891", "abcdefghijklmnop"):
            self.assertNotIn(raw, queued)

    async def test_unread_and_malformed_request_bodies_are_safe(self):
        async def no_read(scope, receive, send):
            await send({"type": "http.response.start", "status": 204, "headers": []})
            await send({"type": "http.response.body", "body": b"", "more_body": False})

        await exchange(HttpLoggingMiddleware(no_read, self.settings), body=b'{"password":"unread"}')
        await exchange(HttpLoggingMiddleware(echo_app, self.settings), body=b'{"password": invalid')
        events = self.events()
        self.assertEqual(len(events), 4)
        self.assertTrue(events[0]["data"]["request"]["body_omitted"])
        self.assertTrue(events[2]["data"]["request"]["body_parse_error"])
        self.assertNotIn("unread", self.stream.getvalue())
        self.assertNotIn("invalid", self.stream.getvalue())

    async def test_binary_response_is_metadata_only(self):
        async def binary(scope, receive, send):
            await send({"type": "http.response.start", "status": 200,
                        "headers": [(b"content-type", b"application/octet-stream")]})
            await send({"type": "http.response.body", "body": b"PRIVATE FILE BYTES",
                        "more_body": False})

        sent = await exchange(HttpLoggingMiddleware(binary, self.settings), method="GET")
        events = self.events()
        self.assertEqual(sent[1]["body"], b"PRIVATE FILE BYTES")
        self.assertTrue(events[1]["data"]["response"]["body_omitted"])
        self.assertNotIn("PRIVATE FILE BYTES", self.stream.getvalue())

    async def test_concurrent_contexts_stay_isolated(self):
        middleware = HttpLoggingMiddleware(echo_app, self.settings)
        await asyncio.gather(*(
            exchange(middleware, path="/api/query", body=json.dumps({"query": f"hello-{i}"}).encode(),
                     headers=(("X-Request-Id", f"gateway-{i}"),))
            for i in range(20)
        ))
        events = self.events()
        self.assertEqual(len(events), 40)
        pairs = {}
        for event in events:
            pairs.setdefault(event["request_id"], []).append(event)
        self.assertEqual(len(pairs), 20)
        for pair in pairs.values():
            self.assertEqual({item["event"] for item in pair}, {"request_received", "response_completed"})
            self.assertEqual(len({item["upstream_request_id"] for item in pair}), 1)

    async def test_actual_error_handlers_use_trusted_id_with_upstream_header(self):
        from fastapi import FastAPI
        import main
        from utils.service_errors import InvalidRequestError

        app = FastAPI()
        app.add_exception_handler(main.BankException, main.bank_exception_handler)
        app.add_exception_handler(InvalidRequestError, main.service_exception_handler)

        @app.get("/api/bank-error")
        async def bank_error():
            raise main.BankException("BANK_ERROR", "safe message", status_code=400)

        @app.get("/api/service-error")
        async def service_error():
            raise InvalidRequestError("safe message")

        instrumented = HttpLoggingMiddleware(app, self.settings)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=instrumented),
                                     base_url="http://test") as client:
            for path in ("/api/bank-error", "/api/service-error"):
                response = await client.get(path, headers={"X-Request-Id": "gateway-123"})
                self.assertEqual(response.status_code, 400)
                server_id = response.headers["X-Request-Id"]
                self.assertRegex(server_id, r"^[0-9a-f]{32}$")
                self.assertEqual(response.json()["errorDetails"]["requestId"], server_id)
                self.assertNotEqual(server_id, "gateway-123")
        events = [event for event in self.events() if event["event"] in
                  {"request_received", "response_completed"}]
        self.assertEqual(len(events), 4)
        for request, response in ((events[0], events[1]), (events[2], events[3])):
            self.assertEqual(request["request_id"], response["request_id"])
            self.assertEqual(request["upstream_request_id"], "gateway-123")
            self.assertEqual(response["upstream_request_id"], "gateway-123")
            self.assertEqual(response["data"]["http"]["status_code"], 400)

    async def test_cancelled_request_is_logged_once_and_propagated(self):
        async def cancelled(scope, receive, send):
            raise asyncio.CancelledError()

        with self.assertRaises(asyncio.CancelledError):
            await exchange(HttpLoggingMiddleware(cancelled, self.settings), method="GET")
        events = self.events()
        self.assertEqual([item["event"] for item in events],
                         ["request_received", "response_completed"])
        self.assertEqual(events[0]["request_id"], events[1]["request_id"])
        self.assertEqual(events[1]["data"]["http"]["status_code"], 500)
        self.assertEqual(events[1]["data"]["error"]["type"], "CancelledError")

    async def test_main_login_mobile_eval_bypass_regression(self):
        # Validation fails before any service call; this exercises the real
        # mounted routes and browser-auth exemptions without external systems.
        import main

        transport = httpx.ASGITransport(app=main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            login = await client.post("/api/login", json={"password": "login-private-password"})
            mobile = await client.post("/api/mobile/v1/talk", json={"session_id": "s"})
            evaluation = await client.post("/api/internal/evaluation/v1/turn", json={"query": "hi"})
        self.assertEqual((login.status_code, mobile.status_code, evaluation.status_code), (422, 422, 422))
        self.assertTrue(all(response.headers.get("x-request-id") for response in (login, mobile, evaluation)))
        events = self.events()
        self.assertEqual(len([item for item in events if item["event"] == "response_completed"]), 3)
        self.assertNotIn("login-private-password", self.stream.getvalue())


if __name__ == "__main__":
    unittest.main()
