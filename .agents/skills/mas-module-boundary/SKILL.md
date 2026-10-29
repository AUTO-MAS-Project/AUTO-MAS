---
name: mas-module-boundary
description: Define backend module boundaries, DIP/IoC, low coupling and high cohesion. Use for dependency direction, injection, layer ownership, or preventing script-specific business from leaking into shared modules under app/.
---

# MAS Module Boundary

## Objective
Keep backend code maintainable by enforcing clear ownership, dependency direction, and placement rules across modules.

## Layer Model
1. `models/schema.py`: cross-module external contracts and shared typed payloads; `models/config/`: domain config declarations; `config/`: framework behavior and contract derivation.
2. `api`: request parsing, response shaping, transport concerns.
3. `core`: orchestration, lifecycle, task scheduling, state coordination.
4. `task`: script-domain execution flow.
5. `services`: system/network/integration capabilities.
6. `utils`: reusable low-level helpers with no business policy.

## Current Dev Map
1. API routes: `app/api/*.py`
2. Runtime orchestration: `app/core/*.py`
3. Shared/config/runtime models: `app/models/schema.py`, `app/models/config/`, `app/models/task.py`; config framework: `app/config/`
4. Script domains: `app/task/MAA`, `app/task/general`, `app/task/SRC`

## Dependency Direction
1. `api -> core/services/models/config.wire`; endpoint-local models are declared in the owning API module.
2. `core -> services/task/models/utils`
3. `task -> core/services/models/utils`
4. `services -> utils/models`
5. `models -> none of api/core/services/task`
6. `models.config -> config/utils/shared models`; `config -> utils` for low-level capabilities. Config framework, models and business code do not import routers; shared contracts are extracted to `schema.py`, not another API module.

These arrows describe permitted layer relationships, not permission for every module to import every concrete implementation. In particular, `core -> task` allows application composition and calls through adapter contracts; it does not allow shared orchestration to absorb script-specific policy. Reciprocal layer relationships do not permit circular module imports.

Disallowed examples:
1. `models/schema` importing `core` or `services`
2. `utils` importing `core` or `api`
3. `services` importing concrete `api` routers
4. `api` embedding long-running workflow loops directly

## DIP / IoC and Low Coupling / High Cohesion

1. **Dependency inversion (DIP):** shared orchestration depends on the capabilities it consumes, not on a particular adapter's implementation or private config layout. Define a narrow contract with the consumer or in a neutral lower-level module, following the layer rules above; implementations conform to that contract. Transport contracts keep their existing API/schema placement.
2. **Inversion of control (IoC):** the application composition entry point selects and wires concrete implementations, registers handlers/factories, and owns their lifetime. Shared workflows receive those capabilities and invoke them at explicit lifecycle steps. A type-to-factory registry or constructor callback is sufficient; no DI container or generic plugin framework is required.
3. Prefer the smallest useful dependency: explicit values, typed callables, or a focused `Protocol`. Do not pass the entire `AppConfig`, task manager, publisher or service container when only one read or operation is needed. A wrapper that still reaches through global objects, service locators or lazy imports into adapter internals has not inverted the dependency.
4. **Low coupling:** keep implementation changes behind stable inputs, results and error contracts. Consumers must not inspect an adapter's private fields, branch on its name to reconstruct its policy, or duplicate its decisions. Direct construction and calls within one ownership boundary remain valid; do not create an interface for every helper.
5. **High cohesion:** keep state, decisions, operations and cleanup that maintain the same business invariant under one owner. Separate unrelated reasons to change, including domain policy and external I/O. A real responsibility or dependency boundary justifies extraction with one caller; file count, import count and reuse count alone do not establish good boundaries.

## Script-Specific Business Must Not Flow Back into Shared Modules

Script-specific policies and workflows must not be added or moved back into `AppConfig`, the public `TaskManager`, or general-purpose base services. Adapter-owned behavior stays in the owning `app/task/<Adapter>/` domain and is accessed through contracts. This does not authorize implementing upstream-owned work: apply [the black-box boundary](../mas-script-specialized-adapter/references/blackbox-boundary.md) first.

| Shared owner | Allowed responsibilities | Script-specific behavior that must stay outside |
| --- | --- | --- |
| `AppConfig` | Collections, identity, locks, transactions, commits, and invoking registered config handlers | Adapter defaults/initialization policy, resource interpretation, config conversion and external-script import workflows |
| Public `TaskManager` | Manager registration, common dispatch, resource coordination and task lifecycle | Per-adapter preparation/run branches, config interpretation and upstream-result interpretation |
| General-purpose base services | File, network, process and other MAS-defined capabilities | Adapter names, private config semantics or game-specific conditions controlling the generic algorithm |

Type declarations, registry entries and concrete wiring at an application composition entry point are allowed integration work. Keep these entries declarative or limited to construction; moving an adapter workflow into a factory lambda or startup callback is still business leakage. Dedicated integration services are judged by their actual ownership and contracts, not by the `services` directory name alone.

When a capability has MAS-defined semantics independent of any one adapter, keep its single implementation in the framework and let adapters declare parameters or invoke it. The prohibition above does not justify copying common lifecycle, notification, backup or update logic into each adapter. Existing exceptions are migration targets, not templates for new code; keep repairs scoped to the affected boundary unless a broader migration is authorized.

## Ownership Rules
1. `app/models/schema.py`: shared transport contracts and payloads only. Endpoint-specific models belong at the top of their owning API module; config fields are declared once in `app/models/config/` and projected through `app/config/wire.py`.
2. `app/api/*`: accept `*In`, return `*Out`/`OutBase`, validate input, call `core/services`, shape response.
3. `app/core/*`: own global coordination, lifecycle, config composition, task scheduling, and broadcast.
4. `app/task/*`: own per-script execution lifecycle (`check/prepare/run/final`) and domain task decisions.
5. `app/services/*`: wrap external integrations and provide stable capabilities to `core/task`.
6. `app/utils/*`: generic helpers and low-level adapters only. No domain policy and no orchestrator imports.
7. Common script-config import/restore orchestration belongs to `core/task`, not `api` or `schema`. Adapter-specific directory rules, conversion and preparation belong to the owning task domain; shared orchestration invokes its registered capability.
8. The owning task domain/log adapter interprets upstream result surfaces within the black-box boundary. Shared orchestrators consume normalized domain results without reconstructing per-script verdicts; schema models and transport handlers contain neither policy.

## Placement Decision Tree
1. Endpoint-specific request/response contract -> owning `api` module; cross-module or business-shared contract -> single-file `models/schema.py`; config field/default/constraint -> `models/config/`
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
10. Script-specific adaptation is cross-layer by design: add script/user declarations in `app/models/config/script.py`, update the owning registry/public exports in `app/models/config/__init__.py`, derive endpoint config payloads, extend startup orchestration and task dispatch. API modules own endpoint contracts and thin handlers: parse, call the owning `app/task/<Xxx>/` function, shape the response. Directory handling, import, update and group propagation belong in the script domain. The MaaFW engine's `tools/core/` packages stay host-agnostic and its worker subprocess does not import host modules — see `app/task/MaaFW/AGENTS.md`.
11. For a new script domain, start from the closest existing task folder shape, commonly `app/task/general`, then rename and adapt domain-specific config, run, manual-review, and manager code in place.
12. Config field declarations, framework lifecycle and business configuration ownership are separate responsibilities. Use [the configuration framework reference](../mas-data-model/references/config-framework.md) for framework contracts; external script file snapshots remain owned by task/restore orchestration.

## Anti-Patterns
1. Business rules inside schema definitions.
2. Route handlers containing workflow loops or retry engines.
3. Utility modules importing orchestrators for convenience.
4. Duplicated policy checks spread across `api/core/task` without an owner.
5. A new domain folder that introduces multiple thin modules without actual reuse or boundary pressure.
6. Route handlers or module-private helpers in `app/api/` that carry script-specific business (directory layout, import/update flows, config migration) instead of calling the owning `app/task/<Xxx>/` module.
7. Moving adapter policy into `AppConfig`, the public task manager, base services or their registration callbacks under the name of reuse or composition.
8. Injecting a broad global object or wrapping a concrete adapter lookup while leaving the shared consumer coupled to its internals.

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
11. Cross-boundary dependencies are explicit and narrow; concrete selection/lifetime belongs to application composition, and consumers do not read adapter internals or recover dependencies from globals.
12. Script-specific policy has not flowed back into shared modules; registration is only registration, and cohesive ownership or a real dependency boundary can justify extraction without a second caller.
