from __future__ import annotations
import subprocess
from pathlib import Path
import pytest
from orch.core.audit import AuditRunner, task_spec_digest
from orch.core.git import GitRepository
from orch.core.merger import MergeController
from orch.errors import AuditCertificateStale, IntegrationBranchDrift, RegressionFailed
from orch.models.execution import TaskAttempt
from orch.models.state import TaskState
from orch.models.task import TaskSpec


def task() -> TaskSpec:
    return TaskSpec.model_validate({'id':'T','title':'T','description':'x','role':'core_backend','dependencies':[],
        'ownership':{'allowed_paths':['src/**']},'resources':{},'acceptance':{'criteria':[]},'timeout_seconds':60,'max_attempts':1,'priority':0,'allow_noop':False})


def candidate(repo: Path) -> tuple[TaskAttempt, object]:
    gr=GitRepository(repo); base=gr.head(); subprocess.run(['git','checkout','-b','feat'],cwd=repo,check=True,capture_output=True); (repo/'src').mkdir(); (repo/'src/a.py').write_text('x=1\n'); subprocess.run(['git','add','.'],cwd=repo,check=True); subprocess.run(['git','commit','-m','feat'],cwd=repo,check=True,capture_output=True); head=gr.head();
    tsk=task(); a=TaskAttempt(run_id='R',task_id='T',attempt_id='A',attempt_number=1,generation=1,branch='feat',worktree_path=str(repo),base_sha=base,head_sha=head,task_spec_sha256=task_spec_digest(tsk),prompt_sha256='c'*64,state=TaskState.AUDITED,version=0)
    report=AuditRunner(repo).run(a.model_copy(update={'state':TaskState.AUDIT_READY}),tsk); subprocess.run(['git','checkout','main'],cwd=repo,check=True,capture_output=True); return a,report


def test_merge_rejects_candidate_when_head_no_longer_matches_certificate(git_repo: Path) -> None:
    a,report=candidate(git_repo); subprocess.run(['git','checkout','feat'],cwd=git_repo,check=True,capture_output=True); (git_repo/'src/b.py').write_text('y=2'); subprocess.run(['git','add','.'],cwd=git_repo,check=True); subprocess.run(['git','commit','-m','mutate'],cwd=git_repo,check=True,capture_output=True); subprocess.run(['git','checkout','main'],cwd=git_repo,check=True,capture_output=True)
    with pytest.raises(AuditCertificateStale): MergeController(git_repo).merge_one(a,report,expected_integration_sha=GitRepository(git_repo).head())


def test_merge_rejects_when_integration_head_moved_externally(git_repo: Path) -> None:
    a,report=candidate(git_repo); expected=GitRepository(git_repo).head(); (git_repo/'README.md').write_text('moved\n'); subprocess.run(['git','add','README.md'],cwd=git_repo,check=True); subprocess.run(['git','commit','-m','move'],cwd=git_repo,check=True,capture_output=True)
    with pytest.raises(IntegrationBranchDrift): MergeController(git_repo).merge_one(a,report,expected_integration_sha=expected)


def test_regression_failure_restores_exact_premerge_sha(git_repo: Path) -> None:
    a,report=candidate(git_repo); before=GitRepository(git_repo).head();
    with pytest.raises(RegressionFailed): MergeController(git_repo,regression_commands=[['python','-c','import sys;sys.exit(2)']]).merge_one(a,report,expected_integration_sha=before)
    assert GitRepository(git_repo).head()==before
