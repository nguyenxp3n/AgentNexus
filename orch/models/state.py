from __future__ import annotations
from enum import StrEnum

class TaskState(StrEnum):
    PENDING='PENDING'; READY='READY'; ASSIGNED='ASSIGNED'; SPAWNED='SPAWNED'; IN_PROGRESS='IN_PROGRESS'; AUDIT_READY='AUDIT_READY'; AUDITED='AUDITED'; MERGING='MERGING'; COMPLETED='COMPLETED'; REJECTED='REJECTED'; RECOVERING='RECOVERING'
class RunState(StrEnum):
    CREATED='CREATED'; PLANNED='PLANNED'; RUNNING='RUNNING'; INTEGRATING='INTEGRATING'; VERIFYING='VERIFYING'; READY_FOR_PROMOTION='READY_FOR_PROMOTION'; COMPLETED='COMPLETED'; FAILED='FAILED'; SAFE_MODE='SAFE_MODE'
class TransitionActor(StrEnum):
    SCHEDULER='scheduler'; ORCHESTRATOR='orchestrator'; DISPATCHER='dispatcher'; RUNTIME_MONITOR='runtime_monitor'; AUDITOR='auditor'; MERGER='merger'; RECOVERY='recovery'; WORKER='worker'
class WorktreeStatus(StrEnum): PROVISIONING='PROVISIONING'; READY='READY'; ACTIVE='ACTIVE'; DIRTY='DIRTY'; AUDIT_FROZEN='AUDIT_FROZEN'; STALE='STALE'; RECOVERING='RECOVERING'; REMOVED='REMOVED'

_ALLOWED={
(TaskState.PENDING,TaskState.READY):{TransitionActor.SCHEDULER,TransitionActor.RECOVERY},
(TaskState.READY,TaskState.ASSIGNED):{TransitionActor.ORCHESTRATOR},
(TaskState.ASSIGNED,TaskState.SPAWNED):{TransitionActor.DISPATCHER},
(TaskState.SPAWNED,TaskState.IN_PROGRESS):{TransitionActor.RUNTIME_MONITOR},
(TaskState.IN_PROGRESS,TaskState.AUDIT_READY):{TransitionActor.RUNTIME_MONITOR},
(TaskState.AUDIT_READY,TaskState.AUDITED):{TransitionActor.AUDITOR},
(TaskState.AUDIT_READY,TaskState.REJECTED):{TransitionActor.AUDITOR},
(TaskState.AUDITED,TaskState.MERGING):{TransitionActor.MERGER},
(TaskState.MERGING,TaskState.COMPLETED):{TransitionActor.MERGER},
(TaskState.MERGING,TaskState.RECOVERING):{TransitionActor.MERGER,TransitionActor.RECOVERY},
(TaskState.ASSIGNED,TaskState.RECOVERING):{TransitionActor.RECOVERY},
(TaskState.SPAWNED,TaskState.RECOVERING):{TransitionActor.RECOVERY},
(TaskState.IN_PROGRESS,TaskState.RECOVERING):{TransitionActor.RECOVERY},
(TaskState.RECOVERING,TaskState.READY):{TransitionActor.RECOVERY},
(TaskState.RECOVERING,TaskState.REJECTED):{TransitionActor.RECOVERY},
}
def validate_task_transition(old:TaskState,new:TaskState,actor:TransitionActor)->bool:return actor in _ALLOWED.get((old,new),set())
