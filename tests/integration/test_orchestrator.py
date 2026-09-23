from __future__ import annotations
import sys
from pathlib import Path
import yaml
import pytest
from orch.core.orchestrator import Orchestrator
from orch.models.state import TaskState

@pytest.mark.asyncio
async def test_orchestrator_spawns_fake_agent_and_freezes_candidate(git_repo: Path) -> None:
    cfg={'harnesses':{'default':'fake','definitions':{'fake':{'type':'generic','command':[sys.executable,str(Path(__file__).parents[1]/'fixtures'/'fake_agent.py'),'--behavior','success'],'prompt_delivery':'stdin','env_allowlist':[]}}}}
    (git_repo/'.orch').mkdir(exist_ok=True);(git_repo/'.orch/config.yaml').write_text(yaml.safe_dump(cfg))
    plan=git_repo/'tasks.yaml';plan.write_text(yaml.safe_dump({'version':1,'project':{'name':'x'},'tasks':[{'id':'A','title':'A','description':'x','role':'core_backend','dependencies':[],'ownership':{'allowed_paths':['src/**']},'resources':{},'acceptance':{'criteria':[]},'timeout_seconds':30,'max_attempts':1,'priority':0,'allow_noop':False}]}))
    o=Orchestrator.open(git_repo);rid=o.activate_plan(plan);result=await o.spawn_task('A',rid)
    assert result.state is TaskState.AUDIT_READY
    a=o.current_attempt('A',rid);assert a.head_sha and a.prompt_sha256
    assert (git_repo/'.orch/prompts/A'/a.attempt_id/'manifest.json').exists()
    o.close()

@pytest.mark.asyncio
async def test_dirty_agent_enters_recovering(git_repo: Path) -> None:
    cfg={'harnesses':{'default':'fake','definitions':{'fake':{'type':'generic','command':[sys.executable,str(Path(__file__).parents[1]/'fixtures'/'fake_agent.py'),'--behavior','dirty'],'prompt_delivery':'stdin','env_allowlist':[]}}}}
    (git_repo/'.orch').mkdir(exist_ok=True);(git_repo/'.orch/config.yaml').write_text(yaml.safe_dump(cfg))
    plan=git_repo/'tasks.yaml';plan.write_text(yaml.safe_dump({'version':1,'project':{'name':'x'},'tasks':[{'id':'A','title':'A','description':'x','role':'core_backend','dependencies':[],'ownership':{'allowed_paths':['src/**']},'resources':{},'acceptance':{'criteria':[]},'timeout_seconds':30,'max_attempts':1,'priority':0,'allow_noop':False}]}))
    o=Orchestrator.open(git_repo);rid=o.activate_plan(plan);result=await o.spawn_task('A',rid);assert result.state is TaskState.RECOVERING;o.close()

@pytest.mark.asyncio
async def test_orchestrator_persists_process_and_frozen_worktree(git_repo: Path) -> None:
    cfg={'harnesses':{'default':'fake','definitions':{'fake':{'type':'generic','command':[sys.executable,str(Path(__file__).parents[1]/'fixtures'/'fake_agent.py'),'--behavior','success'],'prompt_delivery':'stdin','env_allowlist':[]}}}}
    (git_repo/'.orch').mkdir(exist_ok=True);(git_repo/'.orch/config.yaml').write_text(yaml.safe_dump(cfg))
    plan=git_repo/'tasks.yaml';plan.write_text(yaml.safe_dump({'version':1,'project':{'name':'x'},'tasks':[{'id':'A','title':'A','description':'x','role':'core_backend','dependencies':[],'ownership':{'allowed_paths':['src/**']},'resources':{},'acceptance':{'criteria':[]},'timeout_seconds':30,'max_attempts':1,'priority':0,'allow_noop':False}]}))
    o=Orchestrator.open(git_repo);rid=o.activate_plan(plan);await o.spawn_task('A',rid);a=o.current_attempt('A',rid)
    proc=o.store._conn.execute('SELECT status,command_fingerprint FROM agent_processes WHERE attempt_id=?',(a.attempt_id,)).fetchone();wt=o.store._conn.execute('SELECT status FROM worktrees WHERE attempt_id=?',(a.attempt_id,)).fetchone()
    assert proc['status']=='EXITED' and proc['command_fingerprint']
    assert wt['status']=='AUDIT_FROZEN';o.close()
