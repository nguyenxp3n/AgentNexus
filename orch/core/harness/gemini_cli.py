from __future__ import annotations
from pathlib import Path
from .discovery import discover_executable
from .base import PreparedExecution
class GeminiCLIAdapter:
    name='gemini-cli'
    def discover(self):return discover_executable('gemini')
    def prepare(self,*,prompt:str,cwd:Path,env:dict[str,str])->PreparedExecution:return PreparedExecution(['gemini','-p',prompt],Path(cwd),dict(env))
