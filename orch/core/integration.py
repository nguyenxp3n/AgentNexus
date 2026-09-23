from __future__ import annotations
import subprocess
from dataclasses import dataclass
from pathlib import Path
from orch.core.git import GitRepository
from orch.errors import WorktreeError
@dataclass(frozen=True)
class IntegrationWorkspace:path:Path;branch:str;base_sha:str
class IntegrationManager:
    def __init__(self,repo:Path,root:Path|None=None):self.repo=Path(repo).resolve();self.root=(Path(root) if root else self.repo/'.worktrees').resolve();self.git=GitRepository(self.repo)
    def ensure(self,run_id:str,base_branch:str='main')->IntegrationWorkspace:
        branch=f'orch/integration/{run_id}';path=self.root/'integration'/run_id;path.parent.mkdir(parents=True,exist_ok=True);base=self.git._out(['rev-parse',base_branch])
        if path.exists():return IntegrationWorkspace(path,GitRepository(path).branch(),base)
        exists=self.git.runner.run(['show-ref','--verify','--quiet',f'refs/heads/{branch}'],self.repo).returncode==0
        args=['worktree','add',str(path),branch] if exists else ['worktree','add','-b',branch,str(path),base]
        r=self.git.runner.run(args,self.repo)
        if r.returncode!=0:raise WorktreeError(r.stderr.strip())
        return IntegrationWorkspace(path,branch,base)
    def verify_expected_head(self,path:Path,expected:str)->bool:return GitRepository(path).head()==expected
