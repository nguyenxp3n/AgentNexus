from __future__ import annotations
import hashlib,os,subprocess,time
from dataclasses import dataclass
from pathlib import Path
@dataclass(frozen=True)
class CommandEvidence:
    argv:list[str]; cwd:str; exit_code:int|None; stdout_path:Path; stderr_path:Path; stdout_sha256:str; stderr_sha256:str; duration_ms:int; timed_out:bool=False
class VerificationRunner:
    def __init__(self,evidence_root:Path):self.root=Path(evidence_root);self.root.mkdir(parents=True,exist_ok=True)
    @staticmethod
    def _hash(path:Path)->str:return hashlib.sha256(path.read_bytes()).hexdigest()
    def run(self,argv:list[str],*,cwd:Path,name:str='command',timeout_seconds:float|None=None,env:dict[str,str]|None=None)->CommandEvidence:
        out=self.root/f'{name}.stdout';err=self.root/f'{name}.stderr';start=time.monotonic();timed=False
        clean={k:v for k,v in os.environ.items() if k not in {'GITHUB_TOKEN','GH_TOKEN','AWS_SECRET_ACCESS_KEY','OPENAI_API_KEY','ANTHROPIC_API_KEY'}};clean.update(env or {})
        try:
            p=subprocess.run(argv,cwd=Path(cwd),text=True,capture_output=True,shell=False,timeout=timeout_seconds,env=clean);code=p.returncode;stdout=p.stdout;stderr=p.stderr
        except subprocess.TimeoutExpired as e:
            timed=True;code=None;stdout=(e.stdout.decode() if isinstance(e.stdout,bytes) else e.stdout) or '';stderr=(e.stderr.decode() if isinstance(e.stderr,bytes) else e.stderr) or ''
        out.write_text(stdout);err.write_text(stderr)
        return CommandEvidence(list(argv),str(Path(cwd).resolve()),code,out,err,self._hash(out),self._hash(err),int((time.monotonic()-start)*1000),timed)
