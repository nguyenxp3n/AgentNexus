from __future__ import annotations
import asyncio
from pathlib import Path
import typer
from orch.core.orchestrator import Orchestrator
from orch.cli.common import fail
def spawn_command(task:str|None=typer.Option(None,'--task'),wave:int|None=typer.Option(None,'--wave'),run_id:str|None=typer.Option(None,'--run'),repo:Path=typer.Option(Path('.'),'--repo')):
    try:
        if (task is None)==(wave is None):raise ValueError('choose exactly one of --task or --wave')
        o=Orchestrator.open(repo.resolve())
        result=asyncio.run(o.spawn_task(task,run_id)) if task is not None else asyncio.run(o.spawn_wave(wave,run_id));o.close();typer.echo(result)
    except Exception as e:fail(e,False,'spawn')
