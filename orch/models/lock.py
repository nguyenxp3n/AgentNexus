from __future__ import annotations
from enum import StrEnum
from pydantic import BaseModel, ConfigDict, Field
class LockMode(StrEnum): SHARED_READ='shared_read'; EXCLUSIVE_WRITE='exclusive_write'; SHARED_WRITE_CONTROLLED='shared_write_controlled'; INTEGRATION_ONLY='integration_only'
class ResourceRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    paths:list[str]=Field(default_factory=list); migration_count:int=Field(0,ge=0); ports:dict[str,int]=Field(default_factory=dict); lease_seconds:int=Field(120,ge=1)
