from __future__ import annotations
import asyncio,hashlib,json,os,socket,subprocess,time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from orch.core.observability import redact_text
@dataclass(frozen=True)
class ProcessIdentity:
    pid:int; spawned_at:float; command_fingerprint:str; host_id:str; os_start_token:str|None=None
@dataclass(frozen=True)
class ExecutionResult:
    exit_code:int; stdout_path:Path; stderr_path:Path; process_identity:ProcessIdentity; command_fingerprint:str; duration_seconds:float; timed_out:bool=False
class ProcessSupervisor:
    def __init__(self,repo_root:Path):self.repo=Path(repo_root).resolve()
    def _start_token(self,pid:int)->str|None:
        try:return Path(f'/proc/{pid}/stat').read_text().split()[21]
        except Exception:return None
    async def spawn_and_wait(self,*,task_id:str,attempt_id:str,argv:list[str],cwd:Path,env:dict[str,str],stdin_text:str|None=None,timeout_seconds:float|None=None,on_spawn:Callable[[ProcessIdentity],None]|None=None)->ExecutionResult:
        logdir=self.repo/'.orch'/'logs'/task_id/attempt_id;logdir.mkdir(parents=True,exist_ok=True);outp=logdir/'stdout.log';errp=logdir/'stderr.log';eventp=logdir/'events.jsonl'
        fingerprint=hashlib.sha256(json.dumps(argv,separators=(',',':')).encode()).hexdigest();start=time.time()
        proc=await asyncio.create_subprocess_exec(*argv,cwd=str(cwd),env={**os.environ,**env},stdin=asyncio.subprocess.PIPE if stdin_text is not None else None,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
        ident=ProcessIdentity(proc.pid,start,fingerprint,socket.gethostname(),self._start_token(proc.pid))
        if on_spawn:on_spawn(ident)
        event_lock=asyncio.Lock();seq={'n':0}
        async def pump(stream,path,label):
            with Path(path).open('w',encoding='utf-8',errors='replace') as f:
                while True:
                    raw=await stream.readline()
                    if not raw:break
                    text=redact_text(raw.decode(encoding='utf-8',errors='replace'));f.write(text);f.flush()
                    async with event_lock:
                        seq['n']+=1
                        trimmed=text.rstrip('\r\n')
                        if len(trimmed)>10000:trimmed=trimmed[:10000]+' [TRUNCATED]'
                        with eventp.open('a',encoding='utf-8') as ef:ef.write(json.dumps({'ts':time.time(),'stream':label,'seq':seq['n'],'text':trimmed})+'\n')
        out_task=asyncio.create_task(pump(proc.stdout,outp,'stdout'));err_task=asyncio.create_task(pump(proc.stderr,errp,'stderr'))
        if stdin_text is not None and proc.stdin is not None:
            proc.stdin.write(stdin_text.encode());await proc.stdin.drain();proc.stdin.close()
        timed=False
        try:
            if timeout_seconds is None:code=await proc.wait()
            else:code=await asyncio.wait_for(proc.wait(),timeout_seconds)
        except asyncio.TimeoutError:
            timed=True
            try:
                if os.name=='nt':
                    subprocess.run(['taskkill','/F','/T','/PID',str(proc.pid)],capture_output=True,check=False)
                proc.terminate()
            except (ProcessLookupError,OSError):pass
            try:await asyncio.wait_for(proc.wait(),2)
            except asyncio.TimeoutError:
                try:proc.kill()
                except (ProcessLookupError,OSError):pass
                await proc.wait()
            code=proc.returncode if proc.returncode is not None else -9
        await asyncio.gather(out_task,err_task)
        return ExecutionResult(int(code or 0),outp,errp,ident,fingerprint,time.time()-start,timed)
