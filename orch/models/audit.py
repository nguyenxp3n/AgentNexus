from __future__ import annotations
from datetime import datetime, timezone
from enum import StrEnum
from pydantic import BaseModel, ConfigDict, Field
class AuditDisposition(StrEnum): PASS='PASS'; FAIL='FAIL'; UNKNOWN='UNKNOWN'; VIOLATION='VIOLATION'
class Severity(StrEnum): CRITICAL='critical'; HIGH='high'; MEDIUM='medium'; LOW='low'; INFO='info'
class AuditFinding(BaseModel):
    model_config=ConfigDict(extra='forbid')
    finding_id:str; gate:str; severity:Severity; code:str; message:str; path:str|None=None
class AuditStepResult(BaseModel):
    model_config=ConfigDict(extra='forbid')
    name:str; disposition:AuditDisposition; detail:str=''; exit_code:int|None=None; stdout_sha256:str|None=None; stderr_sha256:str|None=None
class EvidenceRef(BaseModel):
    model_config=ConfigDict(extra='forbid')
    kind:str; path:str; sha256:str; size_bytes:int
class AuditReport(BaseModel):
    model_config=ConfigDict(extra='forbid')
    audit_id:str; run_id:str; task_id:str; attempt_id:str; base_sha:str; head_sha:str; task_spec_sha256:str; prompt_sha256:str|None=None; evidence_manifest_sha256:str=''; steps:list[AuditStepResult]; findings:list[AuditFinding]=Field(default_factory=list); evidence:list[EvidenceRef]=Field(default_factory=list); disposition:AuditDisposition; certificate_sha256:str=''; completed_at:datetime=Field(default_factory=lambda:datetime.now(timezone.utc))
class CertificateDigest(BaseModel): algorithm:str='sha256'; sha256:str
