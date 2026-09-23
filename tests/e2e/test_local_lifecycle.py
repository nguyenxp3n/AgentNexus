from __future__ import annotations
import subprocess, sys
from pathlib import Path
from orch.core.dag import DagPlan
from orch.core.state import StateStore
from orch.core.locks import LockManager
from orch.core.git import GitRepository
from orch.core.worktree import WorktreeManager
from orch.core.audit import AuditRunner, task_spec_digest
from orch.core.merger import MergeController
from orch.models.execution import TaskAttempt
from orch.models.lock import ResourceRequest
from orch.models.state import TaskState, RunState, TransitionActor
from orch.models.task import ProjectPlan, TaskSpec


def task_dict() -> dict:
    return {'id':'A','title':'A','description':'x','role':'core_backend','dependencies':[], 'ownership':{'allowed_paths':['src/**']}, 'resources':{}, 'acceptance':{'criteria':[]},'timeout_seconds':60,'max_attempts':1,'priority':0,'allow_noop':False}


def test_local_candidate_audit_merge_lifecycle(git_repo: Path, tmp_path: Path) -> None:
    plan=ProjectPlan.model_validate({'version':1,'project':{'name':'x'},'tasks':[task_dict()]}); assert DagPlan.from_plan(plan).validate().ok
    db=git_repo/'.orch/state.db'; s=StateStore.open(db); s.initialize(); s.create_run('R',RunState.RUNNING)
    base=GitRepository(git_repo).head(); tsk=TaskSpec.model_validate(task_dict()); a=TaskAttempt(run_id='R',task_id='A',attempt_id='ATT',attempt_number=1,generation=1,branch='orch/R/A/ATT',worktree_path='',base_sha=base,task_spec_sha256=task_spec_digest(tsk),state=TaskState.READY,version=0); s.create_task_attempt(a)
    lm=LockManager(s,git_repo,{'api':(8500,8502)}); lm.acquire_assignment('ATT',1,ResourceRequest(paths=['src/**']))
    a=s.get_attempt('ATT'); wm=WorktreeManager(git_repo,git_repo/'.worktrees'); ws=wm.create(a)
    src=ws.path/'src'; src.mkdir(); (src/'a.py').write_text('x=1\n'); subprocess.run(['git','add','.'],cwd=ws.path,check=True); subprocess.run(['git','commit','-m','candidate'],cwd=ws.path,check=True,capture_output=True)
    a=s.get_attempt('ATT'); a=s.update_attempt_identity('ATT', head_sha=GitRepository(ws.path).head(), worktree_path=str(ws.path), branch=ws.branch)
    a=s.transition_task('ATT',expected_state=TaskState.ASSIGNED,expected_version=a.version,to_state=TaskState.SPAWNED,actor=TransitionActor.DISPATCHER)
    a=s.transition_task('ATT',expected_state=TaskState.SPAWNED,expected_version=a.version,to_state=TaskState.IN_PROGRESS,actor=TransitionActor.RUNTIME_MONITOR)
    a=s.transition_task('ATT',expected_state=TaskState.IN_PROGRESS,expected_version=a.version,to_state=TaskState.AUDIT_READY,actor=TransitionActor.RUNTIME_MONITOR)
    report=AuditRunner(ws.path).run(a,tsk); assert report.disposition.value=='PASS'
    a=s.transition_task('ATT',expected_state=TaskState.AUDIT_READY,expected_version=a.version,to_state=TaskState.AUDITED,actor=TransitionActor.AUDITOR)
    result=MergeController(git_repo).merge_one(a,report,expected_integration_sha=base); assert result.status.value=='PASS'
    s.close()
