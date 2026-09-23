from __future__ import annotations
import subprocess
from pathlib import Path
import pytest
from orch.core.audit import AuditRunner,task_spec_digest
from orch.core.git import GitRepository
from orch.core.merger import MergeController
from orch.core.recovery import RecoveryController,RecoveryKind
from orch.core.state import StateStore
from orch.models.execution import TaskAttempt
from orch.models.state import TaskState,RunState
from orch.models.task import TaskSpec

class Crash(RuntimeError):pass

def t()->TaskSpec:return TaskSpec.model_validate({'id':'T','title':'T','description':'x','role':'core_backend','dependencies':[],'ownership':{'allowed_paths':['src/**']},'resources':{},'acceptance':{'criteria':[]},'timeout_seconds':60,'max_attempts':1,'priority':0,'allow_noop':False})

def test_recovery_proves_merge_from_parent_shas_after_crash(git_repo:Path)->None:
    s=StateStore.open(git_repo/'.orch/state.db');s.initialize();s.create_run('R',RunState.INTEGRATING);gr=GitRepository(git_repo);base=gr.head();subprocess.run(['git','checkout','-b','feat'],cwd=git_repo,check=True,capture_output=True);(git_repo/'src').mkdir();(git_repo/'src/a.py').write_text('x=1');subprocess.run(['git','add','.'],cwd=git_repo,check=True);subprocess.run(['git','commit','-m','feat'],cwd=git_repo,check=True,capture_output=True);tsk=t();a=TaskAttempt(run_id='R',task_id='T',attempt_id='A',attempt_number=1,generation=1,branch='feat',worktree_path=str(git_repo),base_sha=base,head_sha=gr.head(),task_spec_sha256=task_spec_digest(tsk),state=TaskState.AUDITED,version=0);s.create_task_attempt(a);report=AuditRunner(git_repo).run(a.model_copy(update={'state':TaskState.AUDIT_READY}),tsk);subprocess.run(['git','checkout','main'],cwd=git_repo,check=True,capture_output=True)
    def hook(stage):
        if stage=='AFTER_GIT_MERGE':raise Crash()
    with pytest.raises(Crash):MergeController(git_repo,store=s,fault_hook=hook).merge_one(a,report,expected_integration_sha=base)
    rc=RecoveryController(git_repo,s);items=rc.scan();assert any(i['kind']==RecoveryKind.INTERRUPTED_MERGE for i in items);result=rc.apply(rc.plan(items),'R');assert result['safe_mode'] is False
    row=s._conn.execute("SELECT status FROM merge_attempts LIMIT 1").fetchone();assert row['status']=='RECONCILED';s.close()
