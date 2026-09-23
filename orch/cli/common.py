from __future__ import annotations
import json,typer
from orch.errors import OrchError,ExitCode
def emit_json(command:str,success:bool,**payload):typer.echo(json.dumps({'schema_version':'1','command':command,'success':success,**payload},sort_keys=True,default=str))
def fail(exc:Exception,json_output:bool=False,command:str='orch'):
    code=int(exc.exit_code) if isinstance(exc,OrchError) else int(ExitCode.INTERNAL_ERROR)
    if json_output:emit_json(command,False,error=type(exc).__name__,message=str(exc),exit_code=code)
    else:typer.echo(f'ERROR {type(exc).__name__}: {exc}',err=True)
    raise typer.Exit(code)
