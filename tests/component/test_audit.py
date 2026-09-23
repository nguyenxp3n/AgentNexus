from __future__ import annotations
import subprocess
from pathlib import Path
from orch.core.audit import AuditRunner, task_spec_digest
from orch.core.git import GitRepository
from orch.models.audit import AuditDisposition
from orch.models.execution import TaskAttempt
from orch.models.state import TaskState
from orch.models.task import TaskSpec


def make_task(paths: list[str]) -> TaskSpec:
    return TaskSpec.model_validate({'id':'T','title':'T','description':'x','role':'core_backend','dependencies':[],
        'ownership':{'allowed_paths':paths},'resources':{},'acceptance':{'criteria':[]},'timeout_seconds':60,'max_attempts':1,'priority':0,'allow_noop':False})


def commit_file(repo: Path, name: str, content: str='x') -> tuple[str,str]:
    gr=GitRepository(repo); base=gr.head(); (repo/name).parent.mkdir(parents=True,exist_ok=True); (repo/name).write_text(content)
    subprocess.run(['git','add',name],cwd=repo,check=True); subprocess.run(['git','commit','-m','change'],cwd=repo,check=True,capture_output=True)
    return base,gr.head()


def test_audit_passes_clean_in_scope_candidate(git_repo: Path) -> None:
    base,head=commit_file(git_repo,'src/a.py','print(1)')
    tsk=make_task(['src/**']); a=TaskAttempt(run_id='R',task_id='T',attempt_id='A',attempt_number=1,generation=1,branch='main',worktree_path=str(git_repo),base_sha=base,head_sha=head,task_spec_sha256=task_spec_digest(tsk),prompt_sha256='c'*64,state=TaskState.AUDIT_READY,version=0)
    r=AuditRunner(git_repo).run(a,tsk)
    assert r.disposition is AuditDisposition.PASS and len(r.steps)==7 and r.certificate_sha256


def test_audit_rejects_scope_expansion(git_repo: Path) -> None:
    base,head=commit_file(git_repo,'.github/x.yml','x')
    tsk=make_task(['src/**']); a=TaskAttempt(run_id='R',task_id='T',attempt_id='A',attempt_number=1,generation=1,branch='main',worktree_path=str(git_repo),base_sha=base,head_sha=head,task_spec_sha256=task_spec_digest(tsk),prompt_sha256='c'*64,state=TaskState.AUDIT_READY,version=0)
    r=AuditRunner(git_repo).run(a,tsk)
    assert r.disposition is not AuditDisposition.PASS
    assert any(f.code=='SCOPE_EXPANSION_VIOLATION' for f in r.findings)


def test_audit_rejects_secret(git_repo: Path) -> None:
    base,head=commit_file(git_repo,'src/key.py','KEY="ghp_123456789012345678901234567890123456"')
    tsk=make_task(['src/**']); a=TaskAttempt(run_id='R',task_id='T',attempt_id='A',attempt_number=1,generation=1,branch='main',worktree_path=str(git_repo),base_sha=base,head_sha=head,task_spec_sha256=task_spec_digest(tsk),prompt_sha256='c'*64,state=TaskState.AUDIT_READY,version=0)
    r=AuditRunner(git_repo).run(a,tsk)
    assert any(f.code=='SECRET_DETECTED' for f in r.findings)
