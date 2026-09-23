from __future__ import annotations
import subprocess,sys,yaml
from pathlib import Path
import pytest
from typer.testing import CliRunner
from orch.cli.main import app
from orch.core.audit import AuditRunner,task_spec_digest
from orch.core.git import GitRepository
from orch.core.merger import MergeController
from orch.core.worktree import WorktreeManager
from orch.core.harness.generic_cli import GenericCLIAdapter
from orch.errors import AuditCertificateStale,WorktreeError
from orch.models.execution import TaskAttempt
from orch.models.state import TaskState
from orch.models.task import TaskSpec


def task(*,criteria=None)->TaskSpec:
    return TaskSpec.model_validate({'id':'T','title':'T','description':'x','role':'core_backend','dependencies':[],'ownership':{'allowed_paths':['src/**']},'resources':{},'acceptance':{'criteria':criteria or []},'timeout_seconds':60,'max_attempts':1,'priority':0,'allow_noop':False})

def make_candidate(repo:Path):
    gr=GitRepository(repo);base=gr.head();subprocess.run(['git','checkout','-b','feat'],cwd=repo,check=True,capture_output=True);(repo/'src').mkdir();(repo/'src/a.py').write_text('x=1\n');subprocess.run(['git','add','.'],cwd=repo,check=True);subprocess.run(['git','commit','-m','feat'],cwd=repo,check=True,capture_output=True);tsk=task();a=TaskAttempt(run_id='R',task_id='T',attempt_id='A',attempt_number=1,generation=1,branch='feat',worktree_path=str(repo),base_sha=base,head_sha=gr.head(),task_spec_sha256=task_spec_digest(tsk),prompt_sha256='c'*64,state=TaskState.AUDIT_READY,version=0);r=AuditRunner(repo).run(a,tsk);subprocess.run(['git','checkout','main'],cwd=repo,check=True,capture_output=True);return a.model_copy(update={'state':TaskState.AUDITED}),r

def test_tampered_audit_evidence_blocks_merge(git_repo:Path)->None:
    a,r=make_candidate(git_repo);Path(r.evidence[0].path).write_text('tampered')
    with pytest.raises(AuditCertificateStale):MergeController(git_repo).merge_one(a,r,expected_integration_sha=GitRepository(git_repo).head())

def test_manual_required_acceptance_never_auto_passes(git_repo:Path)->None:
    gr=GitRepository(git_repo);base=gr.head();subprocess.run(['git','checkout','-b','feat'],cwd=git_repo,check=True,capture_output=True);(git_repo/'src').mkdir();(git_repo/'src/a.py').write_text('x=1');subprocess.run(['git','add','.'],cwd=git_repo,check=True);subprocess.run(['git','commit','-m','feat'],cwd=git_repo,check=True,capture_output=True)
    t=task(criteria=[{'id':'M','description':'human review','verification':{'type':'manual_review','required':True}}]);a=TaskAttempt(run_id='R',task_id='T',attempt_id='A',attempt_number=1,generation=1,branch='feat',worktree_path=str(git_repo),base_sha=base,head_sha=gr.head(),task_spec_sha256=task_spec_digest(t),state=TaskState.AUDIT_READY,version=0)
    assert AuditRunner(git_repo).run(a,t).disposition.value!='PASS'

def test_protected_branch_worktree_is_rejected(git_repo:Path)->None:
    a=TaskAttempt(run_id='R',task_id='T',attempt_id='A',attempt_number=1,generation=1,branch='main',worktree_path='',base_sha=GitRepository(git_repo).head(),task_spec_sha256='b'*64,state=TaskState.ASSIGNED,version=0)
    with pytest.raises(WorktreeError):WorktreeManager(git_repo,git_repo/'.worktrees').create(a)

def test_argument_prompt_is_single_argv_and_not_shell(tmp_path:Path)->None:
    payload='hello; touch PWNED'
    a=GenericCLIAdapter([sys.executable,'-c','import sys;print(sys.argv[1])','{prompt}'],prompt_delivery='argument');p=a.prepare(prompt=payload,cwd=tmp_path,env={})
    subprocess.run(p.argv,cwd=tmp_path,check=True,capture_output=True,text=True)
    assert not (tmp_path/'PWNED').exists()

def test_plan_validate_rejects_parallel_overlap(git_repo:Path)->None:
    plan=git_repo/'tasks.yaml';base={'title':'x','description':'x','role':'core_backend','dependencies':[],'resources':{},'acceptance':{'criteria':[]},'timeout_seconds':60,'max_attempts':1,'priority':0,'allow_noop':True}
    plan.write_text(yaml.safe_dump({'version':1,'project':{'name':'x'},'tasks':[{'id':'A',**base,'ownership':{'allowed_paths':['src/**']}},{'id':'B',**base,'ownership':{'allowed_paths':['src/auth/**']}}]}))
    r=CliRunner().invoke(app,['plan','validate',str(plan),'--repo',str(git_repo)])
    assert r.exit_code==11
