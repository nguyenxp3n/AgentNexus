from __future__ import annotations
import os
from pathlib import Path
from typing import Any
import yaml
from pydantic import BaseModel, ConfigDict, Field

class StrictModel(BaseModel):
    model_config=ConfigDict(extra='forbid')
class EngineConfig(StrictModel): mode:str='production'
class SchedulerConfig(StrictModel):
    max_parallel_agents:int=Field(8,ge=1,le=128); heartbeat_timeout_seconds:int=Field(60,ge=1); progress_timeout_seconds:int=Field(900,ge=1); spawn_timeout_seconds:int=Field(30,ge=1)
class GitConfig(StrictModel):
    integration_branch:str='main'; integration_mode:str='staging_branch'; worktree_root:str='.worktrees'; protected_branches:list[str]=Field(default_factory=lambda:['main','master','production']); tag_integrations:bool=False
class LockConfig(StrictModel): default_lease_seconds:int=Field(120,ge=1)
class PortConfig(StrictModel): ranges:dict[str,tuple[int,int]]=Field(default_factory=lambda:{'api':(8081,8199),'web':(3001,3099),'test':(9001,9099)})
class AuditConfig(StrictModel): secret_scan:bool=True; require_clean_tree:bool=True
class HarnessDefinition(StrictModel): type:str='generic'; command:list[str]=Field(default_factory=list); prompt_delivery:str='stdin'; env_allowlist:list[str]=Field(default_factory=list)
class HarnessRegistryConfig(StrictModel):
    definitions:dict[str,HarnessDefinition]=Field(default_factory=dict); default:str|None=None
class GitHubConfig(StrictModel): enabled:bool=False; pr_strategy:str='integration'; required_checks:list[str]=Field(default_factory=list); ci_watch_timeout_seconds:int=3600
class IntegrationConfig(StrictModel):
    failure_policy:str='stop'; regression_commands:list[list[str]]=Field(default_factory=list); final_commands:list[list[str]]=Field(default_factory=list)
class OrchConfig(StrictModel):
    engine:EngineConfig=Field(default_factory=EngineConfig); scheduler:SchedulerConfig=Field(default_factory=SchedulerConfig); git:GitConfig=Field(default_factory=GitConfig); locks:LockConfig=Field(default_factory=LockConfig); ports:PortConfig=Field(default_factory=PortConfig); audit:AuditConfig=Field(default_factory=AuditConfig); harnesses:HarnessRegistryConfig=Field(default_factory=HarnessRegistryConfig); github:GitHubConfig=Field(default_factory=GitHubConfig); integration:IntegrationConfig=Field(default_factory=IntegrationConfig)

def _coerce(value:str)->Any:
    try:return yaml.safe_load(value)
    except Exception:return value

def load_config(repo_root:Path)->OrchConfig:
    path=Path(repo_root)/'.orch'/'config.yaml'; data:dict[str,Any]={}
    if path.exists(): data=yaml.safe_load(path.read_text()) or {}
    for key,value in os.environ.items():
        if not key.startswith('ORCH_') or '__' not in key: continue
        parts=key[5:].lower().split('__'); cur=data
        for p in parts[:-1]: cur=cur.setdefault(p,{})
        cur[parts[-1]]=_coerce(value)
    return OrchConfig.model_validate(data)
