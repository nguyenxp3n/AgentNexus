from __future__ import annotations
from pathlib import Path
import typer
from orch.core.merger import MergeController
from orch.core.integration import IntegrationManager
from orch.config import load_config
from orch.core.locks import LockManager
from orch.core.state import StateStore
from orch.models.state import TaskState,TransitionActor
from orch.cli.common import fail
merge_app=typer.Typer(no_args_is_help=True)
@merge_app.command('sequential')
def sequential(repo:Path=typer.Option(Path('.'),'--repo'),dry_run:bool=typer.Option(False,'--dry-run'),run_id:str|None=typer.Option(None,'--run')):
    try:
        repo=repo.resolve();s=StateStore.open(repo/'.orch'/'state.db');s.initialize();rid=run_id or s.latest_run_id();items=[]
        for a in s.list_attempts(rid):
            if a.state is TaskState.AUDITED:
                r=s.audit_report_for_attempt(a.attempt_id)
                if r:items.append((a,r))
        cfg=load_config(repo);merge_repo=repo
        if cfg.git.integration_mode=='staging_branch' and rid:
            merge_repo=IntegrationManager(repo,repo/cfg.git.worktree_root).ensure(rid,cfg.git.integration_branch).path
        m=MergeController(merge_repo,store=s)
        if dry_run:typer.echo(m.dry_run(items,m.git.head()));s.close();return
        results=[]
        for a,r in items:
            a=s.transition_task(a.attempt_id,expected_state=TaskState.AUDITED,expected_version=a.version,to_state=TaskState.MERGING,actor=TransitionActor.MERGER)
            res=m.merge_one(a,r,expected_integration_sha=m.git.head());results.append(res);a=s.get_attempt(a.attempt_id);s.transition_task(a.attempt_id,expected_state=TaskState.MERGING,expected_version=a.version,to_state=TaskState.COMPLETED,actor=TransitionActor.MERGER);LockManager(s,repo,cfg.ports.ranges).release_all(a.attempt_id)
        typer.echo(f'Merged {len(results)} task(s)');s.close()
    except Exception as e:fail(e,False,'merge.sequential')
