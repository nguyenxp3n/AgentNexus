from __future__ import annotations
import json,sqlite3,threading,weakref
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime,timezone
from pathlib import Path
from typing import Iterator,Any
from orch.errors import StateVersionConflict,StateTransitionError
from orch.models.execution import TaskAttempt
from orch.models.state import TaskState,TransitionActor,RunState,validate_task_transition

@dataclass(frozen=True)
class StoredEvent:
    event_id:int; run_id:str; task_id:str|None; attempt_id:str|None; event_type:str; actor:str|None; payload:dict[str,Any]; created_at:str

_SCHEMA='''
CREATE TABLE IF NOT EXISTS schema_meta(version INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS runs(run_id TEXT PRIMARY KEY,state TEXT NOT NULL,safe_mode_reason TEXT,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS tasks(run_id TEXT NOT NULL,task_id TEXT NOT NULL,spec_json TEXT NOT NULL,spec_sha256 TEXT NOT NULL,PRIMARY KEY(run_id,task_id));
CREATE TABLE IF NOT EXISTS task_attempts(attempt_id TEXT PRIMARY KEY,run_id TEXT NOT NULL,task_id TEXT NOT NULL,attempt_number INTEGER NOT NULL,generation INTEGER NOT NULL,branch TEXT NOT NULL,worktree_path TEXT NOT NULL,base_sha TEXT NOT NULL,head_sha TEXT,task_spec_sha256 TEXT NOT NULL,prompt_sha256 TEXT,state TEXT NOT NULL,version INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS task_dependencies(run_id TEXT NOT NULL,task_id TEXT NOT NULL,depends_on TEXT NOT NULL,PRIMARY KEY(run_id,task_id,depends_on));
CREATE TABLE IF NOT EXISTS resource_locks(lock_id INTEGER PRIMARY KEY AUTOINCREMENT,resource_type TEXT NOT NULL,resource_key TEXT NOT NULL,run_id TEXT NOT NULL,task_id TEXT NOT NULL,attempt_id TEXT NOT NULL,generation INTEGER NOT NULL,mode TEXT NOT NULL,expires_at REAL,UNIQUE(resource_type,resource_key,attempt_id));
CREATE TABLE IF NOT EXISTS migration_allocators(name TEXT PRIMARY KEY,next_slot INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS migration_slots(slot INTEGER PRIMARY KEY,attempt_id TEXT NOT NULL UNIQUE,run_id TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS port_allocations(pool TEXT NOT NULL,port INTEGER NOT NULL,attempt_id TEXT NOT NULL,run_id TEXT NOT NULL,expires_at REAL,PRIMARY KEY(pool,port));
CREATE TABLE IF NOT EXISTS worktrees(worktree_id INTEGER PRIMARY KEY AUTOINCREMENT,attempt_id TEXT NOT NULL UNIQUE,path TEXT NOT NULL,branch TEXT NOT NULL,base_sha TEXT NOT NULL,current_head_sha TEXT,status TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS audit_reports(audit_id TEXT PRIMARY KEY,attempt_id TEXT NOT NULL,head_sha TEXT NOT NULL,certificate_sha256 TEXT NOT NULL,report_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS merge_queue(queue_id INTEGER PRIMARY KEY AUTOINCREMENT,attempt_id TEXT NOT NULL UNIQUE,status TEXT NOT NULL DEFAULT 'QUEUED',enqueued_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS merge_attempts(merge_id TEXT PRIMARY KEY,attempt_id TEXT NOT NULL,integration_before_sha TEXT,candidate_head_sha TEXT,merge_commit_sha TEXT,integration_after_sha TEXT,status TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS github_prs(attempt_id TEXT PRIMARY KEY,pr_number INTEGER,pr_url TEXT,head_sha TEXT);
CREATE TABLE IF NOT EXISTS ci_runs(run_key TEXT PRIMARY KEY,head_sha TEXT,state TEXT,payload_json TEXT);
CREATE TABLE IF NOT EXISTS agent_processes(attempt_id TEXT PRIMARY KEY,pid INTEGER,spawned_at TEXT,command_fingerprint TEXT,host_id TEXT,generation INTEGER,status TEXT);
CREATE TABLE IF NOT EXISTS events(event_id INTEGER PRIMARY KEY AUTOINCREMENT,run_id TEXT NOT NULL,task_id TEXT,attempt_id TEXT,event_type TEXT NOT NULL,actor TEXT,payload_json TEXT NOT NULL,created_at TEXT NOT NULL);
'''
class StateStore:
    def __init__(self,path:Path,conn:sqlite3.Connection):
        self.path=Path(path); self._conn=conn; self._lock=threading.RLock(); self._finalizer=weakref.finalize(self,conn.close)
    @classmethod
    def open(cls,path:Path):
        Path(path).parent.mkdir(parents=True,exist_ok=True); c=sqlite3.connect(path,timeout=5,isolation_level=None,check_same_thread=False); c.row_factory=sqlite3.Row; c.execute('PRAGMA foreign_keys=ON'); c.execute('PRAGMA busy_timeout=5000'); return cls(Path(path),c)
    def close(self):
        if self._finalizer.alive:self._finalizer()
    def __enter__(self)->StateStore:
        return self
    def __exit__(self,exc_type:Any,exc_val:Any,exc_tb:Any)->None:
        self.close()
    def initialize(self):
        with self._lock:
            self._conn.execute('PRAGMA journal_mode=WAL'); self._conn.execute('PRAGMA synchronous=FULL'); self._conn.executescript(_SCHEMA)
            row=self._conn.execute('SELECT version FROM schema_meta LIMIT 1').fetchone()
            if not row:self._conn.execute('INSERT INTO schema_meta(version) VALUES(1)')
    def scalar(self,sql:str):
        r=self._conn.execute(sql).fetchone();return r[0] if r else None
    def schema_version(self)->int:return int(self.scalar('SELECT version FROM schema_meta LIMIT 1'))
    @contextmanager
    def transaction(self,*,immediate:bool=False)->Iterator[sqlite3.Connection]:
        with self._lock:
            self._conn.execute('BEGIN IMMEDIATE' if immediate else 'BEGIN')
            try:
                yield self._conn
                self._conn.execute('COMMIT')
            except Exception:
                try:self._conn.execute('ROLLBACK')
                except sqlite3.OperationalError:pass
                raise
    def create_run(self,run_id:str,state:RunState=RunState.CREATED):
        self._conn.execute('INSERT INTO runs(run_id,state,created_at) VALUES(?,?,?)',(run_id,state.value,datetime.now(timezone.utc).isoformat()))
    def get_run_state(self,run_id:str)->RunState:
        r=self._conn.execute('SELECT state FROM runs WHERE run_id=?',(run_id,)).fetchone();return RunState(r['state'])
    def safe_mode_reason(self,run_id:str)->str:
        r=self._conn.execute('SELECT safe_mode_reason FROM runs WHERE run_id=?',(run_id,)).fetchone();return r['safe_mode_reason'] or ''
    def enter_safe_mode(self,run_id:str,reason:str):
        self._conn.execute('UPDATE runs SET state=?,safe_mode_reason=? WHERE run_id=?',(RunState.SAFE_MODE.value,reason,run_id));self.append_event(run_id,'SAFE_MODE_ENTERED',{'reason':reason})
    def upsert_task(self,run_id:str,task_id:str,spec_json:str,spec_sha256:str):
        self._conn.execute('INSERT INTO tasks VALUES(?,?,?,?) ON CONFLICT(run_id,task_id) DO UPDATE SET spec_json=excluded.spec_json,spec_sha256=excluded.spec_sha256',(run_id,task_id,spec_json,spec_sha256))
    def add_dependency(self,run_id:str,task_id:str,depends_on:str):self._conn.execute('INSERT OR IGNORE INTO task_dependencies VALUES(?,?,?)',(run_id,task_id,depends_on))
    def create_task_attempt(self,a:TaskAttempt):
        self._conn.execute('INSERT INTO task_attempts VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',(a.attempt_id,a.run_id,a.task_id,a.attempt_number,a.generation,a.branch,a.worktree_path,a.base_sha,a.head_sha,a.task_spec_sha256,a.prompt_sha256,a.state.value,a.version))
    def _attempt_from(self,r)->TaskAttempt:
        return TaskAttempt(run_id=r['run_id'],task_id=r['task_id'],attempt_id=r['attempt_id'],attempt_number=r['attempt_number'],generation=r['generation'],branch=r['branch'],worktree_path=r['worktree_path'],base_sha=r['base_sha'],head_sha=r['head_sha'],task_spec_sha256=r['task_spec_sha256'],prompt_sha256=r['prompt_sha256'],state=TaskState(r['state']),version=r['version'])
    def get_attempt(self,attempt_id:str)->TaskAttempt:
        r=self._conn.execute('SELECT * FROM task_attempts WHERE attempt_id=?',(attempt_id,)).fetchone()
        if not r:raise KeyError(attempt_id)
        return self._attempt_from(r)
    def current_attempt_for_task(self,run_id:str,task_id:str)->TaskAttempt|None:
        r=self._conn.execute('SELECT * FROM task_attempts WHERE run_id=? AND task_id=? ORDER BY attempt_number DESC LIMIT 1',(run_id,task_id)).fetchone();return self._attempt_from(r) if r else None
    def update_attempt_identity(self,attempt_id:str,**changes)->TaskAttempt:
        allowed={'head_sha','worktree_path','branch','prompt_sha256','base_sha'}; fields=[k for k in changes if k in allowed]
        if fields:self._conn.execute('UPDATE task_attempts SET '+','.join(f'{k}=?' for k in fields)+' WHERE attempt_id=?',tuple(changes[k] for k in fields)+(attempt_id,))
        return self.get_attempt(attempt_id)
    def append_event(self,run_id:str,event_type:str,payload:dict,*,task_id:str|None=None,attempt_id:str|None=None,actor:str|None=None,conn=None):
        c=conn or self._conn;c.execute('INSERT INTO events(run_id,task_id,attempt_id,event_type,actor,payload_json,created_at) VALUES(?,?,?,?,?,?,?)',(run_id,task_id,attempt_id,event_type,actor,json.dumps(payload,sort_keys=True),datetime.now(timezone.utc).isoformat()))
    def events_for_attempt(self,attempt_id:str)->list[StoredEvent]:
        rows=self._conn.execute('SELECT * FROM events WHERE attempt_id=? ORDER BY event_id',(attempt_id,)).fetchall();return [StoredEvent(r['event_id'],r['run_id'],r['task_id'],r['attempt_id'],r['event_type'],r['actor'],json.loads(r['payload_json']),r['created_at']) for r in rows]
    def transition_task(self,attempt_id:str,*,expected_state:TaskState,expected_version:int,to_state:TaskState,actor:TransitionActor)->TaskAttempt:
        if not validate_task_transition(expected_state,to_state,actor):raise StateTransitionError(f'illegal transition {expected_state}->{to_state} by {actor}')
        with self.transaction(immediate=True) as c:
            r=c.execute('SELECT * FROM task_attempts WHERE attempt_id=?',(attempt_id,)).fetchone()
            if not r or r['state']!=expected_state.value or r['version']!=expected_version:raise StateVersionConflict(attempt_id)
            changed=c.execute('UPDATE task_attempts SET state=?,version=version+1 WHERE attempt_id=? AND state=? AND version=?',(to_state.value,attempt_id,expected_state.value,expected_version))
            if changed.rowcount!=1:raise StateVersionConflict(attempt_id)
            self.append_event(r['run_id'],'TASK_STATE_CHANGED',{'from_state':expected_state.value,'to_state':to_state.value,'version':expected_version+1},task_id=r['task_id'],attempt_id=attempt_id,actor=actor.value,conn=c)
        return self.get_attempt(attempt_id)

    def task_spec_record(self,run_id:str,task_id:str):
        r=self._conn.execute('SELECT * FROM tasks WHERE run_id=? AND task_id=?',(run_id,task_id)).fetchone();return dict(r) if r else None
    def list_task_records(self,run_id:str):
        return [dict(r) for r in self._conn.execute('SELECT * FROM tasks WHERE run_id=? ORDER BY task_id',(run_id,)).fetchall()]
    def list_attempts(self,run_id:str|None=None):
        rows=self._conn.execute('SELECT * FROM task_attempts'+(' WHERE run_id=?' if run_id else '')+' ORDER BY task_id,attempt_number',((run_id,) if run_id else ())).fetchall();return [self._attempt_from(r) for r in rows]
    def latest_run_id(self)->str|None:
        r=self._conn.execute('SELECT run_id FROM runs ORDER BY created_at DESC LIMIT 1').fetchone();return r['run_id'] if r else None
    def set_run_state(self,run_id:str,state:RunState):
        self._conn.execute('UPDATE runs SET state=? WHERE run_id=?',(state.value,run_id));self.append_event(run_id,'RUN_STATE_CHANGED',{'to_state':state.value})
    def save_audit_report(self,report):
        self._conn.execute('INSERT OR REPLACE INTO audit_reports(audit_id,attempt_id,head_sha,certificate_sha256,report_json) VALUES(?,?,?,?,?)',(report.audit_id,report.attempt_id,report.head_sha,report.certificate_sha256,report.model_dump_json()))
    def audit_report_for_attempt(self,attempt_id:str):
        from orch.models.audit import AuditReport
        r=self._conn.execute('SELECT report_json FROM audit_reports WHERE attempt_id=? ORDER BY rowid DESC LIMIT 1',(attempt_id,)).fetchone();return AuditReport.model_validate_json(r['report_json']) if r else None
