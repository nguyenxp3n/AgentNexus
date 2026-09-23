from __future__ import annotations
import shutil,sqlite3,sys
from pathlib import Path
import typer
from rich.console import Console
from rich.table import Table
from orch.config import load_config
from orch.core.github import GitHubClient
from orch.core.harness.discovery import discover_executable
from orch.core.git import GitRepository
from orch.cli.common import fail
def doctor_command(repo:Path=typer.Option(Path('.'),'--repo')):
    try:
        repo=repo.resolve();checks=[];checks.append(('Python >=3.12',sys.version_info>=(3,12),sys.version.split()[0]));checks.append(('Git',bool(shutil.which('git')),shutil.which('git') or 'missing'));GitRepository(repo);cfg=load_config(repo)
        db=repo/'.orch/state.db';checks.append(('SQLite',True,sqlite3.sqlite_version));checks.append(('GitHub CLI',bool(shutil.which('gh')),'optional'))
        required=set()
        for r in cfg.harnesses.definitions.values():
            if r.command:required.add(r.command[0])
        for exe in sorted(required):checks.append((f'Harness {exe}',discover_executable(exe).available,'required'))
        t=Table('Check','Status','Detail');[t.add_row(n,'PASS' if ok else 'FAIL',d) for n,ok,d in checks];Console().print(t)
        if any(not ok and d=='required' for n,ok,d in checks):raise typer.Exit(51)
    except typer.Exit:raise
    except Exception as e:fail(e,False,'doctor')
