from __future__ import annotations
from pathlib import Path
from pydantic import BaseModel, ConfigDict
from orch.models.state import TaskState
class TaskAttempt(BaseModel):
    model_config=ConfigDict(extra='forbid')
    run_id:str; task_id:str; attempt_id:str; attempt_number:int; generation:int; branch:str; worktree_path:str; base_sha:str; head_sha:str|None=None; task_spec_sha256:str; prompt_sha256:str|None=None; state:TaskState; version:int=0
class RuntimeEnvironment(BaseModel):
    model_config=ConfigDict(extra='forbid',arbitrary_types_allowed=True)
    root:Path; env:dict[str,str]
