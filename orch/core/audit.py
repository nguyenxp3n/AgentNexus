from __future__ import annotations
import fnmatch,hashlib,json,re,uuid
from dataclasses import dataclass
from pathlib import Path
from orch.core.git import GitRepository
from orch.core.regression import VerificationRunner
from orch.models.audit import AuditDisposition,AuditFinding,AuditReport,AuditStepResult,Severity,CertificateDigest,EvidenceRef
from orch.models.execution import TaskAttempt
from orch.models.task import TaskSpec,VerificationSpec

_SECRET_RULES=[('PRIVATE_KEY',re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----')),('GITHUB_TOKEN',re.compile(r'gh[ps]_[A-Za-z0-9]{20,}')),('OPENAI_KEY',re.compile(r'sk-[A-Za-z0-9_-]{16,}')),('AWS_KEY',re.compile(r'AKIA[0-9A-Z]{16}'))]
@dataclass(frozen=True)
class SecretFinding: rule_id:str; fingerprint:str; match:str

def canonical_json_bytes(payload:dict)->bytes:
    payload={k:v for k,v in payload.items() if k!='certificate_sha256'}
    return json.dumps(payload,sort_keys=True,separators=(',',':'),ensure_ascii=False,default=str).encode()
def canonical_certificate_bytes(payload:dict)->CertificateDigest:return CertificateDigest(sha256=hashlib.sha256(canonical_json_bytes(payload)).hexdigest())
def verify_certificate_digest(payload:dict,digest:str)->bool:return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()==digest
def task_spec_digest(task:TaskSpec)->str:return hashlib.sha256(canonical_json_bytes(task.model_dump(mode='json'))).hexdigest()
def scan_secrets(text:str)->list[SecretFinding]:
    out=[]
    if re.search(r'(?m)^diff --git a/\.env(?:\s|$)',text) or re.search(r'(?m)^\+[^+].*\.env',text):out.append(SecretFinding('ENV_FILE',hashlib.sha256(b'.env').hexdigest(),'.env'))
    for rid,pat in _SECRET_RULES:
        for m in pat.finditer(text):
            val=m.group(0);out.append(SecretFinding(rid,hashlib.sha256(val.encode()).hexdigest(),val[:12]))
    return out

def certificate_payload(report:AuditReport)->dict:
    return {'schema_version':'1','audit_id':report.audit_id,'run_id':report.run_id,'task_id':report.task_id,'attempt_id':report.attempt_id,'base_sha':report.base_sha,'head_sha':report.head_sha,'task_spec_sha256':report.task_spec_sha256,'prompt_sha256':report.prompt_sha256,'evidence_manifest_sha256':report.evidence_manifest_sha256,'gates':{s.name:s.disposition.value for s in report.steps},'disposition':report.disposition.value}
class AuditRunner:
    def __init__(self,repo:Path,evidence_root:Path|None=None):self.repo=Path(repo).resolve();self.git=GitRepository(self.repo);self.root=Path(evidence_root) if evidence_root else self.repo/'.orch'/'audits'
    def _manifest_digest(self,evidence:list[EvidenceRef])->str:
        payload=[e.model_dump(mode='json') for e in sorted(evidence,key=lambda x:(x.kind,x.path))]
        return hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    def _finding(self,idx:int,gate:str,severity:Severity,code:str,message:str,path:str|None=None):return AuditFinding(finding_id=f'AUD-{idx:03d}',gate=gate,severity=severity,code=code,message=message,path=path)
    def _head_unchanged(self,expected:str)->bool:return self.git.head()==expected
    def run(self,a:TaskAttempt,task:TaskSpec)->AuditReport:
        audit_id='AUD-'+uuid.uuid4().hex[:12];adir=self.root/task.id/a.attempt_id/audit_id;adir.mkdir(parents=True,exist_ok=True);steps=[];findings=[];evidence=[];idx=0
        # Gate 1: identity/workspace integrity. Fail-fast on wrong identity.
        identity_ok=True;details=[]
        if self.git.head()!=a.head_sha:identity_ok=False;details.append('HEAD mismatch');idx+=1;findings.append(self._finding(idx,'git_integrity',Severity.HIGH,'CANDIDATE_IDENTITY_MISMATCH','HEAD differs from frozen candidate'))
        if self.git.branch()!=a.branch:identity_ok=False;details.append('branch mismatch');idx+=1;findings.append(self._finding(idx,'git_integrity',Severity.HIGH,'CANDIDATE_IDENTITY_MISMATCH','branch differs from frozen candidate'))
        status=self.git.status_lines()
        if status:identity_ok=False;details.append('working tree dirty');idx+=1;findings.append(self._finding(idx,'git_integrity',Severity.HIGH,'WORKTREE_NOT_CLEAN','working tree contains changes'))
        actual_task_hash=task_spec_digest(task)
        if actual_task_hash!=a.task_spec_sha256:identity_ok=False;details.append('task spec drift');idx+=1;findings.append(self._finding(idx,'git_integrity',Severity.HIGH,'AUDIT_INPUT_DRIFT','task specification hash changed'))
        steps.append(AuditStepResult(name='git_integrity',disposition=AuditDisposition.PASS if identity_ok else AuditDisposition.VIOLATION,detail='; '.join(details)))
        if not identity_ok:
            for n in ['scope','verification','security','acceptance','artifacts','signoff']:steps.append(AuditStepResult(name=n,disposition=AuditDisposition.UNKNOWN,detail='blocked by identity gate'))
            report=AuditReport(audit_id=audit_id,run_id=a.run_id,task_id=a.task_id,attempt_id=a.attempt_id,base_sha=a.base_sha,head_sha=a.head_sha or '',task_spec_sha256=a.task_spec_sha256,prompt_sha256=a.prompt_sha256,evidence_manifest_sha256=self._manifest_digest([]),steps=steps,findings=findings,disposition=AuditDisposition.VIOLATION)
            report.certificate_sha256=canonical_certificate_bytes(certificate_payload(report)).sha256;return report
        # Evidence snapshot diff.
        patch=self.git.diff_patch(a.base_sha,a.head_sha or self.git.head());patch_path=adir/'diff.patch';patch_path.write_text(patch);evidence.append(EvidenceRef(kind='git_diff',path=str(patch_path),sha256=hashlib.sha256(patch_path.read_bytes()).hexdigest(),size_bytes=patch_path.stat().st_size))
        # Gate 2 scope.
        scope_ok=True
        for line in self.git.diff_name_status(a.base_sha,a.head_sha or self.git.head()):
            cols=line.split('\t'); paths=cols[1:]
            for path in paths:
                allowed=any(fnmatch.fnmatch(path,p) for p in task.ownership.allowed_paths)
                forbidden=any(fnmatch.fnmatch(path,p) for p in task.ownership.forbidden_paths)
                readonly=any(fnmatch.fnmatch(path,p) for p in task.ownership.readonly_paths)
                if not allowed or forbidden or readonly:
                    scope_ok=False;idx+=1;findings.append(self._finding(idx,'scope',Severity.HIGH,'SCOPE_EXPANSION_VIOLATION',f'unauthorized changed path: {path}',path))
        steps.append(AuditStepResult(name='scope',disposition=AuditDisposition.PASS if scope_ok else AuditDisposition.VIOLATION))
        # Gate 3 independent verification.
        verify_ok=True;vr=VerificationRunner(adir/'verification')
        for n,v in enumerate(task.verification):
            if v.type!='command' or not v.command:continue
            ev=vr.run(v.command,cwd=self.repo,name=f'check-{n}',timeout_seconds=task.timeout_seconds);evidence.extend([EvidenceRef(kind='stdout',path=str(ev.stdout_path),sha256=ev.stdout_sha256,size_bytes=ev.stdout_path.stat().st_size),EvidenceRef(kind='stderr',path=str(ev.stderr_path),sha256=ev.stderr_sha256,size_bytes=ev.stderr_path.stat().st_size)])
            if ev.timed_out or ev.exit_code!=0:
                verify_ok=False;idx+=1;findings.append(self._finding(idx,'verification',Severity.HIGH,'VERIFICATION_FAILED',f'command failed: {v.command}'))
        steps.append(AuditStepResult(name='verification',disposition=AuditDisposition.PASS if verify_ok else AuditDisposition.FAIL))
        if not self._head_unchanged(a.head_sha or ''):
            idx+=1;findings.append(self._finding(idx,'git_integrity',Severity.HIGH,'CANDIDATE_MUTATED_DURING_AUDIT','HEAD changed during audit'));steps[2]=AuditStepResult(name='verification',disposition=AuditDisposition.VIOLATION,detail='candidate mutated')
        # Gate 4 security.
        secrets=scan_secrets(patch);security_ok=not secrets
        for sf in secrets:idx+=1;findings.append(self._finding(idx,'security',Severity.CRITICAL,'SECRET_DETECTED',f'{sf.rule_id} detected'))
        steps.append(AuditStepResult(name='security',disposition=AuditDisposition.PASS if security_ok else AuditDisposition.VIOLATION))
        # Gate 5 acceptance.
        accept_ok=True;accept_unknown=False
        for criterion in task.acceptance.criteria:
            v=criterion.verification
            if v is None:continue
            if v.type=='manual_review':accept_unknown=True;idx+=1;findings.append(self._finding(idx,'acceptance',Severity.MEDIUM,'MANUAL_REVIEW_REQUIRED',criterion.description));continue
            if v.type=='file_exists' and (not v.path or not (self.repo/v.path).exists()):accept_ok=False;idx+=1;findings.append(self._finding(idx,'acceptance',Severity.HIGH,'ACCEPTANCE_FAILED',criterion.description,v.path))
            if v.type=='file_matches':
                if not v.path or not (self.repo/v.path).exists() or not re.search(v.pattern or '',(self.repo/v.path).read_text()):accept_ok=False;idx+=1;findings.append(self._finding(idx,'acceptance',Severity.HIGH,'ACCEPTANCE_FAILED',criterion.description,v.path))
            if v.type=='command' and v.command:
                ev=vr.run(v.command,cwd=self.repo,name=f'ac-{criterion.id}',timeout_seconds=task.timeout_seconds)
                if ev.timed_out or ev.exit_code!=0:accept_ok=False;idx+=1;findings.append(self._finding(idx,'acceptance',Severity.HIGH,'ACCEPTANCE_FAILED',criterion.description))
        acc_disp=AuditDisposition.UNKNOWN if accept_unknown else (AuditDisposition.PASS if accept_ok else AuditDisposition.FAIL);steps.append(AuditStepResult(name='acceptance',disposition=acc_disp))
        # Gate 6 artifacts.
        art_ok=True
        for art in task.artifacts:
            if art.required and not (self.repo/art.path).exists():art_ok=False;idx+=1;findings.append(self._finding(idx,'artifacts',Severity.HIGH,'REQUIRED_ARTIFACT_MISSING',f'missing artifact {art.path}',art.path))
        steps.append(AuditStepResult(name='artifacts',disposition=AuditDisposition.PASS if art_ok else AuditDisposition.FAIL))
        required_pass=all(s.disposition is AuditDisposition.PASS for s in steps)
        steps.append(AuditStepResult(name='signoff',disposition=AuditDisposition.PASS if required_pass else AuditDisposition.FAIL))
        disposition=AuditDisposition.PASS if all(s.disposition is AuditDisposition.PASS for s in steps) else (AuditDisposition.VIOLATION if any(s.disposition is AuditDisposition.VIOLATION for s in steps) else AuditDisposition.FAIL)
        report=AuditReport(audit_id=audit_id,run_id=a.run_id,task_id=a.task_id,attempt_id=a.attempt_id,base_sha=a.base_sha,head_sha=a.head_sha or '',task_spec_sha256=a.task_spec_sha256,prompt_sha256=a.prompt_sha256,evidence_manifest_sha256=self._manifest_digest(evidence),steps=steps,findings=findings,evidence=evidence,disposition=disposition)
        report.certificate_sha256=canonical_certificate_bytes(certificate_payload(report)).sha256
        (adir/'audit_report.json').write_text(report.model_dump_json(indent=2));(adir/'certificate.sha256').write_text(report.certificate_sha256+'\n')
        return report
