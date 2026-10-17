"""Drain short filesystem work before releasing its worker lease on cancellation.

The shared blocking runner normally permits work to outlive a cancelled waiter.
Audit checkpoint writes/lease acquisition require a stronger local boundary.
Network/model operations do not go through this adapter.
"""
import asyncio
import os


class DurableIO:
    def __init__(self, runner):
        self.runner = runner

    async def run(self, function, /, *args, **kwargs):
        task = asyncio.create_task(self.runner.run(function, *args, **kwargs))
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            # A second shutdown/cancel must not orphan a still-writing thread.
            while not task.done():
                try:
                    await asyncio.shield(task)
                except (asyncio.CancelledError, Exception):
                    pass
            if not task.cancelled():
                try:
                    value = task.result()
                except Exception:
                    pass
                else:
                    if getattr(function, '__name__', '') in {'lease', 'global_lease'}:
                        os.close(value)  # acquired but never delivered to the caller
            raise
