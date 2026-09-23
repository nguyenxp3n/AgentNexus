from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
@dataclass(frozen=True)
class HarnessCapabilities:
    available:bool; executable:str|None=None; version:str|None=None; headless:bool=True; stdin_prompt:bool=False; prompt_argument:bool=False; supports_resume:bool=False; supports_json_output:bool=False; supports_streaming:bool=True; sandbox_mode:str='external_trust_boundary'
@dataclass(frozen=True)
class PreparedExecution:
    argv:list[str]; cwd:Path; env:dict[str,str]; stdin_text:str|None=None
class HarnessAdapter(Protocol):
    name:str
    def discover(self)->HarnessCapabilities:...
    def prepare(self,*,prompt:str,cwd:Path,env:dict[str,str])->PreparedExecution:...
