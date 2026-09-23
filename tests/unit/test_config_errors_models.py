from __future__ import annotations
from pathlib import Path
import pytest
from pydantic import ValidationError

from orch.config import OrchConfig, load_config
from orch.errors import ExitCode
from orch.models.state import TaskState, TransitionActor, validate_task_transition
from orch.models.task import AgentRole, OwnershipSpec, TaskSpec, ProjectPlan


def task_payload(task_id: str='A') -> dict:
    return {
        'id': task_id, 'title': task_id, 'description': 'x', 'role': AgentRole.CORE_BACKEND,
        'dependencies': [], 'ownership': {'allowed_paths':['src/**']}, 'resources': {},
        'acceptance': {'criteria': []}, 'timeout_seconds': 60, 'max_attempts': 2,
        'priority': 0, 'allow_noop': False,
    }


def test_config_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        OrchConfig.model_validate({'scheduler': {'max_agnts': 8}})


def test_load_config_applies_nested_environment_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / '.orch').mkdir()
    (tmp_path / '.orch' / 'config.yaml').write_text('scheduler:\n  max_parallel_agents: 4\n')
    monkeypatch.setenv('ORCH_SCHEDULER__MAX_PARALLEL_AGENTS', '7')
    assert load_config(tmp_path).scheduler.max_parallel_agents == 7


def test_exit_code_families_are_stable() -> None:
    assert ExitCode.SUCCESS == 0
    assert 10 <= ExitCode.CONFIG_INVALID <= 19
    assert 20 <= ExitCode.AUDIT_FAILED <= 29
    assert 90 <= ExitCode.GLOBAL_SAFE_MODE <= 99


def test_empty_write_ownership_is_deny_write() -> None:
    ownership = OwnershipSpec()
    assert ownership.allowed_paths == []
    assert ownership.can_write_anything is False


def test_task_rejects_unknown_field() -> None:
    payload = task_payload()
    payload['surprise'] = True
    with pytest.raises(ValidationError):
        TaskSpec.model_validate(payload)


def test_project_plan_rejects_duplicate_ids() -> None:
    with pytest.raises(ValidationError):
        ProjectPlan.model_validate({'version':1,'project':{'name':'x'},'tasks':[task_payload('A'),task_payload('A')]})


def test_worker_cannot_complete_task() -> None:
    assert not validate_task_transition(TaskState.IN_PROGRESS, TaskState.COMPLETED, TransitionActor.WORKER)


def test_authorities_enforce_happy_path() -> None:
    assert validate_task_transition(TaskState.PENDING, TaskState.READY, TransitionActor.SCHEDULER)
    assert validate_task_transition(TaskState.READY, TaskState.ASSIGNED, TransitionActor.ORCHESTRATOR)
    assert validate_task_transition(TaskState.AUDIT_READY, TaskState.AUDITED, TransitionActor.AUDITOR)
    assert validate_task_transition(TaskState.AUDITED, TaskState.MERGING, TransitionActor.MERGER)
    assert validate_task_transition(TaskState.MERGING, TaskState.COMPLETED, TransitionActor.MERGER)
