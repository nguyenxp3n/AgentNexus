from __future__ import annotations
from pathlib import Path
import typer
from orch.core.git import GitRepository
from orch.core.state import StateStore

def init_command(repo:Path=typer.Option(Path('.'),'--repo'),force:bool=typer.Option(False,'--force')):
    repo=repo.resolve();GitRepository(repo);meta=repo/'.orch';meta.mkdir(exist_ok=True)
    for d in ['logs','prompts','audits','runtime','recovery','github','artifacts','snapshots']:(meta/d).mkdir(exist_ok=True)
    cfg=meta/'config.yaml'
    if force or not cfg.exists():cfg.write_text('# AgentNexus configuration; omitted values use strict defaults\n{}\n',encoding='utf-8')
    s=StateStore.open(meta/'state.db');s.initialize();s.close()
    gi=repo/'.gitignore';text=gi.read_text(encoding='utf-8') if gi.exists() else ''
    additions=['.orch/','.worktrees/']
    missing=[x for x in additions if x not in text.splitlines()]
    if missing:gi.write_text(text+('' if text.endswith('\n') or not text else '\n')+''.join(x+'\n' for x in missing),encoding='utf-8')
    typer.echo(f'Initialized AgentNexus at {repo}')
