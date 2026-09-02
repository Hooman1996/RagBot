"""Process-local lifecycle for the CUDA-capable canonical RagBot runtime."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from typing import Any


CUDA_REINITIALIZATION_FRAGMENT = "cannot re-initialize cuda in forked subprocess"


class WorkerRuntimeInitializationError(RuntimeError):
    """Content-free initialization failure safe for Celery logs."""

    def __init__(self, error_code: str):
        self.error_code = error_code
        super().__init__(f"evaluation worker runtime initialization failed: {error_code}")


def worker_initialization_error_code(exc: BaseException) -> str:
    message = str(exc).lower()
    if CUDA_REINITIALIZATION_FRAGMENT in message:
        return "CUDA_WORKER_INIT_FAILED"
    return "EVALUATION_WORKER_INIT_FAILED"


def _default_runtime_factory() -> AbstractAsyncContextManager:
    # Delay heavyweight RagBot/Torch imports until the solo worker process is
    # running. The canonical factory still selects the production device.
    from ..core_adapter.runtime import canonical_turn_runtime

    return canonical_turn_runtime()


class WorkerProcessRuntime:
    """Own one event loop and one canonical runtime for a worker process."""

    def __init__(
        self,
        *,
        runtime_factory: Callable[[], AbstractAsyncContextManager] | None = None,
    ) -> None:
        self._runtime_factory = runtime_factory or _default_runtime_factory
        self._lock = threading.RLock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._runtime_context: AbstractAsyncContextManager | None = None
        self._answering_service: Any = None
        self._closed = False

    @property
    def initialized(self) -> bool:
        return self._answering_service is not None

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        if self._closed:
            raise RuntimeError("evaluation worker runtime is closed")
        if self._loop is None:
            self._loop = asyncio.new_event_loop()
        return self._loop

    def _ensure_runtime(self) -> Any:
        if self._answering_service is not None:
            return self._answering_service
        loop = self._ensure_loop()
        context = self._runtime_factory()
        try:
            service = loop.run_until_complete(context.__aenter__())
        except BaseException as exc:
            self._runtime_context = None
            self._answering_service = None
            raise WorkerRuntimeInitializationError(
                worker_initialization_error_code(exc)
            ) from None
        self._runtime_context = context
        self._answering_service = service
        return service

    def run_with_service(
        self,
        operation: Callable[[Any], Awaitable[Any]],
    ) -> Any:
        """Run one task on the persistent loop with the shared service."""

        with self._lock:
            service = self._ensure_runtime()
            return self._ensure_loop().run_until_complete(operation(service))

    def run_maintenance(self, awaitable: Awaitable[Any]) -> Any:
        """Run failure persistence on the same loop, even before init succeeds."""

        with self._lock:
            return self._ensure_loop().run_until_complete(awaitable)

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            loop = self._loop
            context = self._runtime_context
            self._runtime_context = None
            self._answering_service = None
            if loop is not None and context is not None:
                try:
                    loop.run_until_complete(context.__aexit__(None, None, None))
                except Exception:
                    pass
            if loop is not None:
                try:
                    loop.run_until_complete(loop.shutdown_asyncgens())
                except Exception:
                    pass
                loop.close()
            self._loop = None
            self._closed = True


_singleton_lock = threading.Lock()
_worker_runtime: WorkerProcessRuntime | None = None


def get_worker_runtime() -> WorkerProcessRuntime:
    global _worker_runtime
    with _singleton_lock:
        if _worker_runtime is None:
            _worker_runtime = WorkerProcessRuntime()
        return _worker_runtime


def close_worker_runtime() -> None:
    global _worker_runtime
    with _singleton_lock:
        runtime = _worker_runtime
        _worker_runtime = None
    if runtime is not None:
        runtime.close()
