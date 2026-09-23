# AgentNexus — Production Design Specification

**Date:** 2026-09-23  
**Status:** Approved design, production implementation  
**Target:** Python 3.12+  
**Package:** `agent-nexus`  
**CLI:** `nexus` (aliases: `agentnexus`, `orch`)  
**Primary package namespace:** `orch`

## 1. Purpose

`AgentNexus` is a functional Python control plane for coordinating 5–10+ concurrent AI coding agents on one Git repository while preventing unverified completion, uncontrolled resource collisions, stale-worker updates, unsafe integration, and silent regression.

The engine treats every worker claim as untrusted until verified by physical evidence. Workers produce candidate changes; the engine owns assignment, isolation, verification, integration, recovery, and completion state.

The product is not a handbook and not a prompt-only framework. It must install as a Python package, expose a Typer CLI, expose a reusable Python core API, persist authoritative runtime state, launch real CLI-based agents, create and manage native Git worktrees, independently audit candidate branches, integrate approved candidates sequentially, and optionally automate GitHub PR/CI lifecycle operations through `gh`.

## 2. Source foundations and reuse policy

The design synthesizes four supplied source families.

### 2.1 V1 discipline retained

The following are normative engine invariants:

1. **Zero Hallucination / Zero Trust:** no command result, file existence, test result, branch state, or completion claim may be inferred from worker prose when it can be verified directly.
2. **Mandatory Physical Evidence:** authoritative claims require concrete Git state, files, process status, exit codes, hashes, or durable state records.
3. **Strict Scope Enforcement:** a worker may write only inside its assigned ownership boundary and resource allocation.
4. **Zero False Completion:** a task or run is never reported complete while required checks remain failed, missing, unknown, stale, or pending.

### 2.2 V2 invariants retained

The engine retains and formalizes:

- separate task state and process/agent state;
- DAG-constrained scheduling;
- semantic resource ownership and path ownership;
- generation fencing to reject stale zombie updates;
- lease-backed resource allocation;
- recovery bundles before destructive cleanup;
- heartbeat as liveness evidence, not progress evidence;
- fail-closed behavior when safety cannot be proven.

### 2.3 V3 implementation lessons retained selectively

Useful V3 patterns are preserved conceptually:

- Python 3.12+;
- Pydantic v2 strict models;
- Typer CLI;
- SQLite WAL persistence;
- optimistic version checks;
- append-only event records;
- native Git worktree management;
- runtime adapter abstraction;
- independent audit and integration worktree concepts.

The V3 package itself is not adopted as the public contract. `orch-engine` uses the new `orch` namespace, the CLI contract in this specification, a NetworkX DAG implementation, richer transactional resource tables, a stronger evidence-bound audit certificate, first-class GitHub lifecycle support, and the task FSM defined here.

### 2.4 Finalization workflow lessons retained

The engine adopts the supplied release-discipline principle that environment limitations and unperformed assurance steps must be reported explicitly rather than silently treated as success.

## 3. Non-goals

Version 1 will not implement:

- a distributed multi-host consensus protocol;
- Kubernetes orchestration;
- a mandatory Docker runtime;
- an HTTP control-plane service;
- a proprietary model provider dependency;
- automatic LLM-based conflict resolution inside an audited candidate;
- syscall-level containment for native CLI agents unless an optional sandbox provider is configured.

Native CLI agents are an explicit trust boundary. `orch-engine` protects the repository with worktree isolation, resource ownership, environment separation, exact Git evidence, independent audit, and controlled integration; it must not claim stronger sandbox enforcement than the active runtime provides.

## 4. Architecture overview

The system is divided into four planes.

### 4.1 Control plane

- Typer CLI
- `Orchestrator`
- DAG scheduler
- task FSM
- transactional lock/resource manager
- SQLite state and event store

### 4.2 Execution plane

- Git worktree manager
- isolated runtime environment builder
- harness capability discovery
- harness adapters
- async process supervisor
- immutable candidate freeze

### 4.3 Trust plane

- seven-gate forensic audit runner
- evidence store
- cryptographic audit certificate
- sequential merge engine
- integration regression runner
- GitHub PR/CI bridge

### 4.4 Recovery plane

- reconciliation of SQLite desired state, physical Git state, process state, leases, and remote integration evidence
- recovery bundles
- generation invalidation
- deterministic cleanup and safe-mode entry

## 5. Package layout

The implementation shall use this logical structure. Small implementation-driven file splits are allowed if public responsibilities remain unchanged.

```text
orch_engine/
├── pyproject.toml
├── README.md
├── LICENSE
├── tasks.example.yaml
├── orch/
│   ├── __init__.py
│   ├── config.py
│   ├── errors.py
│   ├── cli/
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── init_cmd.py
│   │   ├── plan_cmd.py
│   │   ├── spawn_cmd.py
│   │   ├── lock_cmd.py
│   │   ├── audit_cmd.py
│   │   ├── merge_cmd.py
│   │   ├── pr_cmd.py
│   │   ├── recover_cmd.py
│   │   ├── doctor_cmd.py
│   │   └── logs_cmd.py
│   ├── models/
│   │   ├── __init__.py
│   │   ├── task.py
│   │   ├── state.py
│   │   ├── lock.py
│   │   ├── audit.py
│   │   ├── execution.py
│   │   └── merge.py
│   └── core/
│       ├── __init__.py
│       ├── orchestrator.py
│       ├── state.py
│       ├── dag.py
│       ├── locks.py
│       ├── git.py
│       ├── worktree.py
│       ├── environment.py
│       ├── process.py
│       ├── audit.py
│       ├── merger.py
│       ├── integration.py
│       ├── regression.py
│       ├── github.py
│       ├── recovery.py
│       └── harness/
│           ├── __init__.py
│           ├── base.py
│           ├── discovery.py
│           ├── generic_cli.py
│           ├── claude_code.py
│           ├── gemini_cli.py
│           ├── antigravity.py
│           └── aider.py
└── tests/
    ├── unit/
    ├── component/
    ├── integration/
    ├── adversarial/
    ├── e2e/
    └── fixtures/
```

## 6. Technology choices

### 6.1 Required runtime dependencies

- Python `>=3.12`
- Typer
- Rich
- Pydantic v2
- NetworkX
- PyYAML
- standard-library `sqlite3`
- standard-library `asyncio` and subprocess primitives
- native Git CLI

### 6.2 Build and development

The package shall use Hatchling unless implementation evidence identifies a blocking compatibility issue. Development dependencies shall include pytest, pytest-asyncio, pytest-cov, mypy, Ruff, and build tooling. Hypothesis may be included as a development-only dependency for state/DAG/lock property tests.

The console entry point is:

```toml
[project.scripts]
orch = "orch.cli.main:app"
```

## 7. Strict data models

All configuration, task, audit, execution, and lock models shall use Pydantic v2 with `extra="forbid"` unless a deliberately open extension map is explicitly documented.

### 7.1 Task specification

A `TaskSpec` contains at least:

- `id`
- `title`
- `description`
- `role`
- `dependencies`
- `ownership`
- `resources`
- `acceptance`
- optional `harness`
- `timeout_seconds`
- `max_attempts`
- `priority`
- `allow_noop`

An empty write ownership set is deny-write in production mode, not unrestricted access.

### 7.2 Standard roles

The initial role enum shall expose the five requested standard profiles:

- Architect
- Core Backend
- Fullstack/UI
- QA/Audit
- DevOps/CI/CD

Roles describe work responsibility. They are not bound to a specific model vendor or harness adapter.

### 7.3 Execution identity

A runtime candidate is identified by:

- `run_id`
- `task_id`
- `attempt_id`
- `attempt_number`
- `generation`
- `branch`
- `worktree_path`
- `base_sha`
- `head_sha`
- `task_spec_sha256`
- `prompt_sha256`

Retries create new attempts. Historical attempts are never overwritten.

## 8. Task finite-state machine

The canonical task states are:

```text
PENDING
READY
ASSIGNED
SPAWNED
IN_PROGRESS
AUDIT_READY
AUDITED
MERGING
COMPLETED
REJECTED
RECOVERING
```

`READY` is an intentional addition to the originally supplied transition list. It distinguishes dependency-complete work from dependency-blocked work.

### 8.1 Principal success transitions

```text
PENDING -> READY
READY -> ASSIGNED
ASSIGNED -> SPAWNED
SPAWNED -> IN_PROGRESS
IN_PROGRESS -> AUDIT_READY
AUDIT_READY -> AUDITED
AUDITED -> MERGING
MERGING -> COMPLETED
```

### 8.2 Failure/recovery transitions

A state may enter `RECOVERING` only through recovery-authorized transitions. Audit may transition `AUDIT_READY -> REJECTED`. Integration may transition `MERGING -> REJECTED` when policy chooses terminal rejection rather than retry. A retry creates a new attempt and returns the task's active attempt to a schedulable state; it does not resurrect a terminal historical attempt.

### 8.3 Transition authority

- scheduler: `PENDING -> READY`
- orchestrator: `READY -> ASSIGNED`
- dispatcher/process controller: `ASSIGNED -> SPAWNED`
- runtime monitor: `SPAWNED -> IN_PROGRESS`, `IN_PROGRESS -> AUDIT_READY`
- auditor only: `AUDIT_READY -> AUDITED` or audit rejection
- merger only: `AUDITED -> MERGING`, `MERGING -> COMPLETED`
- recovery controller: recovery transitions

A worker adapter can never directly declare `AUDITED`, `MERGING`, or `COMPLETED`.

### 8.4 Optimistic concurrency

Mutable state rows carry a monotonically increasing `version`. Updates must include expected current version and expected current state. A zero-row update is a `STATE_VERSION_CONFLICT`, not permission to retry silently against unknown state.

## 9. Run state

Run-level state is distinct from task state:

```text
CREATED
PLANNED
RUNNING
INTEGRATING
VERIFYING
READY_FOR_PROMOTION
COMPLETED
FAILED
SAFE_MODE
```

A run cannot become `COMPLETED` merely because every worker process exited. If configured remote CI is pending, the run remains `VERIFYING`. If final integration regression fails, the run is not complete even if all individual tasks previously passed audit.

## 10. SQLite authoritative store

The default state database is `.orch/state.db`.

Required pragmas:

```sql
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;
PRAGMA synchronous = FULL;
PRAGMA busy_timeout = 5000;
```

SQLite is the authoritative mutable runtime state. YAML/JSON files are input/output interchange and evidence formats, not competing canonical runtime stores.

### 10.1 Core tables

The database shall include a schema metadata/version table so `orch init` can apply explicit, idempotent state-store migrations. The schema shall include equivalent normalized tables for:

- `runs`
- `tasks`
- `task_attempts`
- `task_dependencies`
- `agents`
- `agent_processes`
- `resource_locks`
- `migration_allocators`
- `migration_slots`
- `port_allocations`
- `worktrees`
- `audit_reports`
- `audit_evidence`
- `merge_queue`
- `merge_attempts`
- `github_prs`
- `ci_runs`
- `events`

### 10.2 Event journal

Every authoritative state mutation and its corresponding append-only event must be committed in the same SQLite transaction. A state change is not successful unless both the canonical row mutation and its event commit atomically. External side effects such as Git or process creation use an operation journal with pre/post physical reconciliation because SQLite cannot transact the filesystem or OS process table.

Core event families include:

- task state changes
- lock acquire/renew/release/reclaim
- worktree create/remove
- process spawn/exit/loss
- audit start/step/certification/invalidation
- merge start/conflict/rollback/completion
- recovery scan/action/completion
- GitHub PR/CI state changes

Application logs are diagnostic and are not a replacement for the event journal.

## 11. DAG planner and scheduler

`orch.core.dag` shall parse `tasks.yaml` or `project-spec.json` into a `networkx.DiGraph`.

Validation must reject:

- duplicate task IDs
- missing dependencies
- self-dependencies
- dependency cycles
- invalid ownership declarations
- irreconcilable static resource conflicts

Execution waves are generated with topological generations. Static wave membership does not guarantee simultaneous execution.

A task becomes runtime-ready only when:

- dependencies satisfy the configured dependency policy;
- required dependency outputs remain valid;
- required resources are acquirable;
- agent capacity is available;
- engine safe mode is off.

The production default dependency policy is integrated completion, not worker exit or unaudited candidate availability.

## 12. Resource ownership and locking

### 12.1 Resource types

Version 1 supports at least:

- repository path/file ownership
- migration slot allocation
- local port allocation
- worktree identity locks
- integration branch lock

The internal API shall be extensible to semantic resources such as API routes, schema names, queue names, CLI commands, or feature flags.

### 12.2 Lock modes

The core modes are:

- `SHARED_READ`
- `EXCLUSIVE_WRITE`
- `SHARED_WRITE_CONTROLLED`
- `INTEGRATION_ONLY`

Controlled shared-write is legal only under an explicitly named coordination policy/group.

### 12.3 Path collision semantics

Path safety requires more than string equality. The validator shall:

1. normalize separators and repository-relative syntax;
2. reject repository escape via `..`;
3. resolve configured case policy;
4. detect actual-file overlap against current repository inventory;
5. detect future-path overlap from literal glob prefixes;
6. classify difficult arbitrary glob intersections as `PROVEN_DISJOINT`, `PROVEN_OVERLAP`, or `AMBIGUOUS`.

Two exclusive writers with `AMBIGUOUS` overlap are rejected in production mode.

Renames/moves are treated as source-path plus destination-path operations.

### 12.4 Symlink safety

A write target resolving outside the repository root is invalid. Resource normalization must not grant permission to escape via symlink or path traversal.

### 12.5 Atomic assignment

All resources needed by one assignment must be reserved transactionally with `BEGIN IMMEDIATE` before process spawn.

Conceptually:

```text
verify READY and current generation
verify dependencies
acquire path locks
reserve migration slots
reserve ports
create assignment
transition READY -> ASSIGNED
append events
COMMIT
```

Any failure rolls back the complete assignment; partial reservation is forbidden.

### 12.6 Deterministic ordering

Resource requests shall be canonicalized and deterministically sorted by type and key before evaluation to minimize logical deadlock risk and make behavior reproducible.

## 13. Migration slot allocator

Migration numbers are allocated centrally in SQLite, never by independently scanning `max(existing_files) + 1` in multiple workers.

A transaction reads the next allocator value, reserves it for the current attempt, increments the allocator, and commits. Concurrent allocators must never issue duplicate slots.

Example sequence:

```text
000008
000009
000010
000011
```

A reservation exists before the worker creates its migration file. Once a migration number has been issued, it is never reassigned to a different attempt, even when the original attempt fails; gaps are permitted and are safer than identity reuse. A remediation attempt may explicitly inherit the same migration identity only when it is continuing the same logical migration and the old generation has been revoked.

## 14. Port allocator

Named pools are configured, for example:

```yaml
ports:
  ranges:
    web: [3001, 3099]
    api: [8081, 8199]
    test: [9001, 9099]
```

Tasks request pool/count, not arbitrary global ports by default. Allocation is transactional and bound to the task attempt lease. Unlike migration identities, released ports may be reused after the engine proves the owning process is gone and the lease is safely reclaimed.

## 15. Leases, liveness, and generation fencing

Resource leases contain:

- lock/resource ID
- run/task/attempt
- generation
- owner host/process metadata
- acquired time
- heartbeat time
- expiry

Expiry alone is insufficient proof that a live worker may be destroyed. Reclamation requires lease expiry plus process/attempt reconciliation.

Every assignment has a monotonically increasing generation. Any update, heartbeat, completion message, lock renewal, or audit request from an older generation is rejected as stale.

Path write ownership remains reserved through candidate audit and integration eligibility, not merely until worker process exit. It is released only when the task is `COMPLETED`, terminally `REJECTED`, or an orchestrator-controlled remediation transfers ownership to a newer generation. Ephemeral runtime resources such as ports may be released earlier after their owning process and verification step are conclusively finished. Migration identities follow the non-reuse rule above.

## 16. Worktree manager

Each task attempt receives its own native Git worktree and branch.

Default path form:

```text
.worktrees/<run-id>/<task-id>/<attempt-id>/
```

Default branch form:

```text
orch/<run-id>/<task-id>/<attempt-short-id>
```

### 16.1 Provisioning

Before creation, the manager verifies:

- valid Git repository;
- no unresolved repository merge state affecting provisioning;
- exact base ref can be resolved to a SHA;
- target path remains inside configured worktree root;
- branch/path collision does not exist;
- task assignment and generation are current;
- required resource leases are active.

The worktree is created from the exact persisted `base_sha`, not a moving symbolic branch reference.

After creation, branch and `HEAD` are independently re-read and must match expectations before state becomes ready.

### 16.2 Worktree statuses

At minimum:

- `PROVISIONING`
- `READY`
- `ACTIVE`
- `DIRTY`
- `AUDIT_FROZEN`
- `STALE`
- `RECOVERING`
- `REMOVED`

## 17. Runtime environment isolation

Worktree isolation is supplemented by per-attempt runtime directories under `.orch/runtime/<attempt-id>/` for temporary files, home/state/cache where practical, and produced artifacts.

The engine injects canonical identifiers such as:

- `ORCH_RUN_ID`
- `ORCH_TASK_ID`
- `ORCH_ATTEMPT_ID`
- `ORCH_WORKTREE`

It may isolate common cache variables such as `TMPDIR`, `XDG_CACHE_HOME`, coverage output, Python bytecode caches, and ecosystem-specific caches through configurable profiles.

Secrets are never copied into worktrees automatically. Environment passthrough uses an explicit allowlist. Known secret-shaped output is redacted before durable transcript logging when redaction can be performed without destroying required forensic metadata.

## 18. Harness architecture

Harnesses are execution providers, not authorities.

The adapter protocol provides the equivalent of:

- `discover()`
- `prepare()`
- `spawn()`
- `wait()`
- `interrupt()`
- `terminate()`
- `health()`

Adapters never write canonical task state directly.

### 18.1 Required adapters

Version 1 shall include:

- Generic CLI
- Claude Code
- Gemini CLI
- Antigravity adapter
- Aider

Antigravity availability must be discovered at runtime; the engine must not assume a stable `agy` executable when the host does not provide one.

### 18.2 Capability discovery

Each adapter discovers executable, version, supported headless mode, prompt delivery mechanism, streaming support, and relevant sandbox limitations.

Unavailable tools return an explicit `HARNESS_UNAVAILABLE` result. A static manifest is not proof of host capability.

### 18.3 Generic CLI safety

Generic CLI commands are stored as argv arrays. `shell=True` is disabled by default. Prompt placeholders are compiled before spawn. Shell execution is allowed only under explicit configuration.

## 19. Prompt execution envelope

The engine compiles and persists the prompt given to each worker from:

- global iron rules;
- agent role;
- canonical task identity;
- exact workspace/base SHA;
- task definition;
- dependency context;
- write/read/forbidden ownership boundaries;
- allocated migration/port/resources;
- acceptance criteria;
- commit rules;
- forbidden actions;
- completion evidence contract.

The envelope explicitly states that the worker cannot mark the task audited or completed.

Compiled prompts are persisted with SHA-256 hashes under `.orch/prompts/<task>/<attempt>/` so later audit can prove exactly what instructions were provided.

## 20. Async process supervision

Process spawning uses `asyncio.create_subprocess_exec`, not shell execution by default.

Each process has independent stdout and stderr pumps plus a supervisor. Logs are streamed durably and stored per attempt.

The process record includes at least:

- PID
- spawn time
- host identity
- attempt/generation
- worktree
- command fingerprint
- exit code/termination reason

PID alone is not sufficient ownership proof because operating systems reuse process IDs.

### 20.1 Timeouts

The engine distinguishes:

- spawn timeout;
- measurable-progress timeout;
- absolute execution timeout.

Stdout activity alone is not progress. Measurable progress may include Git tree/diff fingerprint changes, commits, artifact changes, or verified milestone evidence.

### 20.2 Termination

Timeout termination follows graceful interrupt/terminate, bounded grace period, then force-kill when supported. Before cleanup, the engine captures final process and Git evidence.

## 21. Candidate completion and freeze

Worker exit code `0` is only process evidence. Before `AUDIT_READY`, the engine independently verifies:

- process exited;
- assigned worktree still exists;
- branch identity is correct;
- a candidate commit exists unless `allow_noop=true`;
- working tree is clean;
- no unsafe untracked files remain;
- candidate `HEAD` is readable and persisted.

Multi-commit candidates are valid; audit binds to the complete `base_sha...head_sha` diff.

On successful candidate validation the worker loses write authority, the candidate SHA/tree identity is frozen, and the worktree becomes `AUDIT_FROZEN`.

## 22. Seven-gate zero-trust audit

Audit is an independent trust boundary. The auditor is read-only with respect to candidate source. It never fixes a candidate and passes it in the same audit attempt.

The audit target binds:

- run/task/attempt/generation;
- branch and worktree;
- base SHA and head SHA;
- task-spec hash;
- prompt hash;
- verification/acceptance configuration hashes.

The candidate `HEAD` is re-read at audit boundaries. Mutation during audit aborts with `CANDIDATE_MUTATED_DURING_AUDIT`. Audit commands are configured so caches and temporary output are routed outside the candidate worktree whenever practical. Any tracked-source mutation caused by an audit command, or any undeclared persistent worktree mutation, fails final sign-off even when `HEAD` itself did not move.

### 22.1 Dispositions

Audit steps use:

- `PASS`
- `FAIL`
- `UNKNOWN`
- `VIOLATION`

Only required gates all equal to `PASS` can produce a passing certificate. `UNKNOWN` is blocking.

### 22.2 Gate 1 — Git identity and workspace integrity

Verify repository root, worktree, branch, exact `HEAD`, clean status, untracked files, and absence of unresolved merge/rebase state.

### 22.3 Gate 2 — Scope and diff boundary

Compute canonical changes from Git using `base_sha...head_sha`, including adds, modifications, deletes, copies, and renames. Every changed path must satisfy ownership and forbidden-path policy. Renames validate both source and destination.

The gate also detects destructive policy risks such as unauthorized test deletion, CI bypass, migration removal, or hiding artifacts through ignore rules. Path ownership grants a write boundary, not exemption from acceptance/security policy.

### 22.4 Gate 3 — Independent verification commands

Configured unit, integration, type, lint, build, or project commands run independently in the candidate worktree. Each captures argv, cwd, duration, stdout/stderr evidence, exit code, and termination reason.

The audit may record baseline results to distinguish new regressions from pre-existing failures. Baseline awareness improves diagnosis; it does not automatically convert a required nonzero command into success.

### 22.5 Gate 4 — Secret/credential scan

The scanner examines candidate diff and relevant new/renamed/artifact files for private keys, common provider tokens, credential files, password-bearing URLs, `.env` secrets, and other configured patterns.

Findings have rule ID, path/line, severity, confidence, and fingerprint. Allowlisting is fingerprint-specific with a recorded reason; broad wildcard suppression is invalid in production mode.

### 22.6 Gate 5 — Acceptance barem

Every task acceptance criterion has a unique ID and explicit verification method such as:

- command/test;
- file exists;
- file content match;
- schema validation;
- artifact hash;
- Git property;
- explicit manual review.

Manual review remains pending/unknown until real review evidence is supplied. Vague quality statements do not become machine PASS automatically.

### 22.7 Gate 6 — Artifact and contract inspection

Required artifacts are checked for existence, non-emptiness where relevant, format/schema validity, hash, and producer identity. Cross-contract checks cover interfaces such as state enums, public schemas, migration manifests, configuration schema, and other task-declared contracts.

### 22.8 Gate 7 — final sign-off

The final gate verifies all required prior gates, evidence completeness, candidate immutability, and audit input fingerprint. It constructs the certificate only when every blocker is cleared.

## 23. Audit evidence and certificate

Audit evidence lives under `.orch/audits/<task>/<attempt>/<audit-id>/` and includes the report, certificate, evidence manifest, Git evidence, test output, security findings, and artifact manifest.

Each evidence object records path, kind, size, creation time, and SHA-256.

The certificate payload is serialized with deterministic canonical JSON semantics and hashed with SHA-256. The digest is computed over the canonical certificate payload with the `certificate_sha256` field omitted; the resulting digest is then stored in that field. This avoids self-referential hashing.

The certificate binds at minimum:

- schema version;
- audit/run/task/attempt;
- base SHA;
- head SHA;
- task spec hash;
- prompt hash;
- ownership/acceptance/verification configuration fingerprint;
- gate dispositions;
- evidence manifest hash;
- final disposition;
- completion time;
- certificate hash.

A change to candidate `HEAD`, task spec, ownership, acceptance criteria, required verification config, or evidence invalidates the certificate. Version 1 certificates are tamper-evident SHA-256 attestations, not digital signatures and not claims of cryptographic non-repudiation. Optional signing can be added later behind a separate key-provider interface.

## 24. Findings and remediation

Findings have stable IDs and severities `CRITICAL`, `HIGH`, `MEDIUM`, `LOW`, `INFO`.

Hard gates are not weighted scores. A critical credential leak cannot be compensated by unrelated passing tests.

Audit failure preserves the candidate and evidence according to retention policy. Remediation creates a new attempt/generation or an explicit remediation work package; it never edits an already-certified candidate under the old certificate.

## 25. Sequential integration engine

Audit proves a candidate relative to its base. Integration separately proves composition with the current integration state.

### 25.1 Dedicated integration worktree

Integration occurs in an engine-owned worktree, never a worker worktree.

The recommended production default is a staging integration branch:

```text
main -> orch/integration/<run-id>
```

Direct-main mode may be configured for simpler repositories, subject to branch protection and rollback policy.

### 25.2 Deterministic merge queue

Only audited candidates enter `merge_queue`. Order is deterministic by:

1. DAG dependency rank;
2. configured priority;
3. audit completion time;
4. task ID tie-breaker.

Finishing a worker earlier does not grant arbitrary integration priority.

### 25.3 Pre-merge revalidation

Immediately before merge, verify:

- candidate ref still equals certificate head SHA;
- certificate hash is valid;
- task/audit fingerprint is unchanged;
- integration branch actual SHA equals expected SHA;
- integration exclusive lock is held.

Any drift blocks the merge.

### 25.4 Merge operation

Default Git operation is native three-way `git merge --no-ff <candidate>` in the integration worktree. The engine does not rely on `git pull` because user pull/rebase configuration is not deterministic enough for the control plane.

### 25.5 Conflicts

On conflict:

- capture status/conflicted paths/merge base/SHA evidence;
- abort the merge;
- verify exact pre-merge SHA restored;
- create a remediation/rebase task or require architect intervention according to policy.

Automatic LLM semantic conflict resolution is disabled in the core integration path. A changed/rebased candidate requires a fresh audit.

### 25.6 Regression after every merge

A successful Git merge is not completion. Configured integration regression commands run on the integrated tree. Only passing regression can finalize the merge and transition the task to `COMPLETED`.

### 25.7 Rollback

The pre-merge integration SHA is persisted before mutation. Regression failure restores the engine-owned staging branch to that exact SHA, captures evidence, and verifies the restored tree is clean. Failure to verify rollback enters global safe mode.

### 25.8 Crash-safe merge journal

Merge attempts persist enough phase/state data to reconcile crashes between Git mutation and SQLite update. Recovery may resume verification only when it can prove the observed merge commit has expected parents; otherwise it rolls back or enters safe mode.

## 26. Final run verification

After all mergeable tasks are integrated, the run executes the configured final regression suite, which may be broader than per-task or per-merge checks.

Only a passing final suite can advance the run to `READY_FOR_PROMOTION`.

## 27. GitHub PR and CI lifecycle

`orch.core.github` is a validated wrapper around Git and GitHub CLI behavior. It does not own scheduler/FSM policy.

### 27.1 Capability discovery

Before GitHub actions:

- `gh` must exist;
- version must be queryable;
- authentication status must be valid for the requested operation.

GitHub unavailability does not prevent local plan/spawn/audit/local-integration operations when project policy does not require remote CI.

### 27.2 Push policy

Workers do not push by default. The GitHub controller revalidates branch, head SHA, certificate, and remote before pushing.

Plain force push is forbidden. Explicit rewrite workflows may use `--force-with-lease` only against a known expected remote SHA.

### 27.3 PR strategies

Support:

- per-task PRs;
- a single integration PR from `orch/integration/<run-id>`.

PR bodies are generated from canonical task, changed-file, acceptance, test, and audit data rather than worker prose.

PR creation is idempotent. Existing branch/PR state is queried and verified before creating a new PR.

### 27.4 CI binding

CI status must be bound to exact repository, branch/PR, workflow/check, and `head_sha`. A passing run for a different SHA is irrelevant.

Normalized CI states:

- `PENDING`
- `RUNNING`
- `PASS`
- `FAIL`
- `CANCELLED`
- `TIMED_OUT`
- `UNKNOWN`

Required checks are project-configured. CI timeout is reported as timeout, never guessed as success or failure.

Local audit and remote CI are separate proof layers. Production policy may require both before promotion.

## 28. Recovery and safe mode

`orch recover --dangling` reconciles:

- SQLite canonical state;
- Git branches/worktrees/HEAD/dirty state;
- live process evidence;
- lock/lease state;
- merge journal;
- optional remote PR/CI state.

### 28.1 Recovery classifications

At minimum:

- dangling process
- orphan worktree
- expired lock
- stale attempt/generation
- interrupted merge
- dirty recovery worktree
- DB/Git divergence
- remote state drift
- unknown unsafe state

### 28.2 Recovery bundles

Before destructive cleanup of a dirty/crashed workspace, preserve:

- metadata;
- `git status`;
- patch/diff;
- untracked manifest;
- exact `HEAD`;
- relevant transcript tail;
- locks/resources;
- failed/pending criteria when known.

### 28.3 Orphan worktree cleanup

Automatic removal requires proof that:

- no owned live process exists;
- no current assignment owns it;
- recovery evidence is durable;
- the branch is known;
- the path is inside configured engine worktree root.

Unknown arbitrary worktrees are never force-removed.

### 28.4 Deadlock/wait-for recovery

The resource subsystem may construct a wait-for graph. A logical cycle selects a deterministic victim preferring unspawned/lower-priority/newer reservation work. Recovery releases only safe reservations, not arbitrary active writer locks.

### 28.5 Global safe mode

When canonical and physical state disagree in a way the engine cannot prove safe, it enters `SAFE_MODE`.

In safe mode:

- new spawn is blocked;
- new merge is blocked;
- unsafe mutations are blocked;
- status, evidence inspection, and recovery scans remain available.

The engine never guesses which state is correct merely to continue execution.

## 29. Configuration

Configuration precedence:

1. CLI flags;
2. environment overrides;
3. `.orch/config.yaml`;
4. built-in defaults.

Environment overrides use `ORCH_<SECTION>__<FIELD>` naming.

Configuration models are strict and reject unknown fields.

A representative configuration includes:

```yaml
engine:
  mode: production

scheduler:
  max_parallel_agents: 8
  spawn_timeout_seconds: 30
  heartbeat_timeout_seconds: 60
  progress_timeout_seconds: 900

git:
  integration_branch: main
  integration_mode: staging_branch
  worktree_root: .worktrees
  protected_branches: [main, master, production]

locks:
  default_lease_seconds: 120

ports:
  ranges:
    api: [8081, 8199]
    web: [3001, 3099]

audit:
  require_clean_tree: true
  secret_scan: true

github:
  enabled: true
  pr_strategy: integration
  ci_watch_timeout_seconds: 3600
```

## 30. CLI contract

### 30.1 Required commands

```bash
orch init
orch plan validate <file>
orch plan status
orch spawn --task <task_id>
orch spawn --wave <wave_id>
orch lock list
orch audit run <task_id>
orch merge sequential
orch pr create-all
orch pr watch-ci
orch recover --dangling
```

### 30.2 Additional production commands

```bash
orch doctor
orch logs <task_id>
orch version
```

### 30.3 `orch init`

Creates `.orch/`, initializes/upgrades database schema, writes default configuration when absent, verifies repository identity, and is idempotent. Existing user configuration is not overwritten without explicit force.

### 30.4 `orch plan validate`

Validates schema, DAG, ownership overlap, resources, harness references, and acceptance definitions. Validation alone is read-only. `--activate` imports the validated plan and creates its run records.

### 30.5 `orch plan status`

Displays task state, attempt, harness/agent, lock count, process health, and relevant waiting reason. `--json` emits a versioned machine-readable structure.

### 30.6 `orch spawn`

Performs preflight, atomic resource assignment, worktree creation, environment setup, prompt compilation, harness discovery, async spawn, process persistence, and supervision.

Wave spawn schedules only eligible tasks and obeys configured parallelism/resources. Waiting tasks are reported as waiting, not failed.

### 30.7 `orch lock list`

Shows active resource leases, owner attempt/generation, mode, and expiry/health. The first release does not expose an unsafe unguarded "force unlock" command.

### 30.8 `orch audit run`

Audits the current `AUDIT_READY` attempt unless `--attempt` explicitly identifies a historical candidate. Passing audit exits zero; failed/unknown/violation outcomes are nonzero.

### 30.9 `orch merge sequential`

Integrates audited queue items in deterministic order. `--dry-run` computes ordering, validates certificates/refs/dependencies, and reports intended actions without Git mutation.

### 30.10 `orch pr create-all`

Pushes/creates PRs according to configured strategy and is idempotent.

### 30.11 `orch pr watch-ci`

Monitors exact-SHA required checks until terminal status or configured timeout. It must prefer structured `gh --json` data when available rather than parsing decorated terminal output.

### 30.12 `orch recover --dangling`

Performs scan/classify/plan/apply/reconcile/verify. `--dry-run` reports actions without mutation.

### 30.13 `orch doctor`

Checks Python, Git, repository integrity, SQLite WAL behavior, configuration, worktree safety, configured harnesses, `gh`, authentication, and schema compatibility. Missing optional harnesses are warnings unless the active plan requires them.

### 30.14 `orch logs`

Reads attempt logs with stderr/follow/tail selection without requiring users to know internal directory layout.

## 31. Machine-readable command results

Human output uses Rich. Automation must not parse Rich tables. Important commands provide `--json` with versioned structures.

## 32. Exit-code families

Stable families:

- `0`: success
- `10–19`: input/config/plan
- `20–29`: audit
- `30–39`: resource/lock
- `40–49`: Git/worktree
- `50–59`: harness/process
- `60–69`: merge/integration
- `70–79`: GitHub/CI
- `80–89`: recovery
- `90–99`: internal/safe mode

Initial named mappings include:

- `10 CONFIG_INVALID`
- `11 PLAN_INVALID`
- `20 AUDIT_FAILED`
- `21 SCOPE_VIOLATION`
- `22 SECRET_VIOLATION`
- `23 MISSING_EVIDENCE`
- `24 CANDIDATE_IDENTITY_MISMATCH`
- `31 LOCK_CONFLICT`
- `42 WORKTREE_INVALID`
- `51 HARNESS_UNAVAILABLE`
- `52 AGENT_PROCESS_FAILED`
- `61 MERGE_CONFLICT`
- `62 REGRESSION_FAILED`
- `71 CI_FAILED`
- `72 CI_TIMEOUT`
- `81 RECOVERY_REQUIRED`
- `90 GLOBAL_SAFE_MODE`
- `99 INTERNAL_ERROR`

The implementation plan may assign additional codes within these reserved families but must not change family semantics.

## 33. Python API and error model

CLI modules remain thin. Business logic is exposed through typed core services headed by `Orchestrator`.

The exception hierarchy starts with `OrchError` and typed children for config, plan, state transition, resources, worktree/Git, harness/process, audit, merge, GitHub, and recovery errors.

Core functions return structured result types rather than Rich-formatted strings.

## 34. Logging and observability

Structured diagnostic logs include run/task/attempt/component/event context and are written under `.orch/logs/` without plaintext secret leakage.

The event journal remains the canonical sequence of state-changing facts.

Initial operational counters include task start/completion/rejection, audit pass/fail, lock conflicts, recovery actions, merge conflicts, and regression failures. Version 1 does not require a Prometheus server.

## 35. Test strategy

Production readiness requires five layers.

### 35.1 Unit tests

Cover strict models, FSM guards, DAG/cycle/wave logic, path normalization/overlap, lock compatibility, migration allocator logic, port allocator logic, canonical audit hashing, and configuration validation.

### 35.2 Component tests

Use real temporary SQLite databases and real temporary Git repositories for state store, lock store, worktree manager, process supervisor, audit runner, and merger behavior.

Git behavior shall not be fully mocked because native Git semantics are part of the product contract.

### 35.3 Integration tests

Create a temporary repository and run:

```text
plan -> assignment -> fake harness -> commit -> audit -> merge -> regression
```

A deterministic fake-agent executable provides success, crash, timeout, dirty exit, scope violation, secret leak, and conflict behaviors without requiring paid or network LLM providers.

### 35.4 Adversarial tests

Must cover at least:

- concurrent duplicate migration allocation attempts;
- concurrent overlapping path writers;
- two orchestrator processes assigning the same task;
- PID/process loss mid-write;
- expired lease with uncertain process ownership;
- stale generation trying to complete;
- candidate mutation during audit;
- forbidden file modification;
- secret commit;
- test deletion to hide failure;
- external integration branch movement;
- merge conflict;
- regression failure after clean merge;
- orchestrator crash after Git merge before DB finalization;
- wrong-SHA PR/CI evidence;
- path traversal and symlink escape;
- shell-injection-shaped input.

### 35.5 End-to-end tests

A complete local E2E must prove:

```text
orch init
-> plan validation/activation
-> concurrent fake agents
-> candidate freeze
-> independent audit
-> sequential integration
-> final regression
-> completed run
```

Optional GitHub live E2E runs only when explicitly enabled and authenticated.

## 36. Crash injection

Test-only fault injection points shall exist around critical crash windows such as after lock commit, after worktree creation, after process spawn, after Git merge, and before merge DB finalization. Restart/recovery tests must prove deterministic reconciliation.

## 37. Quality gates for orch-engine itself

Before declaring implementation complete, evidence must show:

- full pytest suite passing;
- strict mypy passing;
- Ruff passing;
- package build passing;
- wheel install into a clean environment passing;
- `orch --help` passing;
- `orch doctor` passing for required local capabilities;
- local full E2E orchestration passing;
- Git diff/status inspection clean or intentionally documented;
- no unresolved high/critical findings.

A numeric coverage target may be used as a supporting metric; it is not a substitute for concurrency/recovery invariant tests.

## 38. Security constraints

The implementation must reject or safely contain:

- task IDs/branch names attempting path traversal;
- repository escape;
- unsafe symlink writes;
- shell injection through task commands;
- unbounded wildcard secret-scan suppression;
- arbitrary force deletion of unknown worktrees;
- arbitrary force push;
- worker attempts to write protected integration branches;
- stale generation state mutation;
- audit evidence that belongs to a different candidate SHA.

## 39. Definition of Done

The engine is complete only when physical verification proves all of the following:

1. Package installs on supported Python.
2. `orch` entry point works.
3. Configuration and task models are strict.
4. DAG cycle detection and execution waves are correct.
5. Concurrent resource allocation cannot duplicate exclusive path leases, migration slots, or ports.
6. Native Git worktree create/inspect/remove lifecycle works.
7. Generic fake agents run concurrently under async supervision.
8. Prompt, process, log, and candidate evidence are durable and attempt-scoped.
9. Worker process success cannot directly complete a task.
10. Audit independently verifies Git identity, scope, tests, security, acceptance, artifacts, and sign-off.
11. Audit certificate hashing is deterministic and stale certificates are blocked.
12. Sequential integration is exclusive and deterministic.
13. Conflicts abort cleanly.
14. Regression failure restores exact pre-merge integration state.
15. Interrupted merge state can be reconciled or safely halted.
16. GitHub client behavior is idempotent and exact-SHA aware in tests.
17. Recovery preserves evidence and rejects zombie generations.
18. Adversarial concurrency/security/recovery tests pass.
19. Strict typing, lint, build, clean-install smoke, and full local E2E pass.
20. Final documentation states real limitations and does not claim unperformed provider/CI/sandbox validation.

## 40. Implementation sequencing constraint

Implementation shall be planned and executed in dependency order rather than by file-tree order. The implementation plan must establish foundational models/state, then DAG/resources, Git/worktrees, process/harness execution, audit, integration, GitHub lifecycle, recovery, CLI composition, adversarial tests, documentation, and final package verification.

Test-driven development is required for feature and bug-fix implementation under the active Superpowers workflow. Completion claims require independent verification commands immediately before delivery.

## 41. Resolved design decisions

The following are intentionally fixed and are not implementation-time ambiguities:

- architecture approach: greenfield `orch` engine with selective reuse of proven invariants, not a compatibility facade over V3;
- authoritative runtime store: SQLite WAL;
- DAG library: NetworkX;
- CLI: Typer + Rich;
- public runtime namespace: `orch`;
- task FSM includes explicit `READY`;
- task and process/agent state remain separate;
- assignment resources are acquired atomically before spawn;
- migration/port allocation is centralized in SQLite;
- one worktree and branch per task attempt;
- workers do not directly push or merge by default;
- audit is read-only and exact-SHA bound;
- hard-gate audit results are not weighted-score overrides;
- merge is sequential through an exclusive integration worktree;
- regression runs after every merge;
- staging integration branch is the recommended default;
- GitHub CLI is optional for local operation but mandatory when project policy requires GitHub CI;
- native harness sandbox guarantees are disclosed honestly;
- ambiguous exclusive path overlap fails closed;
- unknown recovery state blocks unsafe mutation through safe mode.

## 42. Acceptance of this design

Approval of this document authorizes creation of the detailed implementation plan. It does not by itself authorize skipping the implementation-plan review/execution-method gate required by the active Superpowers workflow.
