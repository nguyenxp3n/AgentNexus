from __future__ import annotations
import fnmatch,time
from enum import StrEnum
from pathlib import Path,PurePosixPath
from orch.core.state import StateStore
from orch.errors import PathOwnershipError,ResourceUnavailable,StaleGenerationError,StateVersionConflict
from orch.models.lock import ResourceRequest,LockMode
from orch.models.state import TaskState,TransitionActor

class Overlap(StrEnum): PROVEN_DISJOINT='PROVEN_DISJOINT'; PROVEN_OVERLAP='PROVEN_OVERLAP'; AMBIGUOUS='AMBIGUOUS'
_WILD=set('*?[')
def _literal_prefix(pattern:str)->str:
    parts=[]
    for part in pattern.replace('\\','/').split('/'):
        if any(c in part for c in _WILD):break
        if part and part!='.':parts.append(part)
    return '/'.join(parts)
def normalize_repo_path(repo:Path,value:str)->str:
    repo=Path(repo).resolve(); raw=value.replace('\\','/')
    if raw.startswith('/') or raw.startswith('~'):raise PathOwnershipError('absolute path not allowed')
    parts=[]
    for p in raw.split('/'):
        if p in ('','.'):continue
        if p=='..':
            if not parts:raise PathOwnershipError('path escapes repository')
            parts.pop();continue
        parts.append(p)
    norm='/'.join(parts)
    prefix=_literal_prefix(norm)
    probe=repo
    for part in prefix.split('/') if prefix else []:
        probe=probe/part
        if probe.exists() or probe.is_symlink():
            resolved=probe.resolve()
            if resolved!=repo and repo not in resolved.parents:raise PathOwnershipError('symlink escapes repository')
    return norm
def _simple_tree(pattern:str)->str|None:
    p=pattern.rstrip('/')
    if p.endswith('/**') and not any(c in p[:-3] for c in '?[') and '*' not in p[:-3]:return p[:-3].strip('/')
    if not any(c in p for c in '*?['):return p.strip('/')
    return None
def classify_path_overlap(repo:Path,a:str,b:str)->Overlap:
    a=normalize_repo_path(repo,a); b=normalize_repo_path(repo,b)
    sa,sb=_simple_tree(a),_simple_tree(b)
    if sa is not None and sb is not None:
        if sa==sb or sa.startswith(sb+'/') or sb.startswith(sa+'/'):return Overlap.PROVEN_OVERLAP
        if sa.split('/',1)[0]!=sb.split('/',1)[0]:return Overlap.PROVEN_DISJOINT
        return Overlap.PROVEN_DISJOINT
    pa,pb=_literal_prefix(a),_literal_prefix(b)
    if pa and pb and pa.split('/',1)[0]!=pb.split('/',1)[0]:return Overlap.PROVEN_DISJOINT
    # If current inventory proves an overlap, report it; absence does not prove future paths are safe.
    for path in Path(repo).rglob('*'):
        if not path.is_file():continue
        rel=path.resolve().relative_to(Path(repo).resolve()).as_posix()
        if fnmatch.fnmatch(rel,a) and fnmatch.fnmatch(rel,b):return Overlap.PROVEN_OVERLAP
    return Overlap.AMBIGUOUS

class LockManager:
    def __init__(self,store:StateStore,repo_root:Path,port_pools:dict[str,tuple[int,int]]|None=None):self.store=store;self.repo_root=Path(repo_root).resolve();self.port_pools=port_pools or {}
    def _active_path_rows(self,c):return c.execute("SELECT * FROM resource_locks WHERE resource_type='PATH' AND (expires_at IS NULL OR expires_at>?)",(time.time(),)).fetchall()
    def acquire_assignment(self,attempt_id:str,generation:int,request:ResourceRequest)->None:
        with self.store.transaction(immediate=True) as c:
            a=c.execute('SELECT * FROM task_attempts WHERE attempt_id=?',(attempt_id,)).fetchone()
            if not a:raise KeyError(attempt_id)
            if a['generation']!=generation:raise StaleGenerationError(attempt_id)
            if a['state']!=TaskState.READY.value:raise ResourceUnavailable(f'attempt not READY: {a["state"]}')
            now=time.time(); expiry=now+request.lease_seconds
            existing=self._active_path_rows(c)
            for p in sorted(request.paths):
                p=normalize_repo_path(self.repo_root,p)
                for row in existing:
                    if row['attempt_id']==attempt_id:continue
                    overlap=classify_path_overlap(self.repo_root,p,row['resource_key'])
                    if overlap is not Overlap.PROVEN_DISJOINT:raise ResourceUnavailable(f'path conflict: {p} vs {row["resource_key"]}')
                c.execute('INSERT INTO resource_locks(resource_type,resource_key,run_id,task_id,attempt_id,generation,mode,expires_at) VALUES(?,?,?,?,?,?,?,?)',('PATH',p,a['run_id'],a['task_id'],attempt_id,generation,LockMode.EXCLUSIVE_WRITE.value,expiry))
            # Migration slots are monotonic and never reused.
            if request.migration_count:
                r=c.execute("SELECT next_slot FROM migration_allocators WHERE name='default'").fetchone()
                next_slot=int(r['next_slot']) if r else 1
                if not r:c.execute("INSERT INTO migration_allocators(name,next_slot) VALUES('default',?)",(next_slot,))
                for slot in range(next_slot,next_slot+request.migration_count):c.execute('INSERT INTO migration_slots(slot,attempt_id,run_id) VALUES(?,?,?)',(slot,attempt_id,a['run_id']))
                c.execute("UPDATE migration_allocators SET next_slot=? WHERE name='default'",(next_slot+request.migration_count,))
            for pool,count in sorted(request.ports.items()):
                if pool not in self.port_pools:raise ResourceUnavailable(f'unknown port pool: {pool}')
                start,end=self.port_pools[pool];used={r['port'] for r in c.execute('SELECT port FROM port_allocations WHERE pool=? AND (expires_at IS NULL OR expires_at>?)',(pool,now)).fetchall()};free=[p for p in range(start,end+1) if p not in used]
                if len(free)<count:raise ResourceUnavailable(f'port pool exhausted: {pool}')
                for port in free[:count]:c.execute('INSERT INTO port_allocations(pool,port,attempt_id,run_id,expires_at) VALUES(?,?,?,?,?)',(pool,port,attempt_id,a['run_id'],expiry))
            changed=c.execute('UPDATE task_attempts SET state=?,version=version+1 WHERE attempt_id=? AND state=? AND generation=?',(TaskState.ASSIGNED.value,attempt_id,TaskState.READY.value,generation))
            if changed.rowcount!=1:raise StateVersionConflict(attempt_id)
            self.store.append_event(a['run_id'],'ASSIGNMENT_ACQUIRED',{'paths':request.paths,'migration_count':request.migration_count,'ports':request.ports},task_id=a['task_id'],attempt_id=attempt_id,actor=TransitionActor.ORCHESTRATOR.value,conn=c)
    def active_locks_for(self,attempt_id:str):return [dict(r) for r in self.store._conn.execute('SELECT * FROM resource_locks WHERE attempt_id=?',(attempt_id,)).fetchall()]
    def migration_slots_for(self,attempt_id:str)->list[int]:return [int(r['slot']) for r in self.store._conn.execute('SELECT slot FROM migration_slots WHERE attempt_id=? ORDER BY slot',(attempt_id,)).fetchall()]
    def ports_for(self,attempt_id:str)->list[int]:return [int(r['port']) for r in self.store._conn.execute('SELECT port FROM port_allocations WHERE attempt_id=? ORDER BY port',(attempt_id,)).fetchall()]
    def renew_attempt_leases(self,attempt_id:str,generation:int,lease_seconds:int=120):
        a=self.store.get_attempt(attempt_id)
        if a.generation!=generation:raise StaleGenerationError(attempt_id)
        exp=time.time()+lease_seconds
        with self.store.transaction(immediate=True) as c:
            c.execute('UPDATE resource_locks SET expires_at=? WHERE attempt_id=? AND generation=?',(exp,attempt_id,generation));c.execute('UPDATE port_allocations SET expires_at=? WHERE attempt_id=?',(exp,attempt_id))
    def release_ephemeral_resources(self,attempt_id:str,*,process_proven_gone:bool):
        if not process_proven_gone:raise ResourceUnavailable('process liveness not proven')
        with self.store.transaction(immediate=True) as c:c.execute('DELETE FROM port_allocations WHERE attempt_id=?',(attempt_id,))
    def release_all(self,attempt_id:str):
        with self.store.transaction(immediate=True) as c:c.execute('DELETE FROM port_allocations WHERE attempt_id=?',(attempt_id,));c.execute('DELETE FROM resource_locks WHERE attempt_id=?',(attempt_id,))
