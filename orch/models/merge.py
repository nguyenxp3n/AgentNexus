from __future__ import annotations
from enum import StrEnum
from pydantic import BaseModel, ConfigDict, Field
class MergeDisposition(StrEnum): PASS='PASS'; FAIL='FAIL'; CONFLICT='CONFLICT'; ROLLED_BACK='ROLLED_BACK'
class MergeResult(BaseModel):
    model_config=ConfigDict(extra='forbid')
    task_id:str; attempt_id:str; integration_before_sha:str; candidate_head_sha:str; merge_commit_sha:str|None=None; integration_after_sha:str; status:MergeDisposition; regression_exit_codes:list[int]=Field(default_factory=list)
class CIState(StrEnum): PENDING='pending'; RUNNING='running'; PASS='pass'; FAIL='fail'; CANCELLED='cancelled'; TIMED_OUT='timed_out'; UNKNOWN='unknown'
