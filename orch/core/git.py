from __future__ import annotations
import subprocess
from dataclasses import dataclass
from pathlib import Path
from orch.errors import WorktreeError
@dataclass(frozen=True)
class GitResult: argv:list[str]; returncode:int; stdout:str; stderr:str
class GitRunner:
    def run(self,argv:list[str],cwd:Path,*,check:bool=False)->GitResult:
        p=subprocess.run(['git',*argv],cwd=Path(cwd),text=True,capture_output=True,shell=False)
        r=GitResult(argv,p.returncode,p.stdout,p.stderr)
        if check and p.returncode!=0:raise WorktreeError(p.stderr.strip() or 'git command failed')
        return r
class GitRepository:
    def __init__(self,path:Path,runner:GitRunner|None=None):self.path=Path(path).resolve();self.runner=runner or GitRunner();self.runner.run(['rev-parse','--is-inside-work-tree'],self.path,check=True)
    def _out(self,args:list[str])->str:return self.runner.run(args,self.path,check=True).stdout.strip()
    def root(self)->Path:return Path(self._out(['rev-parse','--show-toplevel'])).resolve()
    def head(self)->str:return self._out(['rev-parse','HEAD'])
    def branch(self)->str:return self._out(['branch','--show-current'])
    def status_lines(self)->list[str]:return self._out(['status','--porcelain=v1','--untracked-files=all']).splitlines() if self._out(['status','--porcelain=v1','--untracked-files=all']) else []
    def is_clean(self)->bool:return len(self.status_lines())==0
    def merge_base(self,a:str,b:str)->str:return self._out(['merge-base',a,b])
    def diff_names(self,base:str,head:str)->list[str]:
        out=self._out(['diff','--name-only',f'{base}...{head}']);return [x for x in out.splitlines() if x]
    def diff_name_status(self,base:str,head:str)->list[str]:
        out=self._out(['diff','--name-status',f'{base}...{head}']);return [x for x in out.splitlines() if x]
    def diff_patch(self,base:str,head:str)->str:return self.runner.run(['diff',f'{base}...{head}'],self.path,check=True).stdout
    def parents(self,sha:str)->list[str]:return self._out(['show','-s','--format=%P',sha]).split()
