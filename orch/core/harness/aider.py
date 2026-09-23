from __future__ import annotations
from pathlib import Path
from .discovery import discover_executable
from .base import PreparedExecution
class AiderAdapter:
    name='aider'
    def discover(self):return discover_executable('aider')
    def prepare(self,*,prompt:str,cwd:Path,env:dict[str,str])->PreparedExecution:return PreparedExecution(['aider','--message',prompt,'--yes'],Path(cwd),dict(env))
