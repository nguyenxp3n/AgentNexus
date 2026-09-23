from __future__ import annotations
from pathlib import Path
from .discovery import discover_executable
from .base import PreparedExecution
class ClaudeCodeAdapter:
    name='claude-code'
    def discover(self):return discover_executable('claude')
    def prepare(self,*,prompt:str,cwd:Path,env:dict[str,str])->PreparedExecution:return PreparedExecution(['claude','-p',prompt],Path(cwd),dict(env))
