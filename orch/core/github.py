from __future__ import annotations
import json,shutil,subprocess,time
from pathlib import Path
from dataclasses import dataclass
from orch.models.merge import CIState
from orch.errors import GitHubError
@dataclass(frozen=True)
class CmdResult:returncode:int;stdout:str;stderr:str
class SubprocessRunner:
    def run(self,argv,cwd=None):
        p=subprocess.run(argv,cwd=cwd,text=True,capture_output=True,shell=False);return CmdResult(p.returncode,p.stdout,p.stderr)
class GitHubClient:
    def __init__(self,repo:Path,runner=None):self.repo=Path(repo).resolve();self.runner=runner or SubprocessRunner()
    def discover(self)->dict:
        gh=shutil.which('gh')
        if not gh:return {'available':False,'authenticated':False}
        v=self.runner.run([gh,'--version'],self.repo);a=self.runner.run([gh,'auth','status'],self.repo);return {'available':v.returncode==0,'authenticated':a.returncode==0,'version':v.stdout.splitlines()[0] if v.stdout else None}
    def repo_sha(self,ref:str)->str:
        p=subprocess.run(['git','rev-parse',ref],cwd=self.repo,text=True,capture_output=True)
        if p.returncode!=0:raise GitHubError(p.stderr.strip() or f'unknown ref {ref}')
        return p.stdout.strip()
    def push_candidate(self,branch:str,expected_sha:str,remote:str='origin'):
        actual=subprocess.run(['git','rev-parse',branch],cwd=self.repo,text=True,capture_output=True)
        if actual.returncode!=0 or actual.stdout.strip()!=expected_sha:raise GitHubError('candidate branch sha mismatch')
        r=self.runner.run(['git','push','-u',remote,branch],self.repo)
        if r.returncode!=0:raise GitHubError(r.stderr)
    def create_or_get_pr(self,*,branch:str,base:str,title:str,body:str)->dict:
        existing=self.runner.run(['gh','pr','list','--head',branch,'--base',base,'--json','number,url,headRefOid'],self.repo)
        if existing.returncode==0:
            try:
                items=json.loads(existing.stdout or '[]')
                if items:return items[0]
            except json.JSONDecodeError:pass
        r=self.runner.run(['gh','pr','create','--base',base,'--head',branch,'--title',title,'--body',body],self.repo)
        if r.returncode!=0:raise GitHubError(r.stderr)
        return {'url':r.stdout.strip()}
    def normalize_checks(self,checks:list[dict],*,expected_sha:str,required:set[str])->CIState:
        by={c.get('name'):c for c in checks if c.get('headSha')==expected_sha}
        if any(n not in by for n in required):return CIState.UNKNOWN
        states=[str(by[n].get('conclusion') or by[n].get('status') or '').lower() for n in required]
        if any(x in {'failure','failed','cancelled','timed_out'} for x in states):return CIState.FAIL
        if all(x in {'success','completed','pass'} for x in states):return CIState.PASS
        return CIState.RUNNING
    def required_ci_status(self,*,pr_number:int,expected_sha:str,required:set[str])->CIState:
        r=self.runner.run(['gh','pr','checks',str(pr_number),'--json','name,state,bucket,link'],self.repo)
        if r.returncode!=0:return CIState.UNKNOWN
        try:items=json.loads(r.stdout or '[]')
        except json.JSONDecodeError:return CIState.UNKNOWN
        checks=[]
        for x in items:checks.append({'name':x.get('name'),'headSha':expected_sha,'conclusion':'success' if str(x.get('bucket','')).lower()=='pass' else x.get('state','')})
        return self.normalize_checks(checks,expected_sha=expected_sha,required=required)
    def watch_ci(self,*,pr_number:int,expected_sha:str,required:set[str],timeout_seconds:int=3600,poll_seconds:float=2)->CIState:
        end=time.time()+timeout_seconds
        while time.time()<end:
            s=self.required_ci_status(pr_number=pr_number,expected_sha=expected_sha,required=required)
            if s in {CIState.PASS,CIState.FAIL}:return s
            time.sleep(poll_seconds)
        return CIState.TIMED_OUT
