---
name: mas-function-design
description: Define backend function design standards for Python services. Use when implementing or refactoring functions in app/, choosing function boundaries, designing signatures and return contracts, controlling side effects, and reviewing correctness/readability in core/task/services/api modules.
---

# MAS Function Design

## Objective
Design backend functions that are predictable, easy to trace, and easy to evolve.

## Core Principles
1. Keep one primary responsibility per function.
2. Make data flow explicit through inputs and return values.
3. Minimize hidden side effects and shared mutable state.
4. Keep error semantics stable and actionable.
5. Match function placement with module boundary ownership.

## Responsibility
1. Keep a function focused on one decision unit or one orchestration step.
2. Split when a function mixes domain decision and integration IO.
3. Split when one function serves unrelated call paths.
4. Keep thin wrappers thin; move real logic only when it creates real reuse.
5. Do not extract a helper for logic that is easier to understand inline at the call site.
6. For frequently edited task-configuration code, keep the mutation block in the owning orchestration function with a short purpose comment and blank lines around it.
7. Do not split one linear task flow into `builder`/`loader` helpers unless the split removes real duplication or clarifies a true boundary.
8. In AUTO-MAS task flows, keep config import/export, log monitoring, and end-state judgment as explicit orchestration steps; do not hide product-critical run criteria behind vague wrappers.

## Signatures And Returns
1. Use explicit named parameters for business-critical options.
2. Avoid ambiguous boolean positional parameters.
3. Group related data in typed models/dataclasses when argument count grows.
4. Keep optional parameters truly optional with clear default meaning.
5. Return one stable shape per function role.
6. Return domain values, not transport-layer response objects.
7. Prefer signatures that remain compatible with basic static type checking.
8. If omission is a valid state, omit the argument or field instead of passing a typed placeholder that conflicts with the signature.
9. Use positional arguments only for simple, obvious calls with at most two clear parameters.
10. Use keyword arguments for boolean arguments and for calls with more than two parameters.

## Error Handling
1. Raise domain-meaningful exceptions at domain layers.
2. Convert exceptions to API-safe output only at API boundary.
3. Do not swallow exceptions without logging context and fallback reason.
4. Keep retry logic near integration boundaries, not in pure helpers.
5. Include enough context in errors for diagnosis (`script_id`, `user_id`, step).

## Side Effects And Async
1. Keep file IO, network, process, and global state operations explicit.
2. Isolate side effects behind service/helper functions.
3. In pure transformation functions, avoid logging and external calls.
4. Do not mutate input objects unless the contract explicitly states mutation.
5. Use `async` only when awaiting IO or async coordination primitives.
6. Keep cancellation-safe cleanup in `finally` blocks for long-running flows.
7. Avoid mixing sync blocking calls directly in async hot paths.
8. Keep task spawning in orchestrator-level functions, not leaf utilities.
9. Trust existing base-layer guarantees instead of repeating their correction logic in every function.
10. Prefer one clear wait/check block over several tiny sleeps, logs, or staged wrappers that express the same step.
11. When success/failure depends on log text, log timestamps, and process exit together, keep that decision rule centralized and readable instead of scattering partial checks across helpers.
12. `TaskExecuteBase.main_task`, `final_task`, and `on_crash` are the required execution contract for task classes; keep their responsibilities distinct.
13. `main_task` and `final_task` may raise normally, but `on_crash` must protect itself from uncaught exceptions.
14. Await child task spawning through `await self.spawn(...)`; do not fire child tasks without awaiting unless the owning orchestration has a documented reason.
15. Use `.cancel()` plus `await .accomplish.wait()` when parent code must wait for nested task shutdown and cleanup to finish.

## Placement
1. `api`: parse input, call core/service, map output.
2. `core`: orchestrate flow and state transitions.
3. `task`: execute domain run lifecycle per script type.
4. `services`: wrap external/system capabilities.
5. `utils`: generic reusable helpers without business policy.
6. `models/schema`: no business logic functions.

## Naming
1. Use verb-first names for actions (`load_*`, `build_*`, `merge_*`, `send_*`).
2. Use `check_*` for validation returning status/result.
3. Use `prepare_*` for pre-run setup.
4. Use `finalize_*` or `cleanup_*` for teardown semantics.
5. Avoid vague names like `handle` or `process` without scope words.

## Refactor Triggers
1. Function exceeds clear readability for one screenful of logic.
2. Same decision branch appears in multiple places.
3. Repeated parameter bundles travel together across call sites.
4. Testing one behavior requires heavy environment setup.
5. A dict/registry mapping can replace multiple near-identical branches without hiding the main flow.
6. A proposed helper adds more lookup cost than it removes.
7. A proposed fallback only mirrors an invariant already enforced by the owning model or base class.

## Review Checklist
1. Function has one primary responsibility.
2. Signature is explicit and stable for callers.
3. Return shape is typed and consistent.
4. Error behavior is clear and layered correctly.
5. Side effects are visible and isolated.
6. Placement follows `mas-module-boundary`.
7. Shared schema semantics align with `mas-schema-naming`.
8. One-off helpers were not extracted unless they created real reuse.
9. Existing base-layer guarantees were reused instead of reimplemented in the function body.
10. Optional values and temporary placeholders remain type-safe under basic static analysis.
11. Multi-argument and boolean-heavy calls use keyword arguments for readability and fewer ordering mistakes.
12. Task classes preserve the documented `main_task`/`final_task`/`on_crash` lifecycle and nested cancellation behavior.
