"""HTTP transport and completed-turn persistence for the web stream."""

import asyncio
import json
import time

from anyio import CancelScope
from fastapi import HTTPException
from starlette.responses import Response

from conversation_history import ProductionHistoryProvider
from utils.service_errors import ServiceError, ServiceTimeoutError, ServiceUnavailableError


class WebStreamHistoryProvider(ProductionHistoryProvider):
    def __init__(self, db_manager, blocking_runner, query_id, deadline):
        super().__init__(db_manager, blocking_runner)
        self.query_id = query_id
        self.deadline = deadline
        self.completed_query_id = None

    async def save_snapshot(self, snapshot, final_state):
        messages = final_state["messages"]
        last = messages[-1] if messages else {}
        answer = last["content"] if last.get("role") == "assistant" else ""
        row = await self._blocking_runner.run(
            self._db_manager.complete_web_turn,
            self._session_pk(snapshot.conversation_key),
            snapshot.actor_id,
            self.query_id,
            answer,
            {"agent_state": final_state},
            deadline=self.deadline,
            wait_for_completion_on_cancel=True,
        )
        if not row:
            raise ServiceUnavailableError("Failed to save the assistant response")
        self.completed_query_id = str(row["id"])


class WebAnswerStream(Response):
    media_type = "text/event-stream"

    def __init__(self, operation, *, deadline):
        super().__init__(headers={
            "Cache-Control": "no-store",
            "X-Accel-Buffering": "no",
        })
        del self.headers["content-length"]
        self.operation = operation
        self.deadline = deadline

    async def __call__(self, scope, receive, send):
        started = False

        async def event(name, data, *, terminal=False):
            nonlocal started
            if not started:
                await send({
                    "type": "http.response.start",
                    "status": self.status_code,
                    "headers": self.raw_headers,
                })
                started = True
            frame = f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
            await send({
                "type": "http.response.body",
                "body": frame.encode("utf-8"),
                "more_body": not terminal,
            })

        async def delta(text):
            await event("delta", {"text": text})

        async def produce():
            try:
                try:
                    async with asyncio.timeout(self.deadline - time.monotonic()):
                        result = await self.operation(delta)
                except TimeoutError as exc:
                    raise ServiceTimeoutError("AI request exceeded the total deadline") from exc
            except Exception as exc:
                if not started:
                    if isinstance(exc, (ServiceError, HTTPException)):
                        raise
                    raise HTTPException(500, "Unable to complete the answer") from None
                code = exc.error_code if isinstance(exc, ServiceError) else "STREAM_FAILED"
                await event("error", {"errorCode": code}, terminal=True)
                return

            if not started and result["answer"]:
                await delta(result["answer"])
            await event("done", result, terminal=True)

        async def watch_disconnect():
            while (await receive())["type"] != "http.disconnect":
                pass

        producer = asyncio.create_task(produce())
        disconnect = asyncio.create_task(watch_disconnect())
        try:
            await asyncio.wait((producer, disconnect), return_when=asyncio.FIRST_COMPLETED)
            if producer.done():
                try:
                    producer.result()
                except OSError:
                    pass
            elif not started:
                # BaseHTTPMiddleware expects a response even when the peer is gone.
                producer.cancel()
                await Response(status_code=499)(scope, receive, send)
        finally:
            for task in (producer, disconnect):
                if not task.done() and not task.cancelling():
                    task.cancel()
            with CancelScope(shield=True):
                await asyncio.gather(producer, disconnect, return_exceptions=True)
