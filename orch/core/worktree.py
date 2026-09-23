from __future__ import annotations
import re,subprocess
from dataclasses import dataclass
from pathlib import Path
from orch.core.git import GitRepository,GitRunner
from orch.errors import WorktreeError
from orch.models.execution import TaskAttempt
@dataclass(frozen=True)
class Workspace: path:Path; branch:str; base_sha:str; attempt_id:str
@dataclass(frozen=True)
class WorktreeInspection: path:Path; branch:str; head_sha:str; dirty:bool; untracked:list[str]; status:list[str]
class WorktreeManager:
    def __init__(self,repo:Path,root:Path,protected:set[str]|None=None):self.repo=Path(repo).resolve();self.root=Path(root).resolve();self.root.mkdir(parents=True,exist_ok=True);self.protected=protected or {'main','master','production'};self.git=GitRepository(self.repo)
    def _safe_branch(self,a:TaskAttempt)->str:
        branch=a.branch or f'orch/{a.run_id}/{a.task_id}/{a.attempt_id[:8]}'
        if branch in self.protected or '..' in branch or branch.startswith('/') or branch.endswith('/') or ' ' in branch:raise WorktreeError('unsafe or protected branch')
        return branch
    def create(self,a:TaskAttempt)->Workspace:
        branch=self._safe_branch(a);path=self.root/a.run_id/a.task_id/a.attempt_id;path.parent.mkdir(parents=True,exist_ok=True)
        if path.exists():raise WorktreeError(f'worktree path exists: {path}')
        p=self.git.runner.run(['worktree','add','-b',branch,str(path),a.base_sha],self.repo)
        if p.returncode!=0:raise WorktreeError(p.stderr.strip())
        repo=GitRepository(path)
        if repo.head()!=a.base_sha or repo.branch()!=branch:
            self.git.runner.run(['worktree','remove','--force',str(path)],self.repo);raise WorktreeError('worktree identity mismatch')
        return Workspace(path,branch,a.base_sha,a.attempt_id)
    def inspect(self,path:Path)->WorktreeInspection:
        p=Path(path).resolve();r=GitRepository(p);status=r.status_lines();untracked=[x[3:] for x in status if x.startswith('?? ')]
        return WorktreeInspection(p,r.branch(),r.head(),bool(status),untracked,status)
    def remove(self,path:Path,*,force:bool=False):
        p=Path(path).resolve()
        if p==self.root or self.root not in p.parents:raise ValueError('refusing to remove worktree outside managed root')
        ins=self.inspect(p)
        if ins.dirty and not force:raise WorktreeError('worktree dirty')
        args=['worktree','remove']+(['--force'] if force else [])+[str(p)];r=self.git.runner.run(args,self.repo)
        if r.returncode!=0:raise WorktreeError(r.stderr.strip())
        self.git.runner.run(['worktree','prune'],self.repo)
