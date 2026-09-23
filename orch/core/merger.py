from __future__ import annotations
import contextlib,hashlib,json,os,uuid
from pathlib import Path
from typing import Callable
from orch.core.audit import certificate_payload,verify_certificate_digest
from orch.core.git import GitRepository
from orch.core.regression import VerificationRunner
from orch.errors import AuditCertificateStale,IntegrationBranchDrift,RegressionFailed,MergeError,ResourceUnavailable
from orch.models.audit import AuditDisposition,AuditReport
from orch.models.execution import TaskAttempt
from orch.models.merge import MergeResult,MergeDisposition
class MergeController:
    def __init__(self,repo:Path,regression_commands:list[list[str]]|None=None,store=None,fault_hook:Callable[[str],None]|None=None):
        self.repo=Path(repo).resolve();self.git=GitRepository(self.repo);self.regression_commands=regression_commands or [];self.store=store;self.fault_hook=fault_hook
    def _resolve(self,ref:str)->str:return self.git._out(['rev-parse',ref])
    def _validate(self,a:TaskAttempt,report:AuditReport,expected_integration_sha:str):
        if report.disposition is not AuditDisposition.PASS or report.head_sha!=a.head_sha or not verify_certificate_digest(certificate_payload(report),report.certificate_sha256):raise AuditCertificateStale('invalid audit certificate')
        manifest=[]
        for ev in report.evidence:
            p=Path(ev.path)
            if not p.exists() or hashlib.sha256(p.read_bytes()).hexdigest()!=ev.sha256:raise AuditCertificateStale('audit evidence changed or missing')
            manifest.append(ev.model_dump(mode='json'))
        actual_manifest=hashlib.sha256(json.dumps(sorted(manifest,key=lambda x:(x['kind'],x['path'])),sort_keys=True,separators=(',',':')).encode()).hexdigest()
        if actual_manifest!=report.evidence_manifest_sha256:raise AuditCertificateStale('evidence manifest drift')
        try:actual_candidate=self._resolve(a.branch)
        except Exception:actual_candidate=self._resolve(a.head_sha or '')
        if actual_candidate!=a.head_sha:raise AuditCertificateStale('candidate branch moved after audit')
        if self.git.head()!=expected_integration_sha:raise IntegrationBranchDrift('integration branch moved')
    def _journal(self,merge_id:str,a:TaskAttempt,before:str,status:str,merge_sha:str|None=None,after:str|None=None):
        if not self.store:return
        self.store._conn.execute('INSERT INTO merge_attempts(merge_id,attempt_id,integration_before_sha,candidate_head_sha,merge_commit_sha,integration_after_sha,status) VALUES(?,?,?,?,?,?,?) ON CONFLICT(merge_id) DO UPDATE SET merge_commit_sha=excluded.merge_commit_sha,integration_after_sha=excluded.integration_after_sha,status=excluded.status',(merge_id,a.attempt_id,before,a.head_sha,merge_sha,after,status))
        self.store.append_event(a.run_id,f'MERGE_{status}',{'merge_id':merge_id,'before':before,'candidate':a.head_sha,'merge_sha':merge_sha,'after':after},task_id=a.task_id,attempt_id=a.attempt_id,actor='merger')
    @contextlib.contextmanager
    def _integration_lock(self,a:TaskAttempt):
        if not self.store:yield;return
        key=f'INTEGRATION_BRANCH:{self.git.branch() or "detached"}';lock_attempt=f'MERGER:{os.getpid()}:{a.attempt_id}'
        with self.store.transaction(immediate=True) as c:
            row=c.execute("SELECT attempt_id FROM resource_locks WHERE resource_type='INTEGRATION' AND resource_key=?",(key,)).fetchone()
            if row:raise ResourceUnavailable(f'integration lock held by {row["attempt_id"]}')
            c.execute('INSERT INTO resource_locks(resource_type,resource_key,run_id,task_id,attempt_id,generation,mode,expires_at) VALUES(?,?,?,?,?,?,?,NULL)',('INTEGRATION',key,a.run_id,a.task_id,lock_attempt,a.generation,'integration_only'))
        try:yield
        finally:self.store._conn.execute("DELETE FROM resource_locks WHERE resource_type='INTEGRATION' AND resource_key=? AND attempt_id=?",(key,lock_attempt))
    def merge_one(self,a:TaskAttempt,report:AuditReport,*,expected_integration_sha:str)->MergeResult:
        self._validate(a,report,expected_integration_sha);before=self.git.head();merge_id='MRG-'+uuid.uuid4().hex[:12];self._journal(merge_id,a,before,'PREPARED')
        with self._integration_lock(a):
            p=self.git.runner.run(['merge','--no-ff',a.head_sha or a.branch,'-m',f'orch: integrate {a.task_id}\n\nRun: {a.run_id}\nTask: {a.task_id}\nAttempt: {a.attempt_id}\nAudit: {report.audit_id}\nCertificate-SHA256: {report.certificate_sha256}'],self.repo)
            if p.returncode!=0:
                self.git.runner.run(['merge','--abort'],self.repo);self.git.runner.run(['reset','--hard',before],self.repo);self._journal(merge_id,a,before,'CONFLICT');raise MergeError(p.stderr.strip() or 'merge conflict')
            merge_sha=self.git.head()
            if self.fault_hook:self.fault_hook('AFTER_GIT_MERGE')
            self._journal(merge_id,a,before,'GIT_SUCCEEDED',merge_sha,merge_sha)
            codes=[];vr=VerificationRunner(self.repo/'.orch'/'integration'/'regression')
            for i,cmd in enumerate(self.regression_commands):
                ev=vr.run(cmd,cwd=self.repo,name=f'regression-{i}');codes.append(ev.exit_code if ev.exit_code is not None else -1)
                if ev.exit_code!=0:
                    self.git.runner.run(['reset','--hard',before],self.repo,check=True);self.git.runner.run(['clean','-fd'],self.repo);self._journal(merge_id,a,before,'ROLLED_BACK',merge_sha,before);raise RegressionFailed(f'regression failed: {cmd}')
            self._journal(merge_id,a,before,'COMPLETED',merge_sha,self.git.head())
            return MergeResult(task_id=a.task_id,attempt_id=a.attempt_id,integration_before_sha=before,candidate_head_sha=a.head_sha or '',merge_commit_sha=merge_sha,integration_after_sha=self.git.head(),status=MergeDisposition.PASS,regression_exit_codes=codes)
    def dry_run(self,items:list[tuple[TaskAttempt,AuditReport]],expected_integration_sha:str)->list[str]:
        out=[]
        for a,r in items:self._validate(a,r,expected_integration_sha);out.append(a.task_id)
        return out
    def merge_sequential(self,items:list[tuple[TaskAttempt,AuditReport]])->list[MergeResult]:
        results=[]
        for a,r in items:results.append(self.merge_one(a,r,expected_integration_sha=self.git.head()))
        return results
    def verify_final_run(self,commands:list[list[str]],run_id:str|None=None)->bool:
        if self.store and run_id:self.store.set_run_state(run_id,__import__('orch.models.state',fromlist=['RunState']).RunState.VERIFYING)
        vr=VerificationRunner(self.repo/'.orch'/'integration'/'final');ok=all(vr.run(c,cwd=self.repo,name=f'final-{i}').exit_code==0 for i,c in enumerate(commands))
        if self.store and run_id:
            from orch.models.state import RunState
            self.store.set_run_state(run_id,RunState.READY_FOR_PROMOTION if ok else RunState.FAILED)
        return ok
