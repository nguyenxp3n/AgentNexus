from __future__ import annotations
from pathlib import Path
import typer
from rich.console import Console
from rich.table import Table
from orch.core.state import StateStore
from orch.cli.common import fail
lock_app=typer.Typer(no_args_is_help=True)
@lock_app.command('list')
def list_locks(repo:Path=typer.Option(Path('.'),'--repo'),expired:bool=False):
    try:
        s=StateStore.open(repo.resolve()/'.orch'/'state.db');s.initialize();rows=s._conn.execute('SELECT * FROM resource_locks ORDER BY resource_type,resource_key').fetchall();t=Table('Type','Resource','Task','Attempt','Mode');[t.add_row(r['resource_type'],r['resource_key'],r['task_id'],r['attempt_id'],r['mode']) for r in rows];Console().print(t);s.close()
    except Exception as e:fail(e,False,'lock.list')
