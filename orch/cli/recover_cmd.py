from __future__ import annotations
from pathlib import Path
import typer
from orch.core.recovery import RecoveryController
from orch.core.state import StateStore
from orch.cli.common import fail
def recover_command(dangling:bool=typer.Option(False,'--dangling'),dry_run:bool=typer.Option(False,'--dry-run'),repo:Path=typer.Option(Path('.'),'--repo')):
    try:
        if not dangling:raise ValueError('--dangling is required')
        s=StateStore.open(repo.resolve()/'.orch/state.db');s.initialize();rc=RecoveryController(repo.resolve(),s);items=rc.scan();plan=rc.plan(items);typer.echo(f'found={len(items)} safe_mode={plan.enter_safe_mode}')
        if not dry_run:rc.apply(plan,s.latest_run_id());s.close()
    except Exception as e:fail(e,False,'recover')
