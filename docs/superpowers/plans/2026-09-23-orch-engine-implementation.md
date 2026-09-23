# AgentNexus Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a production-ready Python 3.12+ `agent-nexus` package and `nexus` CLI that safely coordinates 5–10+ concurrent coding agents with transactional scheduling, isolated Git worktrees, independent forensic audit, deterministic sequential integration, recovery, and optional GitHub PR/CI automation.

**Architecture:** The engine is split into control, execution, trust, and recovery planes. SQLite WAL is the authoritative mutable store; NetworkX models task dependencies; workers run in attempt-scoped Git worktrees through harness adapters; candidates are frozen and independently audited before an exclusive merge controller integrates them and reruns regression tests.

**Tech Stack:** Python 3.12+, Typer, Rich, Pydantic v2, NetworkX, PyYAML, stdlib `sqlite3`, stdlib `asyncio`, native Git CLI, optional GitHub CLI (`gh`), pytest, pytest-asyncio, mypy, Ruff, build.

**Spec:** `docs/superpowers/specs/2026-09-23-orch-engine-design.md`

## Global Constraints

- Python runtime is `>=3.12`.
- Public package namespace is `orch`; console entry point is `orch = "orch.cli.main:app"`.
- Runtime source of truth is SQLite with WAL, foreign keys enabled, synchronous FULL, and a 5000 ms busy timeout.
- Pydantic v2 models use `extra="forbid"` unless an extension map is explicitly documented.
- The canonical task FSM includes `PENDING`, `READY`, `ASSIGNED`, `SPAWNED`, `IN_PROGRESS`, `AUDIT_READY`, `AUDITED`, `MERGING`, `COMPLETED`, `REJECTED`, and `RECOVERING`.
- Workers cannot directly set `AUDITED`, `MERGING`, or `COMPLETED`.
- All assignment resources are acquired atomically before process spawn; partial allocation is forbidden.
- Migration slots are never reassigned to a different attempt after issuance; released ports may be reused only after liveness reconciliation.
- One branch and one worktree exist per task attempt.
- Native CLI workers do not push or merge by default.
- Audit is read-only, exact-SHA bound, and hard-gated; missing/unknown evidence cannot pass.
- Integration is sequential under an exclusive integration lock; regression runs after every merge.
- Ambiguous exclusive path overlap fails closed in production mode.
- Unknown recovery state blocks unsafe mutation through `SAFE_MODE`.
- No feature may claim stronger sandbox, CI, provider, or GitHub guarantees than were physically verified.
- Feature and bug-fix implementation follows TDD; each task below ends with fresh verification and a focused commit.

## Review Focus

1. **Two independent orchestrator processes race on the same READY task:** exactly one may acquire assignment/state ownership; the other must receive a deterministic conflict rather than duplicate work. Covered in Task 3 and Task 5.
2. **A symlinked or traversal-shaped ownership path resolves outside the repository:** validation and allocation must reject it before spawn. Covered in Task 5.
3. **A worker exits successfully but leaves dirty/untracked changes or a stale generation:** candidate freeze must refuse `AUDIT_READY`. Covered in Task 8.
4. **An audited candidate changes or the integration branch drifts before merge:** certificate revalidation/integration SHA checks must block mutation rather than merge stale evidence. Covered in Task 10.
5. **The orchestrator crashes after a physical Git merge but before durable DB finalization:** restart recovery must reconcile the merge from parent SHAs or enter safe mode without guessing. Covered in Task 12 and Task 14.

---

## File Structure Map

The implementation is intentionally split by responsibility so each file has one primary job.

- `pyproject.toml` — package metadata, runtime/dev dependencies, console script, tool configuration.
- `orch/config.py` — strict configuration loading, defaults, environment overrides.
- `orch/errors.py` — typed exception hierarchy and stable exit-code mapping.
- `orch/models/state.py` — task/run/process/worktree enums and transition authorities.
- `orch/models/task.py` — task/plan/ownership/resource/acceptance models.
- `orch/models/lock.py` — lock/resource/migration/port models.
- `orch/models/execution.py` — attempts, process handles/results, workspace/runtime identities.
- `orch/models/audit.py` — audit criteria, findings, evidence, reports, certificate models.
- `orch/models/merge.py` — merge queue/result/integration/CI models.
- `orch/core/state.py` — SQLite schema, migrations, transactions, optimistic state/event updates.
- `orch/core/observability.py` — structured diagnostic logging context, redaction, and in-process operational counters.
- `orch/core/dag.py` — plan parsing, NetworkX validation, waves, dependency readiness.
- `orch/core/locks.py` — path normalization/overlap, transactional lock acquisition, migration/port allocation, lease handling.
- `orch/core/git.py` — safe argv-based Git command primitives and repository identity helpers.
- `orch/core/worktree.py` — attempt-scoped worktree lifecycle and inspection.
- `orch/core/environment.py` — runtime directory/env isolation and secret-safe passthrough.
- `orch/core/process.py` — async subprocess supervision, stdout/stderr pumps, timeout/termination handling.
- `orch/core/harness/base.py` — harness protocol and capability/result types.
- `orch/core/harness/discovery.py` — executable/version/capability discovery helpers.
- `orch/core/harness/generic_cli.py` — generic argv/stdin prompt adapter.
- `orch/core/harness/claude_code.py` — Claude Code adapter.
- `orch/core/harness/gemini_cli.py` — Gemini CLI adapter.
- `orch/core/harness/antigravity.py` — Antigravity adapter with fail-closed discovery.
- `orch/core/harness/aider.py` — Aider adapter.
- `orch/core/orchestrator.py` — cross-subsystem lifecycle coordination; no vendor-specific process logic.
- `orch/core/audit.py` — seven-gate audit runner and evidence/certificate generation.
- `orch/core/regression.py` — reusable verification command runner for audit/integration.
- `orch/core/integration.py` — integration worktree/ref validation and merge journal helpers.
- `orch/core/merger.py` — deterministic queue, certificate revalidation, merge/rollback lifecycle.
- `orch/core/github.py` — structured `gh` wrapper, PR idempotency, exact-SHA CI binding.
- `orch/core/recovery.py` — physical reconciliation, recovery bundles, orphan cleanup, safe mode.
- `orch/cli/*.py` — thin Typer commands, Rich rendering, JSON results, exit-code translation.
- `tests/fixtures/fake_agent.py` — deterministic fake worker behaviors for runtime/E2E tests.
- `tests/unit/` — pure/near-pure model, FSM, DAG, path, hash tests.
- `tests/component/` — real temporary SQLite/Git/process subsystem tests.
- `tests/integration/` — multi-subsystem local flows.
- `tests/adversarial/` — races, stale generation, crash windows, security-shaped inputs.
- `tests/e2e/` — full local CLI lifecycle.

---

### Task 1: Package shell, configuration, errors, and CLI bootstrap

**Files:**
- Create: `pyproject.toml`
- Create: `README.md`
- Create: `LICENSE`
- Create: `orch/__init__.py`
- Create: `orch/config.py`
- Create: `orch/errors.py`
- Create: `orch/cli/__init__.py`
- Create: `orch/cli/main.py`
- Create: `tests/unit/test_config.py`
- Create: `tests/unit/test_errors.py`

**Interfaces:**
- Consumes: none.
- Produces: `OrchConfig`, `load_config(repo_root: Path) -> OrchConfig`, `OrchError`, `ExitCode`, and Typer root `app` used by all later CLI tasks.

- [ ] **Step 1: Write failing tests for strict config, defaults, environment override, and exit-code families**

```python
# tests/unit/test_config.py
from pathlib import Path

import pytest
from pydantic import ValidationError

from orch.config import OrchConfig, load_config


def test_config_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        OrchConfig.model_validate({"scheduler": {"max_agnts": 8}})


def test_load_config_applies_nested_environment_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".orch").mkdir()
    (tmp_path / ".orch" / "config.yaml").write_text("scheduler:\n  max_parallel_agents: 4\n")
    monkeypatch.setenv("ORCH_SCHEDULER__MAX_PARALLEL_AGENTS", "7")
    assert load_config(tmp_path).scheduler.max_parallel_agents == 7
```

```python
# tests/unit/test_errors.py
from orch.errors import ExitCode


def test_exit_code_families_are_stable() -> None:
    assert ExitCode.SUCCESS == 0
    assert 10 <= ExitCode.CONFIG_INVALID <= 19
    assert 20 <= ExitCode.AUDIT_FAILED <= 29
    assert 90 <= ExitCode.GLOBAL_SAFE_MODE <= 99
```

- [ ] **Step 2: Run the focused tests and verify they fail because the package/config/error types do not exist**

Run: `pytest tests/unit/test_config.py tests/unit/test_errors.py -q`

Expected: collection/import failure for `orch.config` and `orch.errors`.

- [ ] **Step 3: Add package metadata and strict configuration models**

Implement `pyproject.toml` with Python `>=3.12`, Hatchling, Typer, Rich, Pydantic v2, NetworkX, PyYAML, and dev dependencies. Implement nested Pydantic configuration models in `orch/config.py` with defaults from the spec and `extra="forbid"`. Parse `ORCH_SECTION__FIELD` environment overrides into the YAML mapping before model validation.

```python
# orch/config.py
class SchedulerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_parallel_agents: int = Field(default=8, ge=1, le=128)
    heartbeat_timeout_seconds: int = Field(default=60, ge=1)
    progress_timeout_seconds: int = Field(default=900, ge=1)


class OrchConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    engine: EngineConfig = Field(default_factory=EngineConfig)
    scheduler: SchedulerConfig = Field(default_factory=SchedulerConfig)
    git: GitConfig = Field(default_factory=GitConfig)
    locks: LockConfig = Field(default_factory=LockConfig)
    ports: PortConfig = Field(default_factory=PortConfig)
    audit: AuditConfig = Field(default_factory=AuditConfig)
    harnesses: HarnessRegistryConfig = Field(default_factory=HarnessRegistryConfig)
    github: GitHubConfig = Field(default_factory=GitHubConfig)


def load_config(repo_root: Path) -> OrchConfig: ...
```

- [ ] **Step 4: Implement typed errors, stable exit codes, and a minimal Typer root app**

```python
# orch/errors.py
class ExitCode(IntEnum):
    SUCCESS = 0
    CONFIG_INVALID = 10
    PLAN_INVALID = 11
    AUDIT_FAILED = 20
    SCOPE_VIOLATION = 21
    SECRET_VIOLATION = 22
    MISSING_EVIDENCE = 23
    CANDIDATE_IDENTITY_MISMATCH = 24
    LOCK_CONFLICT = 31
    WORKTREE_INVALID = 42
    HARNESS_UNAVAILABLE = 51
    AGENT_PROCESS_FAILED = 52
    MERGE_CONFLICT = 61
    REGRESSION_FAILED = 62
    CI_FAILED = 71
    CI_TIMEOUT = 72
    RECOVERY_REQUIRED = 81
    GLOBAL_SAFE_MODE = 90
    INTERNAL_ERROR = 99


class OrchError(RuntimeError):
    exit_code: ExitCode = ExitCode.INTERNAL_ERROR
```

```python
# orch/cli/main.py
app = typer.Typer(no_args_is_help=True, rich_markup_mode="rich")


@app.command("version")
def version() -> None:
    typer.echo(__version__)
```

- [ ] **Step 5: Run focused tests plus CLI smoke check**

Run: `pytest tests/unit/test_config.py tests/unit/test_errors.py -q && python -m orch.cli.main --help`

Expected: tests PASS and help exits 0.

- [ ] **Step 6: Commit Task 1**

```bash
git add pyproject.toml README.md LICENSE orch tests/unit/test_config.py tests/unit/test_errors.py
git commit -m "feat: bootstrap orch package and configuration"
```

---

### Task 2: Strict domain models and finite-state machine

**Files:**
- Create: `orch/models/__init__.py`
- Create: `orch/models/state.py`
- Create: `orch/models/task.py`
- Create: `orch/models/lock.py`
- Create: `orch/models/execution.py`
- Create: `orch/models/audit.py`
- Create: `orch/models/merge.py`
- Create: `tests/unit/test_models.py`
- Create: `tests/unit/test_state_machine.py`

**Interfaces:**
- Consumes: `OrchConfig` conventions from Task 1.
- Produces: canonical Pydantic types including `TaskSpec`, `ProjectPlan`, `TaskState`, `RunState`, `TransitionActor`, `TaskAttempt`, `ResourceRequest`, `AuditReport`, `AuditCertificate`, and `MergeResult`.

- [ ] **Step 1: Write failing model tests for strict fields, deny-write empty ownership, roles, and attempt identity**

```python
from pydantic import ValidationError
import pytest

from orch.models.task import AgentRole, OwnershipSpec, TaskSpec


def test_empty_write_ownership_is_deny_write() -> None:
    ownership = OwnershipSpec()
    assert ownership.allowed_paths == []
    assert ownership.can_write_anything is False


def test_task_rejects_unknown_field() -> None:
    with pytest.raises(ValidationError):
        TaskSpec.model_validate({
            "id": "TASK-1",
            "title": "x",
            "description": "x",
            "role": AgentRole.CORE_BACKEND,
            "dependencies": [],
            "ownership": {},
            "resources": {},
            "acceptance": {"criteria": []},
            "timeout_seconds": 60,
            "max_attempts": 1,
            "priority": 0,
            "allow_noop": False,
            "surprise": True,
        })
```

- [ ] **Step 2: Write failing FSM tests for legal authority, illegal shortcuts, and stale expected-state transitions**

```python
from orch.models.state import TaskState, TransitionActor, validate_task_transition


def test_worker_cannot_complete_task() -> None:
    assert not validate_task_transition(
        TaskState.IN_PROGRESS,
        TaskState.COMPLETED,
        TransitionActor.WORKER,
    )


def test_auditor_can_only_advance_audit_ready_to_audited_or_rejected() -> None:
    assert validate_task_transition(TaskState.AUDIT_READY, TaskState.AUDITED, TransitionActor.AUDITOR)
    assert not validate_task_transition(TaskState.IN_PROGRESS, TaskState.AUDITED, TransitionActor.AUDITOR)
```

- [ ] **Step 3: Run tests and verify imports/types are missing**

Run: `pytest tests/unit/test_models.py tests/unit/test_state_machine.py -q`

Expected: FAIL during import.

- [ ] **Step 4: Implement exact enums, task/resource/acceptance models, execution identity, and result models**

```python
class TaskState(StrEnum):
    PENDING = "PENDING"
    READY = "READY"
    ASSIGNED = "ASSIGNED"
    SPAWNED = "SPAWNED"
    IN_PROGRESS = "IN_PROGRESS"
    AUDIT_READY = "AUDIT_READY"
    AUDITED = "AUDITED"
    MERGING = "MERGING"
    COMPLETED = "COMPLETED"
    REJECTED = "REJECTED"
    RECOVERING = "RECOVERING"


class AgentRole(StrEnum):
    ARCHITECT = "architect"
    CORE_BACKEND = "core_backend"
    FULLSTACK_UI = "fullstack_ui"
    QA_AUDIT = "qa_audit"
    DEVOPS_CICD = "devops_cicd"
```

Define `TaskAttempt` with `run_id`, `task_id`, `attempt_id`, `attempt_number`, `generation`, `branch`, `worktree_path`, `base_sha`, optional `head_sha`, `task_spec_sha256`, `prompt_sha256`, `state`, and `version`.

- [ ] **Step 5: Implement transition table and authority guard as a pure function**

```python
_ALLOWED: dict[tuple[TaskState, TaskState], set[TransitionActor]] = {
    (TaskState.PENDING, TaskState.READY): {TransitionActor.SCHEDULER},
    (TaskState.READY, TaskState.ASSIGNED): {TransitionActor.ORCHESTRATOR},
    (TaskState.ASSIGNED, TaskState.SPAWNED): {TransitionActor.DISPATCHER},
    (TaskState.SPAWNED, TaskState.IN_PROGRESS): {TransitionActor.RUNTIME_MONITOR},
    (TaskState.IN_PROGRESS, TaskState.AUDIT_READY): {TransitionActor.RUNTIME_MONITOR},
    (TaskState.AUDIT_READY, TaskState.AUDITED): {TransitionActor.AUDITOR},
    (TaskState.AUDITED, TaskState.MERGING): {TransitionActor.MERGER},
    (TaskState.MERGING, TaskState.COMPLETED): {TransitionActor.MERGER},
}
```

Recovery and rejection transitions must be represented explicitly rather than as an unrestricted wildcard.

- [ ] **Step 6: Run model/FSM tests and mypy on models**

Run: `pytest tests/unit/test_models.py tests/unit/test_state_machine.py -q && mypy orch/models`

Expected: PASS.

- [ ] **Step 7: Commit Task 2**

```bash
git add orch/models tests/unit/test_models.py tests/unit/test_state_machine.py
git commit -m "feat: define strict orchestration domain models"
```

---

### Task 3: SQLite authoritative state store, schema migration, optimistic transitions, and event journal

**Files:**
- Create: `orch/core/__init__.py`
- Create: `orch/core/state.py`
- Create: `orch/core/observability.py`
- Create: `tests/unit/test_observability.py`
- Create: `tests/component/test_state_store.py`
- Create: `tests/adversarial/test_state_races.py`

**Interfaces:**
- Consumes: `TaskState`, `RunState`, `TransitionActor`, `TaskAttempt` from Task 2.
- Produces: `StateStore.open(path: Path)`, `StateStore.initialize()`, `transaction()`, `create_run(...)`, `create_task_attempt(...)`, `transition_task(...)`, `append_event(...)`, `get_attempt(...)`, `enter_safe_mode(...)`, plus `bind_log_context(...)`, `RedactingFormatter`, and `OperationalCounters`.

- [ ] **Step 1: Write a component test that initializes SQLite and verifies required pragmas/schema metadata**

```python
def test_state_store_initializes_required_pragmas(tmp_path: Path) -> None:
    store = StateStore.open(tmp_path / "state.db")
    store.initialize()
    assert store.scalar("PRAGMA journal_mode").lower() == "wal"
    assert store.scalar("PRAGMA foreign_keys") == 1
    assert store.schema_version() == 1
```

- [ ] **Step 2: Write a failing atomic transition/event test**

```python
def test_state_transition_and_event_commit_atomically(store: StateStore, attempt: TaskAttempt) -> None:
    store.create_task_attempt(attempt)
    updated = store.transition_task(
        attempt.attempt_id,
        expected_state=TaskState.PENDING,
        expected_version=0,
        to_state=TaskState.READY,
        actor=TransitionActor.SCHEDULER,
    )
    assert updated.state is TaskState.READY
    assert updated.version == 1
    events = store.events_for_attempt(attempt.attempt_id)
    assert events[-1].event_type == "TASK_STATE_CHANGED"
```

- [ ] **Step 3: Write the review-focus race test for two independent connections assigning the same READY task**

```python
def test_only_one_connection_can_claim_same_ready_attempt(state_db: Path, ready_attempt: TaskAttempt) -> None:
    first = StateStore.open(state_db)
    second = StateStore.open(state_db)
    winner = first.transition_task(
        ready_attempt.attempt_id,
        expected_state=TaskState.READY,
        expected_version=ready_attempt.version,
        to_state=TaskState.ASSIGNED,
        actor=TransitionActor.ORCHESTRATOR,
    )
    with pytest.raises(StateVersionConflict):
        second.transition_task(
            ready_attempt.attempt_id,
            expected_state=TaskState.READY,
            expected_version=ready_attempt.version,
            to_state=TaskState.ASSIGNED,
            actor=TransitionActor.ORCHESTRATOR,
        )
    assert winner.state is TaskState.ASSIGNED
```

- [ ] **Step 4: Run tests and verify they fail before `StateStore` exists**

Run: `pytest tests/component/test_state_store.py tests/adversarial/test_state_races.py -q`

Expected: FAIL on missing state store.

- [ ] **Step 5: Implement schema version 1 and explicit idempotent schema migration**

Create normalized tables required by the spec, including `runs`, `tasks`, `task_attempts`, `task_dependencies`, `agents`, `agent_processes`, `resource_locks`, `migration_allocators`, `migration_slots`, `port_allocations`, `worktrees`, `audit_reports`, `audit_evidence`, `merge_queue`, `merge_attempts`, `github_prs`, `ci_runs`, `events`, and `schema_meta`. Use foreign keys and unique constraints to make duplicate attempt/resource identities impossible.

- [ ] **Step 6: Implement transaction helpers and optimistic state/event mutation**

```python
@contextmanager
def transaction(self, *, immediate: bool = False) -> Iterator[sqlite3.Connection]:
    self._conn.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
    try:
        yield self._conn
    except BaseException:
        self._conn.rollback()
        raise
    else:
        self._conn.commit()
```

`transition_task()` must validate authority using Task 2, update `WHERE attempt_id=? AND state=? AND version=?`, append the event in the same transaction, and raise `StateVersionConflict` if the update count is zero.

- [ ] **Step 7: Add structured diagnostic logging/redaction and operational counters**

```python
def test_redacting_formatter_does_not_persist_known_secret() -> None:
    formatter = RedactingFormatter(secret_values={"super-secret"})
    record = logging.LogRecord("orch", logging.INFO, __file__, 1, "token=super-secret", (), None)
    assert "super-secret" not in formatter.format(record)


def test_operational_counters_increment_named_events() -> None:
    counters = OperationalCounters()
    counters.increment("tasks_started")
    assert counters.snapshot()["tasks_started"] == 1
```

Logs must carry run/task/attempt/component/event context where supplied and remain diagnostic only; `events` stays authoritative.

- [ ] **Step 8: Run component/adversarial state and observability tests and inspect DB integrity**

Run: `pytest tests/unit/test_observability.py tests/component/test_state_store.py tests/adversarial/test_state_races.py -q`

Expected: PASS with no duplicate assignments, an event for every successful mutation, secret redaction, and stable counters.

- [ ] **Step 9: Commit Task 3**

```bash
git add orch/core/state.py orch/core/observability.py tests/unit/test_observability.py tests/component/test_state_store.py tests/adversarial/test_state_races.py
git commit -m "feat: add transactional sqlite state and event store"
```

---

### Task 4: Plan parser, NetworkX DAG validation, waves, and dependency readiness

**Files:**
- Create: `orch/core/dag.py`
- Create: `tests/unit/test_dag.py`
- Create: `tests/fixtures/tasks_valid.yaml`
- Create: `tests/fixtures/tasks_cycle.yaml`

**Interfaces:**
- Consumes: `ProjectPlan`, `TaskSpec`, `TaskState` from Task 2.
- Produces: `load_plan(path: Path) -> ProjectPlan`, `DagPlan`, `DagPlan.validate() -> PlanValidationResult`, `execution_waves() -> list[list[str]]`, `dependencies_satisfied(task_id, states, policy) -> bool`.

- [ ] **Step 1: Write failing tests for cycle, missing dependency, self-dependency, and deterministic waves**

```python
def test_execution_waves_use_topological_generations() -> None:
    plan = ProjectPlan.model_validate({
        "version": 1,
        "project": {"name": "x"},
        "tasks": [task("A"), task("B"), task("C", deps=["A", "B"]), task("D", deps=["C"])],
    })
    dag = DagPlan.from_plan(plan)
    assert dag.execution_waves() == [["A", "B"], ["C"], ["D"]]


def test_cycle_reports_actual_cycle() -> None:
    dag = DagPlan.from_plan(plan_with_cycle("A", "B", "C"))
    result = dag.validate()
    assert result.ok is False
    assert result.cycles == [["A", "B", "C", "A"]]
```

- [ ] **Step 2: Write a failing readiness test proving worker exit is insufficient for default dependency policy**

```python
def test_integrated_completion_is_default_dependency_policy() -> None:
    dag = DagPlan.from_plan(plan_a_then_b())
    assert dag.dependencies_satisfied("B", {"A": TaskState.AUDIT_READY}) is False
    assert dag.dependencies_satisfied("B", {"A": TaskState.COMPLETED}) is True
```

- [ ] **Step 3: Run focused tests and verify failure**

Run: `pytest tests/unit/test_dag.py -q`

Expected: FAIL before DAG implementation.

- [ ] **Step 4: Implement YAML/JSON parsing and NetworkX graph construction**

Use `yaml.safe_load` for YAML and `json.loads` for JSON, then validate with `ProjectPlan`. Build `networkx.DiGraph` with dependency edges `dependency -> dependent`.

- [ ] **Step 5: Implement validation and deterministic wave ordering**

Use `nx.is_directed_acyclic_graph`, `nx.simple_cycles` only on invalid graphs, and `nx.topological_generations`. Sort task IDs within a generation for reproducible output.

- [ ] **Step 6: Implement dependency readiness policy**

Default policy requires every dependency attempt to be `COMPLETED`. Preserve an interface for explicit `audited` dependency requirements but do not weaken the default.

- [ ] **Step 7: Run tests and commit**

Run: `pytest tests/unit/test_dag.py -q`

```bash
git add orch/core/dag.py tests/unit/test_dag.py tests/fixtures/tasks_valid.yaml tests/fixtures/tasks_cycle.yaml
git commit -m "feat: add dag planning and readiness validation"
```

---

### Task 5: Path/resource locking, migration slots, ports, leases, and generation fencing

**Files:**
- Create: `orch/core/locks.py`
- Create: `tests/unit/test_path_overlap.py`
- Create: `tests/component/test_locks.py`
- Create: `tests/adversarial/test_lock_races.py`
- Create: `tests/adversarial/test_path_escape.py`

**Interfaces:**
- Consumes: `StateStore`, `TaskAttempt`, `ResourceRequest`, `LockMode`, `OrchConfig`.
- Produces: `normalize_repo_path(...)`, `classify_path_overlap(...)`, `LockManager.acquire_assignment(...)`, `renew_attempt_leases(...)`, `release_ephemeral_resources(...)`, `reserve_migration_slots(...)`, `allocate_ports(...)`.

- [ ] **Step 1: Write pure path tests for normalization, actual overlap, prefix overlap, ambiguity, traversal, and symlink escape**

```python
def test_nested_exclusive_prefixes_overlap(repo: Path) -> None:
    assert classify_path_overlap(repo, "src/backend/**", "src/backend/auth/**") is Overlap.PROVEN_OVERLAP


def test_ambiguous_exclusive_globs_fail_closed(repo: Path) -> None:
    assert classify_path_overlap(repo, "src/**/models/*.py", "src/auth/**/[a-z]*.py") is Overlap.AMBIGUOUS


def test_parent_traversal_is_rejected(repo: Path) -> None:
    with pytest.raises(PathOwnershipError):
        normalize_repo_path(repo, "../../outside")
```

Create a real symlink inside a temp repo that points outside and assert write ownership through it raises `PathOwnershipError`.

- [ ] **Step 2: Write transactional resource tests proving no partial allocation**

```python
def test_failed_multi_resource_assignment_rolls_back_every_reservation(lock_manager: LockManager) -> None:
    request = assignment_request(paths=["orch/core/**"], migration_count=1, ports={"api": 500})
    with pytest.raises(ResourceUnavailable):
        lock_manager.acquire_assignment(request)
    assert lock_manager.active_locks_for(request.attempt_id) == []
    assert lock_manager.migration_slots_for(request.attempt_id) == []
    assert lock_manager.ports_for(request.attempt_id) == []
```

- [ ] **Step 3: Write concurrency tests for unique migration/port allocation and same-task assignment races**

Use a `ThreadPoolExecutor` with independent SQLite connections to request 100 migration slots and a bounded port pool. Assert all issued migration slots are unique, no port is double-owned concurrently, and duplicate exclusive path writers yield exactly one winner.

- [ ] **Step 4: Write stale-generation renewal test**

```python
def test_stale_generation_cannot_renew_lock(lock_manager: LockManager, active_attempt: TaskAttempt) -> None:
    with pytest.raises(StaleGenerationError):
        lock_manager.renew_attempt_leases(active_attempt.attempt_id, generation=active_attempt.generation - 1)
```

- [ ] **Step 5: Run tests and verify failure**

Run: `pytest tests/unit/test_path_overlap.py tests/component/test_locks.py tests/adversarial/test_lock_races.py tests/adversarial/test_path_escape.py -q`

Expected: FAIL before lock manager exists.

- [ ] **Step 6: Implement path canonicalization and overlap classification**

Normalize separators, reject `..` escape, resolve literal paths against repo root, detect symlink escape, compare current inventory matches, derive literal glob prefixes, and return `PROVEN_DISJOINT`, `PROVEN_OVERLAP`, or `AMBIGUOUS`. Production acquisition treats ambiguous exclusive writers as conflict.

- [ ] **Step 7: Implement atomic assignment acquisition under one `BEGIN IMMEDIATE` transaction**

Deterministically sort resource keys by type/key, verify current attempt generation/state, insert path leases, issue monotonic migration slots, allocate named-pool ports, create assignment metadata, and transition `READY -> ASSIGNED` in the same transaction/event boundary where possible.

- [ ] **Step 8: Implement lease renewal/reclaim policy and resource lifetime split**

Path write ownership remains until completion/rejection/remediation transfer. Ports can be released only after the owning process is proven gone. Migration identities are never reused for another attempt.

- [ ] **Step 9: Run resource tests and commit**

Run: `pytest tests/unit/test_path_overlap.py tests/component/test_locks.py tests/adversarial/test_lock_races.py tests/adversarial/test_path_escape.py -q`

```bash
git add orch/core/locks.py tests/unit/test_path_overlap.py tests/component/test_locks.py tests/adversarial/test_lock_races.py tests/adversarial/test_path_escape.py
git commit -m "feat: add transactional resource locking and allocators"
```

---

### Task 6: Safe Git primitives, worktree lifecycle, and isolated runtime environment

**Files:**
- Create: `orch/core/git.py`
- Create: `orch/core/worktree.py`
- Create: `orch/core/environment.py`
- Create: `tests/component/test_git.py`
- Create: `tests/component/test_worktree.py`
- Create: `tests/unit/test_environment.py`

**Interfaces:**
- Consumes: `TaskAttempt`, `StateStore`, `GitConfig`, lock ownership from Task 5.
- Produces: `GitRunner.run(argv, cwd)`, `GitRepository`, `WorktreeManager.create(...)`, `inspect(...)`, `remove(...)`, `RuntimeEnvironmentBuilder.build(attempt) -> RuntimeEnvironment`.

- [ ] **Step 1: Write real-Git tests for repository identity and exact-SHA worktree creation**

Initialize a temp Git repo with one commit, resolve `base_sha`, create an attempt worktree, and assert actual branch/HEAD/path exactly match expected values.

```python
def test_worktree_is_created_from_exact_base_sha(repo: GitTestRepo, manager: WorktreeManager) -> None:
    workspace = manager.create(attempt_for(repo.base_sha))
    assert repo.git("-C", str(workspace.path), "rev-parse", "HEAD").stdout.strip() == repo.base_sha
    assert workspace.branch.startswith("orch/")
```

- [ ] **Step 2: Write safety tests for protected branches, arbitrary worktree removal, and dirty inspection**

Assert create/spawn refuses a protected branch, `remove()` refuses paths outside configured `.worktrees`, and `inspect()` reports dirty/untracked state accurately.

- [ ] **Step 3: Write environment isolation tests**

```python
def test_runtime_environment_is_attempt_scoped(tmp_path: Path) -> None:
    env = RuntimeEnvironmentBuilder(tmp_path).build(attempt("ATT-1"))
    assert env.env["ORCH_ATTEMPT_ID"] == "ATT-1"
    assert Path(env.env["TMPDIR"]).is_relative_to(tmp_path / ".orch" / "runtime" / "ATT-1")
    assert env.env["COVERAGE_FILE"].endswith("ATT-1/coverage")
```

Also assert secrets are not copied into the worktree and only allowlisted env keys pass through.

- [ ] **Step 4: Run tests and verify failure**

Run: `pytest tests/component/test_git.py tests/component/test_worktree.py tests/unit/test_environment.py -q`

Expected: FAIL before Git/worktree/environment implementation.

- [ ] **Step 5: Implement argv-only Git runner and repository helpers**

Use `subprocess.run([...], shell=False, text=True, capture_output=True, check=False)` and typed results. Implement helpers for root, branch, HEAD, status porcelain, worktree list, merge-base, diff name-status, parents, and clean-tree checks.

- [ ] **Step 6: Implement journaled worktree create/inspect/remove**

Create a durable worktree intent before `git worktree add -b <branch> <path> <base_sha>`, verify branch/HEAD afterward, and record `READY`. Remove only known engine worktrees after liveness/recovery preconditions.

- [ ] **Step 7: Implement isolated runtime directories/environment**

Create `.orch/runtime/<attempt>/tmp`, `home`, `cache`, `state`, `artifacts`; set `TMPDIR/TEMP/TMP`, `XDG_CACHE_HOME`, `XDG_STATE_HOME`, `COVERAGE_FILE`, `PYTHONPYCACHEPREFIX`, and declared ecosystem overrides. Apply explicit env allowlist and log-redaction inputs.

- [ ] **Step 8: Run tests and commit**

Run: `pytest tests/component/test_git.py tests/component/test_worktree.py tests/unit/test_environment.py -q`

```bash
git add orch/core/git.py orch/core/worktree.py orch/core/environment.py tests/component/test_git.py tests/component/test_worktree.py tests/unit/test_environment.py
git commit -m "feat: add isolated git worktree execution environments"
```

---

### Task 7: Harness protocol, capability discovery, async process supervision, and fake agent fixture

**Files:**
- Create: `orch/core/process.py`
- Create: `orch/core/harness/__init__.py`
- Create: `orch/core/harness/base.py`
- Create: `orch/core/harness/discovery.py`
- Create: `orch/core/harness/generic_cli.py`
- Create: `orch/core/harness/claude_code.py`
- Create: `orch/core/harness/gemini_cli.py`
- Create: `orch/core/harness/antigravity.py`
- Create: `orch/core/harness/aider.py`
- Create: `tests/fixtures/fake_agent.py`
- Create: `tests/unit/test_harness_discovery.py`
- Create: `tests/component/test_process_supervisor.py`
- Create: `tests/component/test_generic_harness.py`

**Interfaces:**
- Consumes: `RuntimeEnvironment`, `TaskAttempt`, harness config.
- Produces: `HarnessAdapter` protocol, `HarnessCapabilities`, `PreparedExecution`, `ProcessSupervisor.spawn_and_wait(...)`, `ExecutionResult`.

- [ ] **Step 1: Write discovery tests that distinguish unavailable binaries from supported capabilities**

Monkeypatch executable lookup/version output. Assert missing Antigravity/Claude/Gemini/Aider returns `available=False` rather than fabricated support.

- [ ] **Step 2: Create a deterministic fake agent fixture with explicit behaviors**

`tests/fixtures/fake_agent.py` accepts argv such as `--behavior success|crash|sleep|dirty|scope|secret` and writes deterministic files/commits only when requested by the test. It must require no network or model provider.

- [ ] **Step 3: Write async supervisor tests for streaming logs, redaction, exit code, timeout ladder, and forced termination**

```python
@pytest.mark.asyncio
async def test_supervisor_captures_stdout_stderr_and_exit_code(supervisor: ProcessSupervisor) -> None:
    result = await supervisor.spawn_and_wait(fake_agent("crash"))
    assert result.exit_code == 17
    assert result.stdout_path.read_text()
    assert result.stderr_path.read_text()
```

Add a test where the process exceeds hard timeout and confirm termination reason is `TIMEOUT` with final logs persisted. Add a fake-agent line containing an injected secret value and assert stdout/stderr/transcript persistence contains the redacted marker instead of the raw secret.

- [ ] **Step 4: Write generic CLI tests for stdin and `{prompt}` argument delivery without `shell=True`**

Assert argv boundaries preserve shell-injection-shaped prompt text as one argument/stdin payload rather than executing it.

- [ ] **Step 5: Run tests and verify failure**

Run: `pytest tests/unit/test_harness_discovery.py tests/component/test_process_supervisor.py tests/component/test_generic_harness.py -q`

Expected: FAIL before harness/process implementation.

- [ ] **Step 6: Implement harness protocol and discovery helpers**

```python
class HarnessAdapter(Protocol):
    name: str
    async def discover(self) -> HarnessCapabilities: ...
    async def prepare(self, ctx: ExecutionContext) -> PreparedExecution: ...
    async def spawn(self, prepared: PreparedExecution) -> ProcessHandle: ...
    async def wait(self, handle: ProcessHandle) -> ExecutionResult: ...
    async def interrupt(self, handle: ProcessHandle) -> None: ...
    async def terminate(self, handle: ProcessHandle) -> None: ...
    async def health(self, handle: ProcessHandle) -> ProcessHealth: ...
```

- [ ] **Step 7: Implement async process supervisor with independent stdout/stderr pumps**

Use `asyncio.create_subprocess_exec`, `asyncio.TaskGroup`, append-only `events.jsonl`, attempt-scoped stdout/stderr files, `RedactingFormatter`/stream redaction before durable persistence, graceful terminate-then-kill, and process identity metadata including PID, spawn time, command fingerprint, host ID, attempt ID, and generation.

- [ ] **Step 8: Implement vendor adapters as thin command builders over the shared supervisor**

Each adapter must discover executable/version at runtime and fail closed when its required headless/prompt mode cannot be demonstrated. No adapter may mutate orchestration state directly.

- [ ] **Step 9: Run harness/process tests and commit**

Run: `pytest tests/unit/test_harness_discovery.py tests/component/test_process_supervisor.py tests/component/test_generic_harness.py -q`

```bash
git add orch/core/process.py orch/core/harness tests/fixtures/fake_agent.py tests/unit/test_harness_discovery.py tests/component/test_process_supervisor.py tests/component/test_generic_harness.py
git commit -m "feat: add harness adapters and async process supervision"
```

---

### Task 8: Orchestrator assignment, prompt envelope, concurrent spawn, candidate validation, and freeze

**Files:**
- Create: `orch/core/orchestrator.py`
- Create: `tests/integration/test_orchestrator_spawn.py`
- Create: `tests/adversarial/test_candidate_freeze.py`

**Interfaces:**
- Consumes: `StateStore`, `DagPlan`, `LockManager`, `WorktreeManager`, `RuntimeEnvironmentBuilder`, harness registry, `ProcessSupervisor`.
- Produces: `Orchestrator.open(repo_path)`, `activate_plan(...)`, `spawn_task(task_id)`, `spawn_wave(wave_id)`, `compile_prompt(...)`, `finalize_worker_result(...)`.

- [ ] **Step 1: Write an integration test for READY -> ASSIGNED -> SPAWNED -> IN_PROGRESS using fake agent**

Create a real temp repo and state DB, activate one task, run the fake agent, and assert every state transition/event occurs in order while the process runs only in its worktree.

- [ ] **Step 2: Write prompt-envelope evidence test**

Assert compiled prompt contains run/task/attempt/generation, exact worktree, base SHA, allowed/read-only/forbidden paths, allocated ports/migration slots, acceptance criteria, and explicit text that the worker cannot mark the task audited/completed. Assert prompt/task hashes are persisted before spawn.

- [ ] **Step 3: Write `spawn_wave` bounded-concurrency test**

Use four independent fake tasks with `max_parallel_agents=2`; instrument fake agents with a barrier and assert no more than two are concurrently alive, while waiting tasks remain READY rather than failed.

- [ ] **Step 4: Write review-focus candidate tests: exit 0 + dirty tree, untracked file, no-op without permission, and stale generation**

```python
@pytest.mark.asyncio
async def test_exit_zero_with_dirty_tree_does_not_become_audit_ready(orchestrator: Orchestrator) -> None:
    result = await orchestrator.spawn_task("TASK-DIRTY")
    assert result.process.exit_code == 0
    assert orchestrator.current_attempt("TASK-DIRTY").state is TaskState.RECOVERING
```

Add an explicit stale-generation completion callback and assert it cannot transition state or renew locks.

- [ ] **Step 5: Run integration/adversarial tests and verify failure**

Run: `pytest tests/integration/test_orchestrator_spawn.py tests/adversarial/test_candidate_freeze.py -q`

Expected: FAIL before orchestrator exists.

- [ ] **Step 6: Implement prompt compilation and immutable prompt evidence**

Persist `.orch/prompts/<task>/<attempt>/system.txt`, `task.txt`, `manifest.json` with SHA-256 hashes and adapter/version metadata.

- [ ] **Step 7: Implement spawn lifecycle with atomic assignment before physical side effects**

Perform preflight, resource assignment, exact-base worktree provisioning, runtime env creation, harness capability verification, prompt compilation, process spawn, process identity persistence, and legal FSM transitions. Journal external side effects so restart recovery can reconcile worktree/process existence.

- [ ] **Step 8: Implement candidate validation/freeze**

Require branch correctness, readable HEAD, clean tree, no untracked files, `HEAD != base_sha` unless `allow_noop`, and current generation. Persist head/tree identity, stop write authority, mark worktree `AUDIT_FROZEN`, then transition to `AUDIT_READY`.

- [ ] **Step 9: Run tests and commit**

Run: `pytest tests/integration/test_orchestrator_spawn.py tests/adversarial/test_candidate_freeze.py -q`

```bash
git add orch/core/orchestrator.py tests/integration/test_orchestrator_spawn.py tests/adversarial/test_candidate_freeze.py
git commit -m "feat: orchestrate concurrent isolated worker attempts"
```

---

### Task 9: Seven-gate forensic audit, evidence store, secret scanning, and cryptographic certificate

**Files:**
- Create: `orch/core/regression.py`
- Create: `orch/core/audit.py`
- Create: `tests/unit/test_audit_hashing.py`
- Create: `tests/component/test_audit_runner.py`
- Create: `tests/adversarial/test_audit_mutation.py`
- Create: `tests/adversarial/test_scope_and_secrets.py`

**Interfaces:**
- Consumes: frozen `TaskAttempt`, `TaskSpec`, `GitRepository`, `StateStore`.
- Produces: `VerificationRunner.run(CommandSpec)`, `AuditRunner.run(attempt_id) -> AuditReport`, `canonical_certificate_bytes(...)`, `verify_certificate(...)`.

- [ ] **Step 1: Write deterministic canonical JSON/certificate hash tests**

```python
def test_certificate_hash_is_independent_of_pretty_printing(certificate_payload: dict[str, object]) -> None:
    first = certificate_digest(certificate_payload)
    second = certificate_digest(json.loads(json.dumps(certificate_payload, indent=8)))
    assert first == second
```

Ensure the digest excludes its own `certificate_sha256` field to avoid self-reference.

- [ ] **Step 2: Write Gate 1/2 component tests for wrong HEAD, dirty tree, rename destination violation, and unauthorized changed file**

Use real Git commits/diffs. Assert wrong candidate identity is fail-fast and forbidden path changes produce `SCOPE_EXPANSION_VIOLATION`.

- [ ] **Step 3: Write Gate 3 verification tests using argv commands and timeout evidence**

Assert required command exit 0 passes, exit nonzero fails, timeout records `termination_reason=TIMEOUT`, and shell-shaped strings are not interpreted unless `shell=true` was explicitly allowed by policy.

- [ ] **Step 4: Write Gate 4 secret tests**

Commit a fake private-key header and token-shaped secret and assert violation. Add a fingerprinted allowlist fixture for a documented fake credential and assert only the exact allowed fingerprint is suppressed.

- [ ] **Step 5: Write baseline-aware Gate 3 plus Gate 5/6 acceptance/artifact tests**

First prove baseline-aware verification classifies `NEW_FAILURE`, `BASELINE_FAILURE`, `FIXED_BASELINE_FAILURE`, and `UNCHANGED_FAILURE` without treating an unchanged baseline failure as a newly introduced regression. The project policy may still require exit code 0. Then define criteria with `test`, `file_exists`, `file_matches`, `json_schema`, and `manual_review`; an unresolved required manual review is UNKNOWN and must never auto-pass. Missing required artifact must yield FAIL/UNKNOWN according to the evidence condition and block sign-off.

- [ ] **Step 6: Write candidate-mutation-during-audit adversarial test**

Mutate HEAD between Gate 3 and Gate 4 through a test hook; assert audit aborts with `CANDIDATE_MUTATED_DURING_AUDIT` and never emits a PASS certificate.

- [ ] **Step 7: Run audit tests and verify failure**

Run: `pytest tests/unit/test_audit_hashing.py tests/component/test_audit_runner.py tests/adversarial/test_audit_mutation.py tests/adversarial/test_scope_and_secrets.py -q`

Expected: FAIL before audit implementation.

- [ ] **Step 8: Implement reusable verification command evidence runner**

Record argv, cwd, exit code, stdout/stderr files and hashes, duration, timeout/termination, and environment fingerprint without storing plaintext secrets.

- [ ] **Step 9: Implement seven ordered gates with fail-fast only for identity corruption**

Gate 1 Git identity/workspace integrity; Gate 2 scope/diff/destructive changes; Gate 3 independent tests/static commands with optional baseline comparison; Gate 4 secret scan; Gate 5 acceptance criteria including unresolved manual-review handling; Gate 6 artifacts/contracts; Gate 7 sign-off. Collect multiple findings when candidate identity remains trustworthy.

- [ ] **Step 10: Persist evidence manifest, audit report, and certificate atomically with state transition**

Write evidence under `.orch/audits/<task>/<attempt>/<audit>/`, hash evidence files, canonicalize certificate payload, persist DB rows, then transition `AUDIT_READY -> AUDITED` only if every required gate is PASS and HEAD/fingerprint still match.

- [ ] **Step 11: Run audit tests and commit**

Run: `pytest tests/unit/test_audit_hashing.py tests/component/test_audit_runner.py tests/adversarial/test_audit_mutation.py tests/adversarial/test_scope_and_secrets.py -q`

```bash
git add orch/core/regression.py orch/core/audit.py tests/unit/test_audit_hashing.py tests/component/test_audit_runner.py tests/adversarial/test_audit_mutation.py tests/adversarial/test_scope_and_secrets.py
git commit -m "feat: add zero-trust forensic audit certificates"
```

---

### Task 10: Integration worktree, deterministic merge queue, regression, rollback, and certificate revalidation

**Files:**
- Create: `orch/core/integration.py`
- Create: `orch/core/merger.py`
- Create: `tests/component/test_merger.py`
- Create: `tests/adversarial/test_merge_drift.py`
- Create: `tests/adversarial/test_merge_rollback.py`
- Create: `tests/integration/test_final_run_verification.py`

**Interfaces:**
- Consumes: `StateStore`, `GitRepository`, `AuditCertificate`, `LockManager`, `VerificationRunner`, DAG dependency rank.
- Produces: `IntegrationManager`, `MergeController.enqueue_audited(...)`, `dry_run()`, `merge_sequential()`, `verify_final_run()`, `promote_if_policy_allows()`, `MergeResult`.

- [ ] **Step 1: Write deterministic queue ordering tests**

Given tasks with dependency ranks, priorities, audit times, and IDs, assert queue order is dependency rank -> priority -> audited_at -> task_id and never schedules a dependent before prerequisites.

- [ ] **Step 2: Write review-focus tests for stale certificate and external integration drift**

```python
def test_merge_rejects_candidate_when_head_no_longer_matches_certificate(...):
    mutate_candidate_after_audit()
    with pytest.raises(AuditCertificateStale):
        merger.merge_sequential()


def test_merge_rejects_when_integration_head_moved_externally(...):
    move_integration_branch()
    with pytest.raises(IntegrationBranchDrift):
        merger.merge_sequential()
```

- [ ] **Step 3: Write real-Git clean merge and conflict tests**

Assert `git merge --no-ff` produces a merge commit for a clean branch. For conflicting edits, assert engine captures conflicted paths, calls merge abort, and restores exact pre-merge SHA with clean status.

- [ ] **Step 4: Write regression-failure rollback test**

Create a candidate that merges cleanly but causes configured regression command failure. Assert integration HEAD is reset to the persisted `integration_before_sha`, tree is clean, and task does not become COMPLETED.

- [ ] **Step 5: Write final run verification/state tests**

After the queue is empty, assert configured final commands run on the integrated tree. A local-only successful policy advances `INTEGRATING -> VERIFYING -> READY_FOR_PROMOTION` and may promote/complete according to configured local promotion policy; a failing final command sets the run to FAILED and never reports completion. If GitHub CI is required, the run must remain VERIFYING until Task 11 supplies exact-SHA remote evidence.

- [ ] **Step 6: Run merge tests and verify failure**

Run: `pytest tests/component/test_merger.py tests/adversarial/test_merge_drift.py tests/adversarial/test_merge_rollback.py tests/integration/test_final_run_verification.py -q`

Expected: FAIL before merge engine exists.

- [ ] **Step 7: Implement integration worktree ownership and exact-SHA verification**

Provision `.worktrees/integration/<run-id>` or configured root, acquire an exclusive `INTEGRATION_BRANCH:<branch>` lock, and persist expected integration SHA before every mutation.

- [ ] **Step 8: Implement certificate revalidation and deterministic queue processing**

Before Git mutation verify candidate HEAD, audit digest, task spec hash, ownership hash, acceptance hash, evidence manifest hash, and expected integration SHA.

- [ ] **Step 9: Implement merge journal, regression, rollback, and completion transition**

Persist `MERGE_PREPARED`, execute no-ff merge, record merge commit, run regression, then either persist success and `MERGING -> COMPLETED` or restore exact pre-merge SHA and persist rollback evidence. Failure to verify rollback enters safe mode.

- [ ] **Step 10: Implement final run verification and local promotion gate**

After per-merge regression and queue exhaustion, run configured final verification on the integration worktree, persist run-level evidence/state, and only promote/complete when active policy requirements are proven. Keep remote-CI-required runs in `VERIFYING` for Task 11.

- [ ] **Step 11: Run merge tests and commit**

Run: `pytest tests/component/test_merger.py tests/adversarial/test_merge_drift.py tests/adversarial/test_merge_rollback.py tests/integration/test_final_run_verification.py -q`

```bash
git add orch/core/integration.py orch/core/merger.py tests/component/test_merger.py tests/adversarial/test_merge_drift.py tests/adversarial/test_merge_rollback.py tests/integration/test_final_run_verification.py
git commit -m "feat: add sequential audited integration and rollback"
```

---

### Task 11: GitHub CLI bridge, idempotent PRs, and exact-SHA CI monitoring

**Files:**
- Create: `orch/core/github.py`
- Create: `tests/unit/test_github_client.py`
- Create: `tests/component/test_github_cli.py`

**Interfaces:**
- Consumes: audited/merged refs and certificates, GitHub config, `StateStore`.
- Produces: `GitHubClient.discover()`, `push_candidate(...)`, `create_or_get_pr(...)`, `required_ci_status(...)`, `watch_ci(...)`.

- [ ] **Step 1: Write capability/auth discovery tests from structured fake `gh` responses**

Assert missing binary -> `GITHUB_CLI_UNAVAILABLE`, failed auth -> `GITHUB_AUTH_UNAVAILABLE`, and local orchestration remains usable when GitHub is disabled.

- [ ] **Step 2: Write PR idempotency test**

Call `create_or_get_pr()` twice for the same exact head branch/SHA and assert only one `gh pr create` invocation occurs; second call reuses verified existing PR metadata.

- [ ] **Step 3: Write exact-SHA CI binding tests**

Feed runs/checks where the newest run belongs to the wrong SHA and assert it is ignored. Required checks must all terminate PASS for the expected SHA; missing required checks remain pending/unknown rather than green.

- [ ] **Step 4: Write safe push divergence tests**

Assert remote branch with unexpected SHA blocks a normal push and the client never uses `--force`; explicit remediation may use `--force-with-lease` only with known expected remote SHA.

- [ ] **Step 5: Run tests and verify failure**

Run: `pytest tests/unit/test_github_client.py tests/component/test_github_cli.py -q`

Expected: FAIL before GitHub client exists.

- [ ] **Step 6: Implement argv-based `gh` wrapper with JSON parsing into Pydantic models**

Prefer `--json` for PR/run/check queries. Persist PR and CI records with repo, branch, head SHA, PR number, run IDs, conclusions, and timestamps.

- [ ] **Step 7: Implement PR body rendering from canonical task/audit data**

Include task scope, acceptance checklist, candidate base/head, verification results, audit ID/certificate digest, changed-file summary, and a machine-readable marker comment.

- [ ] **Step 8: Bind remote CI policy to run-level VERIFYING/completion state**

When GitHub CI is required, keep the run in `VERIFYING` until every configured required check for the exact integration/candidate SHA is PASS. Failure/cancel/timeout yields FAILED or policy-specific non-complete status; only proven remote success permits promotion/completion.

- [ ] **Step 9: Run tests and commit**

Run: `pytest tests/unit/test_github_client.py tests/component/test_github_cli.py -q`

```bash
git add orch/core/github.py tests/unit/test_github_client.py tests/component/test_github_cli.py
git commit -m "feat: add github pr and exact-sha ci lifecycle"
```

---

### Task 12: Recovery reconciliation, evidence bundles, deadlock handling, and safe mode

**Files:**
- Create: `orch/core/recovery.py`
- Create: `tests/component/test_recovery.py`
- Create: `tests/adversarial/test_zombie_recovery.py`
- Create: `tests/adversarial/test_merge_crash_recovery.py`
- Create: `tests/adversarial/test_unknown_recovery.py`

**Interfaces:**
- Consumes: `StateStore`, Git/worktree/process inspection, lock state, merge journal.
- Produces: `RecoveryController.scan()`, `plan()`, `apply()`, `recover_dangling()`, `RecoveryBundle`, `enter_safe_mode(...)`.

- [ ] **Step 1: Write dead-process + dirty-worktree recovery test**

DB says IN_PROGRESS, PID is absent, worktree is dirty. Assert recovery creates `.orch/recovery/<task>/<attempt>/metadata.json`, `git-status.txt`, `diff.patch`, `untracked-manifest.json`, `head.txt`, and transcript tail before any destructive cleanup or lease reclamation.

- [ ] **Step 2: Write zombie generation test**

After recovery creates generation N+1, send a completion/heartbeat/renewal from generation N and assert every operation is rejected and canonical state remains unchanged.

- [ ] **Step 3: Write review-focus crash-after-merge-before-DB-finalization test**

Create merge journal with `integration_before=AAA`, `candidate=BBB`, physically create merge commit `CCC` with parents `AAA` and `BBB`, but omit final DB event. On restart, recovery must identify `CCC` as the expected merge and resume regression/finalization; if parent identity does not match, enter safe mode.

- [ ] **Step 4: Write unknown-process-ownership and unknown-worktree tests**

Assert recovery never kills an unprovable PID and never force-removes a worktree outside configured engine namespace; classify as `UNKNOWN` and block unsafe mutation.

- [ ] **Step 5: Write logical wait-for cycle test**

Build A -> R1 -> B -> R2 -> A and assert victim selection is deterministic: unspawned first, then lower priority, then newest assignment. Release only reservation safe to revoke.

- [ ] **Step 6: Run recovery tests and verify failure**

Run: `pytest tests/component/test_recovery.py tests/adversarial/test_zombie_recovery.py tests/adversarial/test_merge_crash_recovery.py tests/adversarial/test_unknown_recovery.py -q`

Expected: FAIL before recovery controller exists.

- [ ] **Step 7: Implement scan/classify/plan/apply/reconcile/verify pipeline**

Reconcile SQLite desired state with Git worktree/branch/HEAD state, OS process liveness, resource leases, and merge journal. Produce typed classifications from the spec and never make a destructive change from an `UNKNOWN` classification.

- [ ] **Step 8: Implement recovery bundle creation and generation invalidation before cleanup**

Persist bundle hashes/metadata and recovery events. Reclaim leases only after process ownership/liveness proof. Transfer long-lived path ownership to remediation generation rather than opening an unsafe gap.

- [ ] **Step 9: Implement global safe mode gate**

Persist run `SAFE_MODE` with reason/evidence. Orchestrator/merger/resource mutation paths must refuse new unsafe work while status/audit-inspection/recovery scan remain available.

- [ ] **Step 10: Run tests and commit**

Run: `pytest tests/component/test_recovery.py tests/adversarial/test_zombie_recovery.py tests/adversarial/test_merge_crash_recovery.py tests/adversarial/test_unknown_recovery.py -q`

```bash
git add orch/core/recovery.py tests/component/test_recovery.py tests/adversarial/test_zombie_recovery.py tests/adversarial/test_merge_crash_recovery.py tests/adversarial/test_unknown_recovery.py
git commit -m "feat: add evidence-preserving recovery and safe mode"
```

---

### Task 13: Complete Typer CLI surface, JSON results, status, doctor, and logs

**Files:**
- Create: `orch/cli/init_cmd.py`
- Create: `orch/cli/plan_cmd.py`
- Create: `orch/cli/spawn_cmd.py`
- Create: `orch/cli/lock_cmd.py`
- Create: `orch/cli/audit_cmd.py`
- Create: `orch/cli/merge_cmd.py`
- Create: `orch/cli/pr_cmd.py`
- Create: `orch/cli/recover_cmd.py`
- Create: `orch/cli/doctor_cmd.py`
- Create: `orch/cli/logs_cmd.py`
- Modify: `orch/cli/main.py`
- Create: `tests/integration/test_cli.py`
- Create: `tests/integration/test_doctor.py`

**Interfaces:**
- Consumes: core services from Tasks 1–12.
- Produces: required CLI contract, Rich rendering, versioned `--json` results, stable exit-code behavior.

- [ ] **Step 1: Write CLI registration tests for every required command**

Use `typer.testing.CliRunner` and assert help contains `init`, `plan validate`, `plan status`, `spawn`, `lock list`, `audit run`, `merge sequential`, `pr create-all`, `pr watch-ci`, `recover --dangling`, `doctor`, `logs`, and `version`.

- [ ] **Step 2: Write `orch init` idempotency test**

Run twice in a temp Git repo. Assert `.orch/state.db`, `.orch/config.yaml`, runtime directories, schema version, and gitignore entries exist; second run preserves existing config unless `--force`.

- [ ] **Step 3: Write `plan validate` read-only vs `--activate` test**

Plain validate must not create a run/task rows. `--activate` must hash the plan and persist a new run/tasks/dependencies.

- [ ] **Step 4: Write `--json` schema and exit-code tests**

For a passing and failing audit/plan, parse stdout JSON and assert `schema_version`, `command`, `success`, identifiers, and stable process exit code; tests must not parse Rich output.

- [ ] **Step 5: Write doctor tests for required vs optional harness capabilities**

Missing optional Antigravity should render warning but exit zero when inactive. Missing Git or a harness required by the active plan must fail with the appropriate exit code.

- [ ] **Step 6: Write logs tests for current attempt, `--attempt`, `--stderr`, and `--tail`**

Use fixture log files and ensure CLI resolves internal attempt path without user knowledge of `.orch/logs` layout.

- [ ] **Step 7: Run CLI tests and verify failure**

Run: `pytest tests/integration/test_cli.py tests/integration/test_doctor.py -q`

Expected: FAIL until subcommands are registered.

- [ ] **Step 8: Implement thin commands only**

Each command loads config/repo context, invokes a typed core service, renders a Rich result, optionally serializes a versioned result model, and translates typed `OrchError.exit_code` into `typer.Exit`. Do not put SQL/Git/process lifecycle logic in CLI modules.

- [ ] **Step 9: Implement `plan status` Rich table from canonical state**

Show task, state, adapter/agent, attempt, active lock count, and health. JSON mode returns the same facts in a stable model.

- [ ] **Step 10: Run CLI tests and commit**

Run: `pytest tests/integration/test_cli.py tests/integration/test_doctor.py -q && python -m orch.cli.main --help`

```bash
git add orch/cli tests/integration/test_cli.py tests/integration/test_doctor.py
git commit -m "feat: expose complete orch command suite"
```

---

### Task 14: Adversarial concurrency, crash injection, full local E2E, documentation, and package verification

**Files:**
- Create: `tests/adversarial/test_concurrency_stress.py`
- Create: `tests/adversarial/test_security_inputs.py`
- Create: `tests/adversarial/test_crash_injection.py`
- Create: `tests/e2e/test_local_lifecycle.py`
- Create: `tasks.example.yaml`
- Modify: `README.md`
- Modify: `pyproject.toml`

**Interfaces:**
- Consumes: complete engine/CLI from Tasks 1–13.
- Produces: release-grade local proof that the full lifecycle and documented limitations match the spec.

- [ ] **Step 1: Add concurrency stress tests for 100 competing allocations**

Use independent state connections and concurrent workers. Assert no duplicate exclusive path leases, migration slots, or concurrently-owned ports; DB integrity check must succeed afterward.

- [ ] **Step 2: Add security-shaped input tests**

Cover malicious task IDs/branch names containing `../`, symlink escape, shell-injection-shaped command args, broad secret-scan suppression, unknown worktree force-delete attempt, arbitrary force-push request, protected integration-branch worker spawn, stale certificate SHA, and stale generation mutation.

- [ ] **Step 3: Add test-only crash injection hooks around required windows**

Support deterministic injected failures at `AFTER_LOCK_COMMIT`, `AFTER_WORKTREE_CREATE`, `AFTER_PROCESS_SPAWN`, `AFTER_GIT_MERGE`, and `BEFORE_MERGE_DB_COMMIT`. For each, restart a fresh `Orchestrator.open()` and assert recovery either reconciles to a proven state or enters safe mode.

- [ ] **Step 4: Write full local E2E using only fake agents**

The test must execute this real lifecycle in a temporary repo:

```text
orch init
-> plan validate --activate
-> spawn --wave 0 with concurrent fake workers
-> candidate freeze
-> audit run for each task
-> merge sequential
-> final regression
-> run COMPLETED
```

Assert all tasks reach COMPLETED, run reaches COMPLETED, evidence/certificates exist, integration history contains merge provenance, and working trees are clean.

- [ ] **Step 5: Run adversarial/E2E tests and fix any invariant failures before documentation**

Run: `pytest tests/adversarial tests/e2e -q`

Expected: PASS before proceeding.

- [ ] **Step 6: Write `tasks.example.yaml` with one parallel wave and one dependent task**

Include explicit ownership, resources, harness selection, acceptance criteria, verification commands, migration/port examples, and no secret values.

- [ ] **Step 7: Complete README with truthful setup, architecture, CLI examples, recovery, security model, and limitations**

Document that native CLI agents are not syscall-sandboxed by Python alone; GitHub is optional unless policy requires CI; vendor adapter availability is runtime-discovered; worker prose is never authoritative evidence.

- [ ] **Step 8: Run the complete verification matrix**

Run all commands fresh:

```bash
pytest -q
mypy orch
ruff check .
python -m build
python -m orch.cli.main --help
```

Then create a clean temporary virtual environment, install the built wheel, and run:

```bash
orch --help
orch version
```

Finally run the local E2E test alone once more:

```bash
pytest tests/e2e/test_local_lifecycle.py -q
```

Expected: every command exits 0.

- [ ] **Step 9: Inspect repository status and diff for unintended files/secrets**

Run:

```bash
git status --short
git diff --check
git diff --stat HEAD~1..HEAD
```

Also run the engine's own secret/audit path against its repository if available by this stage. Any unexpected generated/runtime file must be removed or intentionally ignored before final commit.

- [ ] **Step 10: Commit Task 14**

```bash
git add README.md tasks.example.yaml pyproject.toml tests/adversarial tests/e2e
git commit -m "test: verify orch engine end to end"
```

---

## Final Whole-Branch Review Checklist

Before calling the implementation ready for delivery, the executor and final reviewer must verify all of the following against the approved spec, not merely against task-local tests:

- [ ] Package installs under Python 3.12+ and exposes `orch`.
- [ ] Unknown config/task fields are rejected.
- [ ] FSM authority prevents worker self-completion.
- [ ] SQLite mutations and events commit atomically; external side effects are journaled/reconciled.
- [ ] DAG cycles/missing dependencies/self-dependencies are rejected and waves are deterministic.
- [ ] Exclusive path overlap, traversal, symlink escape, duplicate migration slots, and concurrent port ownership are prevented.
- [ ] Worktrees are attempt-scoped and exact-base-SHA verified.
- [ ] Harnesses are capability-discovered, process logs are attempt-scoped, and shell injection is not introduced by command construction.
- [ ] `spawn --wave` honors bounded concurrency and resource gates.
- [ ] Dirty/untracked/no-op/stale candidates cannot become `AUDIT_READY` incorrectly.
- [ ] All seven audit gates run independently and certificate hashing is deterministic/exact-SHA bound.
- [ ] Candidate mutation or audit input drift invalidates merge eligibility.
- [ ] Integration is exclusive/sequential, conflicts abort cleanly, regression failures restore exact pre-merge SHA.
- [ ] Crash-after-merge recovery is proven from parent SHAs or fails closed into safe mode.
- [ ] GitHub PR creation is idempotent and CI evidence is bound to exact head SHA.
- [ ] Recovery snapshots evidence before cleanup and never kills/removes unknown resources speculatively.
- [ ] Required CLI commands, Rich output, JSON output, doctor, logs, and stable exit codes work.
- [ ] Adversarial concurrency/security/crash tests and full local E2E pass.
- [ ] README documents real guarantees and limitations without claiming unperformed provider/CI/sandbox validation.
- [ ] `pytest`, `mypy`, `ruff`, build, clean-wheel install, CLI smoke, final E2E, Git diff/status, and secret inspection have fresh passing evidence.
