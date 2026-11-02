from __future__ import annotations
import asyncio,hashlib,json,uuid
from dataclasses import dataclass
from pathlib import Path
from orch.config import load_config
from orch.core.audit import task_spec_digest
from orch.core.dag import DagPlan,load_plan
from orch.core.environment import RuntimeEnvironmentBuilder
from orch.core.git import GitRepository
from orch.core.harness import GenericCLIAdapter,ClaudeCodeAdapter,GeminiCLIAdapter,AntigravityAdapter,AiderAdapter
from orch.core.locks import LockManager
from orch.core.process import ProcessSupervisor,ExecutionResult
from orch.core.state import StateStore
from orch.core.worktree import WorktreeManager
from orch.errors import HarnessError,SafeModeError,ResourceUnavailable
from orch.models.execution import TaskAttempt
from orch.models.lock import ResourceRequest
from orch.models.state import TaskState,TransitionActor,RunState
from orch.models.task import ProjectPlan,TaskSpec
@dataclass(frozen=True)
class SpawnResult:task_id:str;attempt_id:str;state:TaskState;process:ExecutionResult|None;worktree:Path|None
class Orchestrator:
    def __init__(self,repo:Path,store:StateStore):
        self.repo=Path(repo).resolve();self.config=load_config(self.repo);self.store=store;self.git=GitRepository(self.repo);self.locks=LockManager(store,self.repo,self.config.ports.ranges);self.worktrees=WorktreeManager(self.repo,self.repo/self.config.git.worktree_root,set(self.config.git.protected_branches));self.environment=RuntimeEnvironmentBuilder(self.repo);self.supervisor=ProcessSupervisor(self.repo);self._plans={}
    @classmethod
    def open(cls,repo_path:Path):
        repo=Path(repo_path).resolve();s=StateStore.open(repo/'.orch'/'state.db');s.initialize();return cls(repo,s)
    def close(self):self.store.close()
    def activate_plan(self,path:Path,run_id:str|None=None)->str:
        plan=load_plan(path);dag=DagPlan.from_plan(plan);v=dag.validate()
        if not v.ok:raise ValueError(v.model_dump())
        run_id=run_id or 'RUN-'+uuid.uuid4().hex[:12];self.store.create_run(run_id,RunState.RUNNING);base=self.git.head();self._plans[run_id]=plan
        roots={x for wave in dag.execution_waves()[:1] for x in wave}
        for t in plan.tasks:
            raw=json.dumps(t.model_dump(mode='json'),sort_keys=True,separators=(',',':'));digest=hashlib.sha256(raw.encode()).hexdigest();self.store.upsert_task(run_id,t.id,raw,digest)
            for d in t.dependencies:self.store.add_dependency(run_id,t.id,d)
            aid=f'ATT-{uuid.uuid4().hex[:12]}';a=TaskAttempt(run_id=run_id,task_id=t.id,attempt_id=aid,attempt_number=1,generation=1,branch=f'orch/{run_id}/{t.id}/{aid[-6:]}',worktree_path='',base_sha=base,task_spec_sha256=digest,state=TaskState.PENDING,version=0);self.store.create_task_attempt(a)
            if t.id in roots:self.store.transition_task(aid,expected_state=TaskState.PENDING,expected_version=0,to_state=TaskState.READY,actor=TransitionActor.SCHEDULER)
        return run_id
    def _task(self,a:TaskAttempt)->TaskSpec:
        r=self.store.task_spec_record(a.run_id,a.task_id)
        if not r:raise KeyError(a.task_id)
        return TaskSpec.model_validate_json(r['spec_json'])
    def current_attempt(self,task_id:str,run_id:str|None=None)->TaskAttempt:
        run_id=run_id or self.store.latest_run_id();a=self.store.current_attempt_for_task(run_id,task_id) if run_id else None
        if not a:raise KeyError(task_id)
        return a
    def compile_prompt(self,a:TaskAttempt,t:TaskSpec)->str:
        ports=[dict(r) for r in self.store._conn.execute('SELECT pool,port FROM port_allocations WHERE attempt_id=?',(a.attempt_id,)).fetchall()];slots=[r['slot'] for r in self.store._conn.execute('SELECT slot FROM migration_slots WHERE attempt_id=?',(a.attempt_id,)).fetchall()]
        return f'''SYSTEM ROLE\nYou are the {t.role.value} worker for {t.id}.\n\nCANONICAL IDENTITY\nRun: {a.run_id}\nTask: {a.task_id}\nAttempt: {a.attempt_id}\nGeneration: {a.generation}\n\nWORKSPACE\n{a.worktree_path}\nBASE COMMIT\n{a.base_sha}\nWRITE OWNERSHIP\n{json.dumps(t.ownership.allowed_paths)}\nREAD ONLY\n{json.dumps(t.ownership.readonly_paths)}\nFORBIDDEN\n{json.dumps(t.ownership.forbidden_paths)}\nALLOCATED RESOURCES\nports={json.dumps(ports)} migrations={json.dumps(slots)}\nACCEPTANCE\n{t.acceptance.model_dump_json()}\nAUTHORITY\nYou cannot mark this task AUDITED, MERGING, or COMPLETED. Commit all intended changes and leave the worktree clean.\n'''
    def _adapter(self,t:TaskSpec):
        name=t.harness.adapter if t.harness else self.config.harnesses.default
        if name and name in self.config.harnesses.definitions:
            d=self.config.harnesses.definitions[name];return GenericCLIAdapter(d.command,d.prompt_delivery)
        if name in {'claude','claude-code'}:return ClaudeCodeAdapter()
        if name in {'gemini','gemini-cli'}:return GeminiCLIAdapter()
        if name in {'antigravity','agy'}:return AntigravityAdapter()
        if name=='aider':return AiderAdapter()
        raise HarnessError('no harness configured for task')
    async def spawn_task(self,task_id:str,run_id:str|None=None)->SpawnResult:
        a=self.current_attempt(task_id,run_id);t=self._task(a)
        if self.store.get_run_state(a.run_id)==RunState.SAFE_MODE:raise SafeModeError('run in safe mode')
        if a.state is TaskState.PENDING:
            states={d:self.current_attempt(d,a.run_id).state for d in t.dependencies}
            if not all(s is TaskState.COMPLETED for s in states.values()):raise ResourceUnavailable('dependencies incomplete')
            a=self.store.transition_task(a.attempt_id,expected_state=a.state,expected_version=a.version,to_state=TaskState.READY,actor=TransitionActor.SCHEDULER)
        if a.state is TaskState.READY:
            self.locks.acquire_assignment(a.attempt_id,a.generation,ResourceRequest(paths=t.ownership.allowed_paths,migration_count=t.resources.migration_count,ports=t.resources.ports,lease_seconds=self.config.locks.default_lease_seconds));a=self.store.get_attempt(a.attempt_id)
        ws=self.worktrees.create(a);a=self.store.update_attempt_identity(a.attempt_id,worktree_path=str(ws.path),branch=ws.branch)
        self.store._conn.execute('INSERT OR REPLACE INTO worktrees(attempt_id,path,branch,base_sha,current_head_sha,status) VALUES(?,?,?,?,?,?)',(a.attempt_id,str(ws.path),ws.branch,a.base_sha,a.base_sha,'ACTIVE'))
        env=self.environment.build(a);adapter=self._adapter(t);caps=adapter.discover()
        if not caps.available:raise HarnessError('configured harness unavailable')
        prompt=self.compile_prompt(a,t);pdir=self.repo/'.orch'/'prompts'/t.id/a.attempt_id;pdir.mkdir(parents=True,exist_ok=True);(pdir/'system.txt').write_text(prompt,encoding='utf-8');ph=hashlib.sha256(prompt.encode()).hexdigest();(pdir/'manifest.json').write_text(json.dumps({'prompt_sha256':ph,'task_spec_sha256':a.task_spec_sha256,'adapter':adapter.name,'adapter_version':caps.version},indent=2),encoding='utf-8');a=self.store.update_attempt_identity(a.attempt_id,prompt_sha256=ph)
        prepared=adapter.prepare(prompt=prompt,cwd=ws.path,env=env.env)
        a=self.store.transition_task(a.attempt_id,expected_state=TaskState.ASSIGNED,expected_version=a.version,to_state=TaskState.SPAWNED,actor=TransitionActor.DISPATCHER)
        a=self.store.transition_task(a.attempt_id,expected_state=TaskState.SPAWNED,expected_version=a.version,to_state=TaskState.IN_PROGRESS,actor=TransitionActor.RUNTIME_MONITOR)
        def record_process(ident):
            self.store._conn.execute('INSERT OR REPLACE INTO agent_processes(attempt_id,pid,spawned_at,command_fingerprint,host_id,generation,status) VALUES(?,?,?,?,?,?,?)',(a.attempt_id,ident.pid,str(ident.spawned_at),ident.command_fingerprint,ident.host_id,a.generation,'RUNNING'))
        proc_task=asyncio.create_task(self.supervisor.spawn_and_wait(task_id=t.id,attempt_id=a.attempt_id,argv=prepared.argv,cwd=prepared.cwd,env=prepared.env,stdin_text=prepared.stdin_text,timeout_seconds=t.timeout_seconds,on_spawn=record_process))
        async def heartbeat():
            interval=max(0.5,self.config.locks.default_lease_seconds/3)
            while not proc_task.done():
                await asyncio.sleep(interval)
                if not proc_task.done():self.locks.renew_attempt_leases(a.attempt_id,a.generation,self.config.locks.default_lease_seconds)
        hb=asyncio.create_task(heartbeat())
        try:process=await proc_task
        finally:
            hb.cancel()
            try:await hb
            except asyncio.CancelledError:pass
        self.store._conn.execute('UPDATE agent_processes SET status=? WHERE attempt_id=?',('EXITED',a.attempt_id))
        return self.finalize_worker_result(a.attempt_id,process,t)
    def finalize_worker_result(self,attempt_id:str,process:ExecutionResult,t:TaskSpec)->SpawnResult:
        a=self.store.get_attempt(attempt_id)
        if a.state is not TaskState.IN_PROGRESS:return SpawnResult(a.task_id,a.attempt_id,a.state,process,Path(a.worktree_path) if a.worktree_path else None)
        ins=self.worktrees.inspect(Path(a.worktree_path));valid=process.exit_code==0 and not process.timed_out and not ins.dirty and (ins.head_sha!=a.base_sha or t.allow_noop)
        if valid:
            a=self.store.update_attempt_identity(a.attempt_id,head_sha=ins.head_sha);self.store._conn.execute('UPDATE worktrees SET current_head_sha=?,status=? WHERE attempt_id=?',(ins.head_sha,'AUDIT_FROZEN',a.attempt_id));a=self.store.transition_task(a.attempt_id,expected_state=TaskState.IN_PROGRESS,expected_version=a.version,to_state=TaskState.AUDIT_READY,actor=TransitionActor.RUNTIME_MONITOR)
        else:a=self.store.transition_task(a.attempt_id,expected_state=TaskState.IN_PROGRESS,expected_version=a.version,to_state=TaskState.RECOVERING,actor=TransitionActor.RECOVERY)
        return SpawnResult(a.task_id,a.attempt_id,a.state,process,Path(a.worktree_path) if a.worktree_path else None)
    async def spawn_wave(self,wave_id:int,run_id:str|None=None)->list[SpawnResult]:
        run_id=run_id or self.store.latest_run_id()
        if not run_id:raise ValueError('no active run_id available')
        records=self.store.list_task_records(run_id);plan=ProjectPlan.model_validate({'version':1,'project':{'name':'active'},'tasks':[json.loads(r['spec_json']) for r in records]});waves=DagPlan.from_plan(plan).execution_waves();ids=waves[wave_id];sem=asyncio.Semaphore(self.config.scheduler.max_parallel_agents)
        async def one(tid):
            async with sem:return await self.spawn_task(tid,run_id)
        return await asyncio.gather(*(one(x) for x in ids))
