from __future__ import annotations
import json,os,subprocess,uuid
from dataclasses import dataclass,field
from enum import StrEnum
from pathlib import Path
from typing import Any
from orch.core.git import GitRepository
from orch.models.state import TaskState,TransitionActor
class RecoveryKind(StrEnum): DANGLING_PROCESS='DANGLING_PROCESS'; ORPHAN_WORKTREE='ORPHAN_WORKTREE'; EXPIRED_LOCK='EXPIRED_LOCK'; STALE_ATTEMPT='STALE_ATTEMPT'; INTERRUPTED_MERGE='INTERRUPTED_MERGE'; DIRTY_RECOVERY_WORKTREE='DIRTY_RECOVERY_WORKTREE'; DB_GIT_DIVERGENCE='DB_GIT_DIVERGENCE'; REMOTE_STATE_DRIFT='REMOTE_STATE_DRIFT'; UNKNOWN='UNKNOWN'
@dataclass(frozen=True)
class RecoveryPlan:
    enter_safe_mode:bool=False; destructive_actions:list[dict]=field(default_factory=list); safe_actions:list[dict]=field(default_factory=list)
@dataclass(frozen=True)
class RecoveryBundle:path:Path;metadata_path:Path
class RecoveryController:
    def __init__(self,repo:Path,store):self.repo=Path(repo).resolve();self.store=store
    def scan(self)->list[dict]:
        out=[]
        if self.store is None:return out
        for m in self.store._conn.execute("SELECT * FROM merge_attempts WHERE status IN ('PREPARED','GIT_SUCCEEDED')").fetchall():
            out.append({'kind':RecoveryKind.INTERRUPTED_MERGE,'merge_id':m['merge_id'],'attempt_id':m['attempt_id'],'detail':m['status']})
        for a in self.store.list_attempts():
            if a.state in {TaskState.SPAWNED,TaskState.IN_PROGRESS}:
                row=self.store._conn.execute('SELECT * FROM agent_processes WHERE attempt_id=?',(a.attempt_id,)).fetchone()
                if row and row['pid'] and not Path(f'/proc/{row["pid"]}').exists():out.append({'kind':RecoveryKind.DANGLING_PROCESS,'attempt_id':a.attempt_id,'detail':'recorded process is gone'})
        return out
    def plan(self,items:list[dict])->RecoveryPlan:
        unknown=any((i.get('kind')==RecoveryKind.UNKNOWN or str(i.get('kind'))==RecoveryKind.UNKNOWN.value) for i in items)
        safe=[]
        for i in items:
            if i.get('kind') in {RecoveryKind.DANGLING_PROCESS,RecoveryKind.EXPIRED_LOCK,RecoveryKind.STALE_ATTEMPT,RecoveryKind.INTERRUPTED_MERGE}:safe.append(i)
        return RecoveryPlan(enter_safe_mode=unknown,safe_actions=safe,destructive_actions=[])
    def create_bundle(self,attempt_id:str)->RecoveryBundle:
        root=self.repo/'.orch'/'recovery'/attempt_id/uuid.uuid4().hex[:8];root.mkdir(parents=True,exist_ok=True);meta=root/'metadata.json';meta.write_text(json.dumps({'attempt_id':attempt_id},indent=2));return RecoveryBundle(root,meta)
    def apply(self,plan:RecoveryPlan,run_id:str|None=None)->dict:
        applied=[]
        if plan.enter_safe_mode and self.store and run_id:self.store.enter_safe_mode(run_id,'recovery encountered unknown physical state')
        for item in plan.safe_actions:
            if item.get('kind')==RecoveryKind.INTERRUPTED_MERGE:
                mid=item.get('merge_id');row=self.store._conn.execute('SELECT * FROM merge_attempts WHERE merge_id=?',(mid,)).fetchone()
                if row:
                    try:
                        head=GitRepository(self.repo).head();parents=GitRepository(self.repo).parents(head)
                        proven=(row['status']=='GIT_SUCCEEDED' and head==row['integration_after_sha']) or (row['status']=='PREPARED' and len(parents)>=2 and parents[0]==row['integration_before_sha'] and parents[1]==row['candidate_head_sha'])
                    except Exception:proven=False
                    if proven:self.store._conn.execute('UPDATE merge_attempts SET merge_commit_sha=?,integration_after_sha=?,status=? WHERE merge_id=?',(head,head,'RECONCILED',mid));applied.append(mid)
                    elif run_id:self.store.enter_safe_mode(run_id,'interrupted merge cannot be proven from Git parents')
                continue
            aid=item.get('attempt_id')
            if aid and self.store:
                self.create_bundle(aid);a=self.store.get_attempt(aid)
                if a.state in {TaskState.SPAWNED,TaskState.IN_PROGRESS,TaskState.ASSIGNED,TaskState.MERGING}:
                    try:self.store.transition_task(aid,expected_state=a.state,expected_version=a.version,to_state=TaskState.RECOVERING,actor=TransitionActor.RECOVERY)
                    except Exception:pass
                self.store._conn.execute('DELETE FROM port_allocations WHERE attempt_id=?',(aid,));applied.append(aid)
        return {'applied':applied,'safe_mode':plan.enter_safe_mode}
    def recover_dangling(self,run_id:str|None=None):
        items=self.scan();return self.apply(self.plan(items),run_id)
