from __future__ import annotations
import os, subprocess
from pathlib import Path
import pytest
from orch.core.git import GitRepository
from orch.core.worktree import WorktreeManager
from orch.core.environment import RuntimeEnvironmentBuilder
from orch.models.execution import TaskAttempt
from orch.models.state import TaskState


def attempt(repo: Path, base: str, aid: str='ATT-1') -> TaskAttempt:
    return TaskAttempt(run_id='RUN-1',task_id='TASK-1',attempt_id=aid,attempt_number=1,generation=1,
        branch=f'orch/RUN-1/TASK-1/{aid}',worktree_path='',base_sha=base,task_spec_sha256='b'*64,state=TaskState.ASSIGNED,version=0)


def test_worktree_is_created_from_exact_base_sha(git_repo: Path) -> None:
    gr=GitRepository(git_repo); base=gr.head(); manager=WorktreeManager(git_repo, git_repo/'.worktrees')
    ws=manager.create(attempt(git_repo,base))
    assert GitRepository(ws.path).head()==base
    assert GitRepository(ws.path).branch()==ws.branch


def test_worktree_inspection_reports_dirty_and_untracked(git_repo: Path) -> None:
    gr=GitRepository(git_repo); manager=WorktreeManager(git_repo,git_repo/'.worktrees'); ws=manager.create(attempt(git_repo,gr.head()))
    (ws.path/'new.txt').write_text('x')
    i=manager.inspect(ws.path); assert i.dirty and 'new.txt' in i.untracked


def test_worktree_remove_refuses_arbitrary_path(git_repo: Path, tmp_path: Path) -> None:
    manager=WorktreeManager(git_repo,git_repo/'.worktrees')
    with pytest.raises(ValueError): manager.remove(tmp_path/'elsewhere')


def test_runtime_environment_is_attempt_scoped(git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('SAFE_ALLOWED','ok'); monkeypatch.setenv('GITHUB_TOKEN','secret')
    a=attempt(git_repo,GitRepository(git_repo).head())
    env=RuntimeEnvironmentBuilder(git_repo, allowlist={'SAFE_ALLOWED'}).build(a)
    assert env.env['ORCH_ATTEMPT_ID']=='ATT-1'
    assert Path(env.env['TMPDIR']).is_relative_to(git_repo/'.orch'/'runtime'/'ATT-1')
    assert env.env['SAFE_ALLOWED']=='ok' and 'GITHUB_TOKEN' not in env.env
