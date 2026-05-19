# mas-function-design（完整说明）

对应 Skill：`mas-function-design`。来源：AUTO-MAS-Project/skills。

---

# MAS Function Design

## Objective
Design backend functions that are predictable, testable, and easy to evolve.

## Global Constraints
Apply these constraints while using this skill.

1. Make minimal necessary changes first; avoid broad refactors unless explicitly requested.
2. Align with current code style and existing project conventions in the touched module.
3. Avoid over-engineering, over-abstraction, and defensive programming that does not match existing code patterns.
4. Study similar existing implementations deeply before coding and follow established local patterns.

## Core Principles
1. Keep one primary responsibility per function.
2. Make data flow explicit through inputs and return values.
3. Minimize hidden side effects and shared mutable state.
4. Keep error semantics stable and actionable.
5. Match function placement with module boundary ownership.

## Function Size And Responsibility
1. Keep a function focused on one decision unit or one orchestration step.
2. Split when a function does both domain decision and integration IO.
3. Split when one function serves unrelated call paths.
4. Keep thin wrappers thin; move real logic to reusable internal functions.

## Signature Design
1. Use explicit named parameters for business-critical options.
2. Avoid ambiguous boolean parameters in positional form.
3. Group related data in typed models/dataclasses when argument count grows.
4. Keep optional parameters truly optional with clear default meaning.
5. Prefer immutable input types for deterministic behavior.

## Return Contract
1. Return typed results instead of ad-hoc dicts when possible.
2. Use one return-shape per function role.
3. Return domain result values, not transport-layer response objects.
4. For orchestration functions, return minimal summary needed by caller.

## Error Handling
1. Raise domain-meaningful exceptions at domain layers.
2. Convert exceptions to API-safe output only in API boundary.
3. Do not swallow exceptions without logging context and fallback reason.
4. Keep retry logic near integration boundaries, not in pure business helpers.
5. Include enough context in errors for diagnosis (`script_id`, `user_id`, step).

## Side Effect Control
1. Keep side-effect operations explicit: file IO, network, process, global state.
2. Isolate side effects behind service/helper functions.
3. In pure transformation functions, avoid logging and external calls.
4. Do not mutate input objects unless the contract explicitly states mutation.

## Async And Concurrency Rules
1. Use `async` only when awaiting IO or async coordination primitives.
2. Keep cancellation-safe cleanup in `finally` blocks for long-running flows.
3. Avoid mixing sync blocking calls directly in async hot paths.
4. Keep task spawning in orchestrator-level functions, not leaf utilities.

## Layer Placement Rules
1. `api` functions: parse input, call core/service, map output.
2. `core` functions: orchestrate flow and state transitions.
3. `task` functions: execute domain run lifecycle per script type.
4. `services` functions: wrap external/system capabilities.
5. `utils` functions: generic reusable helpers without business policy.
6. `models/schema` functions: avoid business logic functions.

## Naming For Functions
1. Use verb-first names for actions (`load_*`, `build_*`, `merge_*`, `send_*`).
2. Use `check_*` for validation that returns status/result.
3. Use `prepare_*` for pre-run setup with explicit outputs.
4. Use `finalize_*` or `cleanup_*` for teardown semantics.
5. Avoid vague names like `handle`, `process`, `do_stuff` without scope words.

## Refactor Triggers
Refactor when one or more conditions are met.

1. Function exceeds clear readability for one screenful of logic.
2. Same decision branch appears in multiple places.
3. Repeated parameter bundles travel together across call sites.
4. Testing one behavior requires heavy environment setup.

## Review Checklist
1. Function has one primary responsibility.
2. Signature is explicit and stable for callers.
3. Return shape is typed and consistent.
4. Error behavior is clear and layered correctly.
5. Side effects are visible and isolated.
6. Placement follows `mas-module-boundary`.
7. Shared schema semantics align with `mas-schema-naming`.
