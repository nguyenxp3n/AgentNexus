from __future__ import annotations
from pathlib import Path
import typer
from orch.core.state import StateStore
from orch.cli.common import fail
def logs_command(task_id:str,repo:Path=typer.Option(Path('.'),'--repo'),attempt:str|None=typer.Option(None,'--attempt'),stderr:bool=False,tail:int=200):
    try:
        repo=repo.resolve();s=StateStore.open(repo/'.orch/state.db');s.initialize();a=s.get_attempt(attempt) if attempt else s.current_attempt_for_task(s.latest_run_id(),task_id);s.close()
        if not a:raise KeyError(task_id)
        p=repo/'.orch/logs'/task_id/a.attempt_id/('stderr.log' if stderr else 'stdout.log');lines=p.read_text().splitlines() if p.exists() else [];typer.echo('\n'.join(lines[-tail:]))
    except Exception as e:fail(e,False,'logs')
