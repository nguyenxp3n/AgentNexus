from __future__ import annotations
from pathlib import Path
import typer
from orch.core.audit import AuditRunner
from orch.core.orchestrator import Orchestrator
from orch.models.audit import AuditDisposition
from orch.models.state import TaskState,TransitionActor
from orch.cli.common import emit_json,fail
audit_app=typer.Typer(no_args_is_help=True)
@audit_app.command('run')
def audit_run(task_id:str,repo:Path=typer.Option(Path('.'),'--repo'),attempt:str|None=typer.Option(None,'--attempt'),json_output:bool=typer.Option(False,'--json')):
    try:
        o=Orchestrator.open(repo.resolve());a=o.store.get_attempt(attempt) if attempt else o.current_attempt(task_id);task=o._task(a);report=AuditRunner(Path(a.worktree_path)).run(a,task);o.store.save_audit_report(report)
        if report.disposition is AuditDisposition.PASS:
            a=o.store.transition_task(a.attempt_id,expected_state=TaskState.AUDIT_READY,expected_version=a.version,to_state=TaskState.AUDITED,actor=TransitionActor.AUDITOR)
        else:
            a=o.store.transition_task(a.attempt_id,expected_state=TaskState.AUDIT_READY,expected_version=a.version,to_state=TaskState.REJECTED,actor=TransitionActor.AUDITOR);o.locks.release_all(a.attempt_id)
        o.close()
        if json_output:emit_json('audit.run',report.disposition is AuditDisposition.PASS,task_id=task_id,audit_id=report.audit_id,disposition=report.disposition.value,certificate_sha256=report.certificate_sha256)
        else:typer.echo(f'{task_id}: {report.disposition.value} certificate={report.certificate_sha256}')
        if report.disposition is not AuditDisposition.PASS:raise typer.Exit(20)
    except typer.Exit:raise
    except Exception as e:fail(e,json_output,'audit.run')
