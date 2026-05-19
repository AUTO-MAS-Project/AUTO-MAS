# mas-module-boundary（完整说明）

对应 Skill：`mas-module-boundary`。来源：AUTO-MAS-Project/skills。

---

# MAS Module Boundary

## Objective
Keep backend code maintainable by enforcing clear ownership, dependency direction, and placement rules across modules.

## Global Constraints
Apply these constraints while using this skill.

1. Make minimal necessary changes first; avoid broad refactors unless explicitly requested.
2. Align with current code style and existing project conventions in the touched module.
3. Avoid over-engineering, over-abstraction, and defensive programming that does not match existing code patterns.
4. Study similar existing implementations deeply before coding and follow established local patterns.

## Layer Model
Use this logical layering for backend code under `app/`.

1. `models/schema` layer: external API contract and typed data structure.
2. `api` layer: request parsing, response shaping, transport-level concerns.
3. `core` layer: orchestration, lifecycle, task scheduling, state coordination.
4. `task` layer: script-domain execution flow.
5. `services` layer: system/network/integration capabilities.
6. `utils` layer: reusable low-level helpers with no business policy.

## Dev Branch Concrete Map
Use this concrete map when making placement decisions on current `dev`.

1. API routes: `app/api/*.py`.
2. Runtime orchestration: `app/core/*.py`.
3. Schema/config/runtime models: `app/models/schema.py`, `app/models/config.py`, `app/models/task.py`, `app/models/ConfigBase.py`.
4. Script domains: `app/task/MAA`, `app/task/general`, `app/task/SRC`.

## Dependency Direction
Keep dependencies one-way unless explicitly listed.

1. `api -> core/services/models.schema`
2. `core -> services/task/models/utils`
3. `task -> core/services/models/utils`
4. `services -> utils/models` (avoid importing `api` or domain orchestration)
5. `models -> (none of api/core/services/task)`

Disallowed direction examples:

1. `models/schema` importing `core` or `services`.
2. `utils` importing `core` or `api`.
3. `services` importing concrete `api` routers.
4. `api` embedding long-running task logic directly.

## Ownership Rules By Module

### `app/models/schema.py`
1. Define Pydantic models and field constraints only.
2. Keep naming/typing/description logic only.
3. Do not call filesystem, network, process, or business services.
4. Do not embed orchestration branches (`if mode == ...` business logic).

### `app/api/*`
1. Accept `*In`, return `*Out`/`OutBase` contracts.
2. Validate and route to `core/services`.
3. Keep transport concerns (HTTP/WebSocket status, input parsing).
4. Do not implement cross-module business workflow.

### `app/core/*`
1. Own global coordination and lifecycle.
2. Orchestrate TaskManager, timers, config composition, broadcast.
3. Compose services and task handlers.
4. Avoid low-level duplicated helpers that belong in `utils`.

### `app/task/*`
1. Own script-domain execution lifecycle (`check/prepare/run/final`).
2. Keep per-domain decision logic in domain task modules.
3. Reuse shared helpers via `services/utils`.
4. Do not leak transport-layer logic (no API response shaping).

### `app/services/*`
1. Wrap external integrations (system, notification, update, telemetry).
2. Provide stable capability interfaces for `core/task`.
3. Avoid direct dependency on specific API endpoint semantics.

### `app/utils/*`
1. Keep generic helpers, adapters, and primitives.
2. No domain policy, no orchestration state machine.
3. No dependency on API/router modules.

## Placement Decision Tree
1. Is it request/response contract or DTO typing? Place in `models/schema`.
2. Is it endpoint parsing and response model mapping? Place in `api`.
3. Is it cross-task orchestration or global runtime state? Place in `core`.
4. Is it script-domain run logic? Place in `task/<domain>`.
5. Is it integration with OS/network/third-party? Place in `services`.
6. Is it reusable, context-agnostic helper? Place in `utils`.

## Cross-Cutting Boundary Rules
1. Avoid circular imports; if seen, extract interface/helper to lower layer.
2. Avoid direct config file IO in `api`; use `core` facade.
3. Keep business constants close to owning domain layer.
4. For shared schema semantics, align names via `mas-schema-naming` skill.

## Anti-Patterns (Reject In Review)
1. Business rules inside schema definitions.
2. Route handlers containing long workflow loops/retry engines.
3. Utility modules importing orchestrators for convenience.
4. Duplicated policy checks spread across `api/core/task` without owner.

## PR Boundary Checklist
1. Each changed file belongs to the right layer by responsibility.
2. New imports follow allowed dependency direction.
3. No new circular dependency is introduced.
4. Schema changes do not add business execution logic.
5. API changes keep thin-controller pattern.
6. Core/task/services boundaries remain explicit and testable.
