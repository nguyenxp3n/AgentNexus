from __future__ import annotations
from pathlib import Path
import typer
from orch.config import load_config
from orch.core.github import GitHubClient
from orch.core.state import StateStore
from orch.cli.common import fail
pr_app=typer.Typer(no_args_is_help=True)
@pr_app.command('create-all')
def create_all(repo:Path=typer.Option(Path('.'),'--repo')):
    try:
        repo=repo.resolve();cfg=load_config(repo);gh=GitHubClient(repo);cap=gh.discover()
        if not cap.get('available') or not cap.get('authenticated'):raise RuntimeError('gh unavailable or unauthenticated')
        s=StateStore.open(repo/'.orch/state.db');s.initialize();rid=s.latest_run_id();created=[]
        if cfg.github.pr_strategy=='integration':
            branch=f'orch/integration/{rid}';sha=gh.repo_sha(branch);gh.push_candidate(branch,sha);created.append(gh.create_or_get_pr(branch=branch,base=cfg.git.integration_branch,title=f'orch integration {rid}',body=f'Run {rid} integration branch.'))
        else:
            for a in s.list_attempts(rid):
                r=s.audit_report_for_attempt(a.attempt_id)
                if r and r.disposition.value=='PASS':gh.push_candidate(a.branch,a.head_sha or '');created.append(gh.create_or_get_pr(branch=a.branch,base=cfg.git.integration_branch,title=f'{a.task_id}',body=f'Audit {r.audit_id}\nCertificate {r.certificate_sha256}\nHead {a.head_sha}'))
        s.close();typer.echo(f'PRs: {len(created)}')
    except Exception as e:fail(e,False,'pr.create-all')
@pr_app.command('watch-ci')
def watch_ci(repo:Path=typer.Option(Path('.'),'--repo'),pr_number:int=typer.Option(...,'--pr'),head_sha:str=typer.Option(...,'--sha')):
    try:
        cfg=load_config(repo.resolve());state=GitHubClient(repo.resolve()).watch_ci(pr_number=pr_number,expected_sha=head_sha,required=set(cfg.github.required_checks),timeout_seconds=cfg.github.ci_watch_timeout_seconds);typer.echo(state.value)
        if state.value!='pass':raise typer.Exit(71 if state.value!='timed_out' else 72)
    except typer.Exit:raise
    except Exception as e:fail(e,False,'pr.watch-ci')
