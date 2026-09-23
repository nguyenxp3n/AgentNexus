from __future__ import annotations
from pathlib import Path
from .discovery import discover_executable
from .base import PreparedExecution
class AntigravityAdapter:
    name='antigravity'
    def discover(self):return discover_executable('agy')
    def prepare(self,*,prompt:str,cwd:Path,env:dict[str,str])->PreparedExecution:return PreparedExecution(['agy','--prompt',prompt],Path(cwd),dict(env))
