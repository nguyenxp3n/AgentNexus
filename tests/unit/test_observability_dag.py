from __future__ import annotations
import logging
from io import StringIO
from orch.core.observability import RedactingFormatter, OperationalCounters
from orch.core.dag import DagPlan
from orch.models.state import TaskState
from orch.models.task import ProjectPlan


def t(i: str, deps: list[str]|None=None) -> dict:
    return {'id':i,'title':i,'description':'x','role':'core_backend','dependencies':deps or [],
        'ownership':{'allowed_paths':[f'{i.lower()}/**']},'resources':{},'acceptance':{'criteria':[]},
        'timeout_seconds':60,'max_attempts':1,'priority':0,'allow_noop':False}


def test_redacting_formatter_does_not_persist_known_secret() -> None:
    fmt=RedactingFormatter('%(message)s'); rec=logging.LogRecord('x',20,'',0,'token ghp_123456789012345678901234567890123456',(),None)
    out=fmt.format(rec)
    assert 'ghp_' not in out and '[REDACTED]' in out


def test_operational_counters_increment_named_events() -> None:
    c=OperationalCounters(); c.increment('tasks_started'); c.increment('tasks_started'); assert c.snapshot()['tasks_started']==2


def test_execution_waves_use_topological_generations() -> None:
    plan=ProjectPlan.model_validate({'version':1,'project':{'name':'x'},'tasks':[t('A'),t('B'),t('C',['A','B']),t('D',['C'])]})
    assert DagPlan.from_plan(plan).execution_waves()==[['A','B'],['C'],['D']]


def test_cycle_reports_actual_cycle() -> None:
    plan=ProjectPlan.model_validate({'version':1,'project':{'name':'x'},'tasks':[t('A',['C']),t('B',['A']),t('C',['B'])]})
    r=DagPlan.from_plan(plan).validate(); assert not r.ok; assert any(c[0]==c[-1] and set(c[:-1])=={'A','B','C'} for c in r.cycles)


def test_missing_and_self_dependencies_are_reported() -> None:
    p1=ProjectPlan.model_validate({'version':1,'project':{'name':'x'},'tasks':[t('A',['Z'])]})
    r1=DagPlan.from_plan(p1).validate(); assert 'A:Z' in r1.missing_dependencies
    p2=ProjectPlan.model_validate({'version':1,'project':{'name':'x'},'tasks':[t('A',['A'])]})
    r2=DagPlan.from_plan(p2).validate(); assert 'A' in r2.self_dependencies


def test_integrated_completion_is_default_dependency_policy() -> None:
    p=ProjectPlan.model_validate({'version':1,'project':{'name':'x'},'tasks':[t('A'),t('B',['A'])]})
    d=DagPlan.from_plan(p)
    assert not d.dependencies_satisfied('B', {'A':TaskState.AUDIT_READY})
    assert d.dependencies_satisfied('B', {'A':TaskState.COMPLETED})
