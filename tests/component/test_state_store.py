from __future__ import annotations
from pathlib import Path
import pytest
from orch.core.state import StateStore, StateVersionConflict
from orch.models.execution import TaskAttempt
from orch.models.state import TaskState, TransitionActor, RunState


def make_attempt(state: TaskState=TaskState.PENDING, version: int=0) -> TaskAttempt:
    return TaskAttempt(run_id='RUN-1', task_id='A', attempt_id='ATT-1', attempt_number=1, generation=1,
        branch='orch/RUN-1/A/ATT-1', worktree_path='.worktrees/RUN-1/A/ATT-1', base_sha='a'*40,
        task_spec_sha256='b'*64, prompt_sha256=None, state=state, version=version)


def setup_store(path: Path) -> StateStore:
    s=StateStore.open(path); s.initialize(); s.create_run('RUN-1', RunState.PLANNED); return s


def test_state_store_initializes_required_pragmas(tmp_path: Path) -> None:
    store = StateStore.open(tmp_path/'state.db'); store.initialize()
    assert str(store.scalar('PRAGMA journal_mode')).lower() == 'wal'
    assert store.scalar('PRAGMA foreign_keys') == 1
    assert store.schema_version() == 1
    store.close()


def test_state_transition_and_event_commit_atomically(tmp_path: Path) -> None:
    store=setup_store(tmp_path/'state.db'); attempt=make_attempt(); store.create_task_attempt(attempt)
    updated=store.transition_task('ATT-1', expected_state=TaskState.PENDING, expected_version=0,
        to_state=TaskState.READY, actor=TransitionActor.SCHEDULER)
    assert updated.state is TaskState.READY and updated.version == 1
    assert store.events_for_attempt('ATT-1')[-1].event_type == 'TASK_STATE_CHANGED'
    store.close()


def test_only_one_connection_can_claim_same_ready_attempt(tmp_path: Path) -> None:
    db=tmp_path/'state.db'; first=setup_store(db); a=make_attempt(TaskState.READY); first.create_task_attempt(a)
    second=StateStore.open(db); second.initialize()
    first.transition_task('ATT-1', expected_state=TaskState.READY, expected_version=0,
        to_state=TaskState.ASSIGNED, actor=TransitionActor.ORCHESTRATOR)
    with pytest.raises(StateVersionConflict):
        second.transition_task('ATT-1', expected_state=TaskState.READY, expected_version=0,
            to_state=TaskState.ASSIGNED, actor=TransitionActor.ORCHESTRATOR)
    first.close(); second.close()


def test_safe_mode_is_durable(tmp_path: Path) -> None:
    s=setup_store(tmp_path/'state.db'); s.enter_safe_mode('RUN-1','unknown physical state')
    assert s.get_run_state('RUN-1') is RunState.SAFE_MODE
    assert 'unknown physical state' in s.safe_mode_reason('RUN-1')
    s.close()


def test_state_store_context_manager(tmp_path: Path) -> None:
    with StateStore.open(tmp_path/'state.db') as store:
        store.initialize()
        assert store.schema_version() == 1
