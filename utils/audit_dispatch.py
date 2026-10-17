"""Task-local opt-in audit accounting. Unbound production calls are unchanged."""
from contextlib import contextmanager
from contextvars import ContextVar

_observer=ContextVar('audit_dispatch_observer',default=None)
_completion=ContextVar('audit_completion_metadata',default={})


@contextmanager
def observe_audit(observer):
    token=_observer.set(observer)
    try:yield
    finally:_observer.reset(token)


@contextmanager
def completion_metadata(responsibility,prompt_tokens=None,on_dispatch=None):
    token=_completion.set({'responsibility':responsibility,'prompt_tokens':prompt_tokens,'on_dispatch':on_dispatch})
    try:yield
    finally:_completion.reset(token)


def current_audit():return _observer.get()


async def audit_dispatch(kind,operation,**metadata):
    observer=_observer.get()
    if observer is None:return await operation()
    return await observer.dispatch(kind,operation,**{**(_completion.get() if kind=='completion' else {}),**metadata})
