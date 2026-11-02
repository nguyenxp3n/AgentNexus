from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pytest
from orch.core.state import StateStore
from orch.core.locks import LockManager
from orch.errors import ResourceUnavailable, StaleGenerationError
from orch.models.execution import TaskAttempt
from orch.models.lock import ResourceRequest
from orch.models.state import TaskState, RunState


def store_with_attempt(db: Path, aid: str='ATT-1', generation: int=1) -> StateStore:
    s=StateStore.open(db); s.initialize()
    try: s.create_run('RUN-1',RunState.RUNNING)
    except Exception: pass
    a=TaskAttempt(run_id='RUN-1',task_id=aid,attempt_id=aid,attempt_number=1,generation=generation,
        branch=f'orch/{aid}',worktree_path=f'.worktrees/{aid}',base_sha='a'*40,task_spec_sha256='b'*64,
        state=TaskState.READY,version=0)
    try: s.create_task_attempt(a)
    except Exception: pass
    return s


def test_failed_multi_resource_assignment_rolls_back_every_reservation(tmp_path: Path) -> None:
    s=store_with_attempt(tmp_path/'s.db'); lm=LockManager(s,tmp_path,{'api':(8000,8000)})
    lm.acquire_assignment('ATT-1',1,ResourceRequest(paths=['src/**'],migration_count=0,ports={'api':1}))
    s2=store_with_attempt(tmp_path/'s.db','ATT-2'); lm2=LockManager(s2,tmp_path,{'api':(8000,8000)})
    with pytest.raises(ResourceUnavailable): lm2.acquire_assignment('ATT-2',1,ResourceRequest(paths=['other/**'],migration_count=1,ports={'api':1}))
    assert lm2.migration_slots_for('ATT-2')==[] and lm2.ports_for('ATT-2')==[] and lm2.active_locks_for('ATT-2')==[]
    s.close(); s2.close()


def test_stale_generation_cannot_renew_lock(tmp_path: Path) -> None:
    s=store_with_attempt(tmp_path/'s.db'); lm=LockManager(s,tmp_path,{'api':(8000,8002)})
    lm.acquire_assignment('ATT-1',1,ResourceRequest(paths=['src/**']))
    with pytest.raises(StaleGenerationError): lm.renew_attempt_leases('ATT-1',0)
    s.close()


def test_migration_slots_are_unique_across_connections(tmp_path: Path) -> None:
    db=tmp_path/'s.db'
    aids=[f'ATT-{i}' for i in range(100)]
    base=StateStore.open(db); base.initialize(); base.create_run('RUN-1',RunState.RUNNING); base.close()
    for aid in aids:
        s=StateStore.open(db); a=TaskAttempt(run_id='RUN-1',task_id=aid,attempt_id=aid,attempt_number=1,generation=1,branch=f'orch/{aid}',worktree_path=aid,base_sha='a'*40,task_spec_sha256='b'*64,state=TaskState.READY,version=0); s.create_task_attempt(a); s.close()
    def reserve(aid: str) -> int:
        s=StateStore.open(db); lm=LockManager(s,tmp_path,{'api':(8100,8125)}); lm.acquire_assignment(aid,1,ResourceRequest(migration_count=1)); slot=lm.migration_slots_for(aid)[0]; s.close(); return slot
    with ThreadPoolExecutor(max_workers=8) as ex: slots=list(ex.map(reserve,aids))
    assert len(slots)==len(set(slots))==100


def test_expired_port_reallocation_does_not_conflict(tmp_path: Path) -> None:
    s=store_with_attempt(tmp_path/'s.db'); lm=LockManager(s,tmp_path,{'api':(8000,8000)})
    lm.acquire_assignment('ATT-1',1,ResourceRequest(paths=['src/**'],lease_seconds=10,ports={'api':1}))
    assert lm.ports_for('ATT-1')==[8000]
    s._conn.execute('UPDATE port_allocations SET expires_at=1 WHERE attempt_id=?',('ATT-1',))
    s2=store_with_attempt(tmp_path/'s.db','ATT-2'); lm2=LockManager(s2,tmp_path,{'api':(8000,8000)})
    lm2.acquire_assignment('ATT-2',1,ResourceRequest(paths=['other/**'],lease_seconds=120,ports={'api':1}))
    assert lm2.ports_for('ATT-2')==[8000]
    s.close(); s2.close()
