from __future__ import annotations
import typer
from orch import __version__
from .init_cmd import init_command
from .spawn_cmd import spawn_command
from .recover_cmd import recover_command
from .doctor_cmd import doctor_command
from .logs_cmd import logs_command
from .plan_cmd import plan_app
from .lock_cmd import lock_app
from .audit_cmd import audit_app
from .merge_cmd import merge_app
from .pr_cmd import pr_app
app=typer.Typer(name='nexus',help='AgentNexus: Autonomous Multi-Agent Orchestration Engine',no_args_is_help=True,rich_markup_mode='rich')
app.command('init')(init_command);app.command('spawn')(spawn_command);app.command('recover')(recover_command);app.command('doctor')(doctor_command);app.command('logs')(logs_command)
app.add_typer(plan_app,name='plan');app.add_typer(lock_app,name='lock');app.add_typer(audit_app,name='audit');app.add_typer(merge_app,name='merge');app.add_typer(pr_app,name='pr')
@app.command('version')
def version():typer.echo(__version__)
if __name__=='__main__':app()
