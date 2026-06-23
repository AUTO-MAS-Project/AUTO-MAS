---
name: mas-module-boundary
description: Define and enforce backend module boundaries for Python services. Use when adding or refactoring backend code under app/, reviewing dependency direction, deciding layer ownership, or preventing logic leakage across schema/api/core/services/task/utils modules.
---

# MAS Module Boundary

## Objective
Keep backend code maintainable by enforcing clear ownership, dependency direction, and placement rules across modules.

## Layer Model
1. `models/schema`: external API contract and typed data structure.
2. `api`: request parsing, response shaping, transport concerns.
3. `core`: orchestration, lifecycle, task scheduling, state coordination.
4. `task`: script-domain execution flow.
5. `services`: system/network/integration capabilities.
6. `utils`: reusable low-level helpers with no business policy.

## Current Dev Map
1. API routes: `app/api/*.py`
2. Runtime orchestration: `app/core/*.py`
3. Schema/config/runtime models: `app/models/schema.py`, `app/models/config.py`, `app/models/task.py`, `app/models/ConfigBase.py`
4. Script domains: `app/task/MAA`, `app/task/general`, `app/task/SRC`

## Dependency Direction
1. `api -> core/services/models.schema`
2. `core -> services/task/models/utils`
3. `task -> core/services/models/utils`
4. `services -> utils/models`
5. `models -> none of api/core/services/task`

Disallowed examples:
1. `models/schema` importing `core` or `services`
2. `utils` importing `core` or `api`
3. `services` importing concrete `api` routers
4. `api` embedding long-running workflow loops directly

## Ownership Rules
1. `app/models/schema.py`: naming, typing, field descriptions only. No filesystem, network, process, or business branching.
2. `app/api/*`: accept `*In`, return `*Out`/`OutBase`, validate input, call `core/services`, shape response.
3. `app/core/*`: own global coordination, lifecycle, config composition, task scheduling, and broadcast.
4. `app/task/*`: own per-script execution lifecycle (`check/prepare/run/final`) and domain task decisions.
5. `app/services/*`: wrap external integrations and provide stable capabilities to `core/task`.
6. `app/utils/*`: generic helpers and low-level adapters only. No domain policy and no orchestrator imports.
7. Script-config import/restore policy belongs to `core/task` orchestration, not `api` or `schema`: AUTO-MAS manages other scripts by swapping their config files/folders before and after task execution.
8. Script success/failure heuristics based on log text, log timestamp, and process exit belong to orchestrators and log-monitor helpers, not to schema models or transport handlers.

## Placement Decision Tree
1. Request/response contract or DTO typing -> `models/schema`
2. Endpoint parsing and response mapping -> `api`
3. Cross-task orchestration or global runtime state -> `core`
4. Script-domain run logic -> `task/<domain>`
5. OS/network/third-party integration -> `services`
6. Reusable, context-agnostic helper -> `utils`

## Cross-Cutting Rules
1. Avoid circular imports; if seen, extract interface/helper to a lower layer.
2. Avoid direct config file IO in `api`; use a `core` facade.
3. Keep business constants close to the owning domain layer.
4. Shared schema semantics should align with `mas-schema-naming`.
5. New config modes or raw-config capabilities must be end-to-end complete: model field, edit entry, persistence path, and runtime consumer must all exist before the feature is considered real.
6. Do not leave placeholder config fields, fake detailed-mode branches, or dead save paths in one layer when no owning runtime path exists.
7. Do not create standalone `builder`, `loader`, or helper-service modules for a feature that has no second call site and no real ownership boundary.
8. If a domain can be expressed as one task class plus nearby local helpers, prefer that over creating a mini-subsystem inside the domain folder.
9. When adding support for a new external script, preserve the product's config-copy plus log-monitor architecture instead of embedding script-specific state machines into shared layers.
10. Script-specific adaptation is cross-layer by design: add the script config/user config in `app/models/config.py`, expose schema types in `app/models/schema.py`, wire API handling in `app/api/scripts.py`, extend global config orchestration in `app/core/config.py`, and add task dispatch in `app/core/task_manager.py`.
11. For a new script domain, start from the closest existing task folder shape, commonly `app/task/general`, then rename and adapt domain-specific config, run, manual-review, and manager code in place.

## Anti-Patterns
1. Business rules inside schema definitions.
2. Route handlers containing workflow loops or retry engines.
3. Utility modules importing orchestrators for convenience.
4. Duplicated policy checks spread across `api/core/task` without an owner.
5. A new domain folder that introduces multiple thin modules without actual reuse or boundary pressure.

## PR Boundary Checklist
1. Each changed file belongs to the right layer by responsibility.
2. New imports follow allowed dependency direction.
3. No new circular dependency is introduced.
4. Schema changes do not add business execution logic.
5. API changes keep the thin-controller pattern.
6. Core/task/services boundaries remain explicit and testable.
7. New configuration concepts are complete across model, UI, and runtime, or they are not introduced yet.
8. New helper modules justify their existence with reuse or a real dependency boundary, not just naming neatness.
9. New script support is complete across config templates, schema, API, task manager dispatch, task folder, and frontend entry points before it is treated as implemented.
10. Searches for the source template domain, such as `GeneralConfig`/`GeneralUserConfig`, were used to find all required registry and branch updates.
