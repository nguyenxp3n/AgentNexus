from __future__ import annotations
from enum import StrEnum
from pathlib import PurePosixPath
from pydantic import BaseModel, ConfigDict, Field, model_validator

class StrictModel(BaseModel): model_config=ConfigDict(extra='forbid')
class AgentRole(StrEnum): ARCHITECT='architect'; CORE_BACKEND='core_backend'; FULLSTACK_UI='fullstack_ui'; QA_AUDIT='qa_audit'; DEVOPS_CICD='devops_cicd'
class OwnershipSpec(StrictModel):
    allowed_paths:list[str]=Field(default_factory=list); readonly_paths:list[str]=Field(default_factory=list); forbidden_paths:list[str]=Field(default_factory=list)
    @property
    def can_write_anything(self)->bool:return False
class ResourceSpec(StrictModel):
    migration_count:int=Field(0,ge=0); ports:dict[str,int]=Field(default_factory=dict)
class VerificationSpec(StrictModel):
    type:str='command'; command:list[str]|None=None; path:str|None=None; pattern:str|None=None; required:bool=True; shell:bool=False
class AcceptanceCriterion(StrictModel): id:str; description:str; verification:VerificationSpec|None=None
class AcceptanceSpec(StrictModel): criteria:list[AcceptanceCriterion]=Field(default_factory=list)
class HarnessSpec(StrictModel): adapter:str='generic'; env_allowlist:list[str]=Field(default_factory=list)
class ArtifactSpec(StrictModel): path:str; required:bool=True
class TaskSpec(StrictModel):
    id:str=Field(min_length=1); title:str; description:str; role:AgentRole; dependencies:list[str]=Field(default_factory=list); ownership:OwnershipSpec=Field(default_factory=OwnershipSpec); resources:ResourceSpec=Field(default_factory=ResourceSpec); acceptance:AcceptanceSpec=Field(default_factory=AcceptanceSpec); verification:list[VerificationSpec]=Field(default_factory=list); artifacts:list[ArtifactSpec]=Field(default_factory=list); harness:HarnessSpec|None=None; timeout_seconds:int=Field(3600,ge=1); max_attempts:int=Field(1,ge=1); priority:int=0; allow_noop:bool=False
    @model_validator(mode='after')
    def safe_id(self):
        if '..' in self.id or '/' in self.id or '\\' in self.id: raise ValueError('unsafe task id')
        return self
class ProjectInfo(StrictModel): name:str
class ProjectPlan(StrictModel):
    version:int=1; project:ProjectInfo; tasks:list[TaskSpec]
    @model_validator(mode='after')
    def unique(self):
        ids=[t.id for t in self.tasks]
        if len(ids)!=len(set(ids)): raise ValueError('duplicate task id')
        return self
