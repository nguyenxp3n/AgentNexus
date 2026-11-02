from __future__ import annotations
import logging,re,threading
from contextlib import contextmanager
from contextvars import ContextVar

_PATTERNS=[re.compile(r'ghp_[A-Za-z0-9]{20,}'),re.compile(r'sk-[A-Za-z0-9_-]{16,}'),re.compile(r'(?i)(bearer\s+)[A-Za-z0-9._-]+')]
def redact_text(text:str)->str:
    for p in _PATTERNS:text=p.sub(lambda m: (m.group(1) if m.lastindex else '')+'[REDACTED]',text)
    return text
class RedactingFormatter(logging.Formatter):
    def format(self,record):
        return redact_text(super().format(record))
class OperationalCounters:
    def __init__(self):self._d={};self._lock=threading.Lock()
    def increment(self,name:str,amount:int=1):
        with self._lock:self._d[name]=self._d.get(name,0)+amount
    def snapshot(self):
        with self._lock:return dict(self._d)
_log_ctx:ContextVar[dict|None]=ContextVar('orch_log_ctx',default=None)
@contextmanager
def bind_log_context(**values):
    curr=_log_ctx.get()
    t=_log_ctx.set({**(curr or {}),**values})
    try:yield
    finally:_log_ctx.reset(t)
