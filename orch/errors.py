from __future__ import annotations
from enum import IntEnum

class ExitCode(IntEnum):
    SUCCESS=0
    CONFIG_INVALID=10; PLAN_INVALID=11
    AUDIT_FAILED=20; SCOPE_VIOLATION=21; SECRET_VIOLATION=22; MISSING_EVIDENCE=23; CANDIDATE_IDENTITY_MISMATCH=24
    LOCK_CONFLICT=31
    WORKTREE_INVALID=42
    HARNESS_UNAVAILABLE=51; AGENT_PROCESS_FAILED=52
    MERGE_CONFLICT=61; REGRESSION_FAILED=62
    CI_FAILED=71; CI_TIMEOUT=72
    RECOVERY_REQUIRED=81
    GLOBAL_SAFE_MODE=90; INTERNAL_ERROR=99

class OrchError(RuntimeError):
    exit_code=ExitCode.INTERNAL_ERROR
class ConfigError(OrchError): exit_code=ExitCode.CONFIG_INVALID
class PlanError(OrchError): exit_code=ExitCode.PLAN_INVALID
class StateTransitionError(OrchError): pass
class StateVersionConflict(StateTransitionError): pass
class ResourceUnavailable(OrchError): exit_code=ExitCode.LOCK_CONFLICT
class StaleGenerationError(ResourceUnavailable): pass
class PathOwnershipError(ResourceUnavailable): pass
class WorktreeError(OrchError): exit_code=ExitCode.WORKTREE_INVALID
class HarnessError(OrchError): exit_code=ExitCode.HARNESS_UNAVAILABLE
class AuditError(OrchError): exit_code=ExitCode.AUDIT_FAILED
class ScopeViolation(AuditError): exit_code=ExitCode.SCOPE_VIOLATION
class SecretViolation(AuditError): exit_code=ExitCode.SECRET_VIOLATION
class AuditCertificateStale(AuditError): exit_code=ExitCode.CANDIDATE_IDENTITY_MISMATCH
class MergeError(OrchError): exit_code=ExitCode.MERGE_CONFLICT
class IntegrationBranchDrift(MergeError): pass
class RegressionFailed(MergeError): exit_code=ExitCode.REGRESSION_FAILED
class GitHubError(OrchError): exit_code=ExitCode.CI_FAILED
class RecoveryError(OrchError): exit_code=ExitCode.RECOVERY_REQUIRED
class SafeModeError(OrchError): exit_code=ExitCode.GLOBAL_SAFE_MODE
