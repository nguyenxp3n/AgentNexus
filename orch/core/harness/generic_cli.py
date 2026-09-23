from __future__ import annotations
import shutil
from pathlib import Path
from orch.core.harness.base import HarnessCapabilities,PreparedExecution
class GenericCLIAdapter:
    name='generic'
    def __init__(self,command:list[str],prompt_delivery:str='stdin'):
        if not command:raise ValueError('command required')
        self.command=list(command);self.prompt_delivery=prompt_delivery
    def discover(self)->HarnessCapabilities:
        exe=shutil.which(self.command[0]) or (self.command[0] if Path(self.command[0]).exists() else None)
        return HarnessCapabilities(bool(exe),exe,stdin_prompt=self.prompt_delivery=='stdin',prompt_argument=self.prompt_delivery=='argument')
    def prepare(self,*,prompt:str,cwd:Path,env:dict[str,str])->PreparedExecution:
        argv=list(self.command);stdin=None
        if self.prompt_delivery=='stdin':stdin=prompt
        elif self.prompt_delivery=='argument':argv=[prompt if x=='{prompt}' else x for x in argv];
        else:raise ValueError('unsupported prompt delivery')
        return PreparedExecution(argv=argv,cwd=Path(cwd),env=dict(env),stdin_text=stdin)
