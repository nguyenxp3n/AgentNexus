from __future__ import annotations
import json
from pathlib import Path
import typer
from rich.console import Console
from rich.table import Table
from orch.config import load_config
from orch.core.dag import load_plan,DagPlan
from orch.core.locks import classify_path_overlap,Overlap
from orch.core.orchestrator import Orchestrator
from orch.core.state import StateStore
from orch.cli.common import emit_json,fail
from orch.errors import PlanError
plan_app=typer.Typer(no_args_is_help=True)

def _static_conflicts(repo:Path,dag:DagPlan)->list[str]:
    conflicts=[];tasks=list(dag.plan.tasks)
    for i,a in enumerate(tasks):
        for b in tasks[i+1:]:
            # Ordered dependencies are allowed to reuse paths sequentially.
            if dag.graph.has_edge(a.id,b.id) or dag.graph.has_edge(b.id,a.id):continue
            for pa in a.ownership.allowed_paths:
                for pb in b.ownership.allowed_paths:
                    if classify_path_overlap(repo,pa,pb) is not Overlap.PROVEN_DISJOINT:conflicts.append(f'{a.id}<->{b.id}:{pa}<->{pb}')
    return conflicts
@plan_app.command('validate')
def validate(file:Path,repo:Path=typer.Option(Path('.'),'--repo'),activate:bool=False,json_output:bool=typer.Option(False,'--json')):
    try:
        repo=repo.resolve();plan=load_plan(file);dag=DagPlan.from_plan(plan);result=dag.validate();conflicts=_static_conflicts(repo,dag) if result.ok else []
        cfg=load_config(repo);overs=[]
        for wi,wave in enumerate(dag.execution_waves()):
            for pool,(start,end) in cfg.ports.ranges.items():
                demand=sum(dag.tasks[t].resources.ports.get(pool,0) for t in wave);cap=end-start+1
                if demand>cap:overs.append(f'wave {wi} pool {pool}: demand {demand} > capacity {cap}')
        ok=result.ok and not conflicts and not overs
        if not ok:raise PlanError(json.dumps({'validation':result.model_dump(),'ownership_conflicts':conflicts,'port_oversubscription':overs}))
        rid=None
        if activate:
            o=Orchestrator.open(repo);rid=o.activate_plan(file);o.close()
        payload={'tasks':len(plan.tasks),'waves':dag.execution_waves(),'run_id':rid}
        if json_output:emit_json('plan.validate',True,**payload)
        else:typer.echo(f'Plan VALID: {len(plan.tasks)} tasks, {len(payload["waves"])} waves'+(f', run {rid}' if rid else ''))
    except Exception as e:fail(e,json_output,'plan.validate')
@plan_app.command('status')
def status(repo:Path=typer.Option(Path('.'),'--repo'),json_output:bool=typer.Option(False,'--json')):
    try:
        s=StateStore.open(repo.resolve()/'.orch'/'state.db');s.initialize();rid=s.latest_run_id();attempts=s.list_attempts(rid) if rid else []
        rows=[]
        for a in attempts:
            locks=s._conn.execute('SELECT COUNT(*) c FROM resource_locks WHERE attempt_id=?',(a.attempt_id,)).fetchone()['c'];rows.append({'task':a.task_id,'state':a.state.value,'attempt':a.attempt_id,'locks':locks})
        s.close()
        if json_output:emit_json('plan.status',True,run_id=rid,tasks=rows);return
        table=Table('Task','State','Attempt','Locks');[table.add_row(r['task'],r['state'],r['attempt'],str(r['locks'])) for r in rows];Console().print(table)
    except Exception as e:fail(e,json_output,'plan.status')
