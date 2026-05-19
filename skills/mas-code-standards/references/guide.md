# mas-code-standards（完整说明）

对应 Skill：`mas-code-standards`。来源：AUTO-MAS-Project/skills。

---

# MAS Code Standards

## Objective
Reproduce the practical implementation style used by `DLmaster_361` in the current `dev` branch without copying obsolete behavior or broadening the scope of a change unnecessarily.

## Scope
The strongest reference samples are in:
1. `frontend/electron/services`
2. `frontend/electron/ipc`
3. `frontend/src/views/Initialization`

For Python modules, carry over the same values of explicit orchestration, compatibility-first changes, and operational logging, but always compare nearby files before applying style assumptions.

## Workflow
1. Read [references/style-observations.md](references/style-observations.md), with priority on the commit lenses for `e541fa5f`, `727aafb`, and `e5d72bdb`.
2. Sample 2 to 3 sibling files in the same module before editing.
3. Keep the main execution path obvious; extract helpers only when they make the flow easier to follow.
4. Match nearby naming, logging tone, comment style, and result contracts.
5. Prefer minimal edits that blend into the surrounding code rather than style-driven rewrites.

## Commit Lenses
Use the nearest matching lens before coding.

1. `e541fa5f`: small behavioral cleanup.
   Keep logic local, remove one-off indirection when it makes the hot path harder to read, and simplify conditions without changing outcome.
2. `727aafb`: large feature landing.
   Extend existing books, models, managers, routes, forms, and logs in parallel instead of inventing a separate architecture for the new type.
3. `e5d72bdb`: merge-into-dev integration.
   Preserve the feature branch structure, then make compatibility or consolidation edits at the integration points instead of rewriting everything during merge.

## Core Style Traits
1. Use clear file sections with banner comments such as `// ==================== 类型定义 ====================`.
2. Keep module headers and function comments short, Chinese, and purpose-driven.
3. Prefer one service or handler class per responsibility with explicit constructor wiring and fields.
4. Write orchestration as staged, numbered steps when the flow is long or stateful.
5. Put exported interfaces, progress types, result types, and callback types near the top of the file.
6. Prefer explicit result objects such as `{ success: boolean; error?: string }` across service boundaries.
7. Catch errors at service boundaries, convert them to stable result objects, and log actionable context.
8. Use `getLogger('中文名')` and short operational log lines instead of decorative logging.
9. Favor straightforward imperative code over generic abstractions, clever helpers, or premature reuse.
10. Allow light duplication when it keeps each step readable and locally understandable.
11. In UI orchestration code, centralize state, drive rendering from computed props, and isolate display formatting in tiny helpers.
12. Respect file-local formatting. Do not normalize indentation or rearrange unrelated code just to satisfy a preferred style.
13. When adding a new script or domain type, mirror the existing end-to-end extension pattern: config model, schema, routing, task registration, frontend types, composables, and dedicated edit views move together.
14. Prefer compatibility edits at registration points such as `BOOK`, union types, routing branches, and progress payloads before considering deeper refactors.

## Avoid
1. Do not introduce framework-heavy abstractions or generic factories unless the surrounding module already uses them.
2. Do not hide the main workflow inside too many helper layers.
3. Do not switch comment or logging language inconsistently inside a file.
4. Do not turn a small fix into a broad refactor for stylistic purity.
5. Do not confuse "explicit" with "verbose"; keep the code direct, not inflated.
6. Do not use a merge or feature landing as an excuse to redesign stable module boundaries unless the task explicitly asks for that.
7. Do not modify OpenAPI-generated files. Ask the developer to regenerate them manually when updates are required.

## Review Checklist
1. The new code reads like neighboring `DLmaster_361` files.
2. Types, results, and progress payloads remain explicit.
3. Logs and comments are concise, operational, and consistent with the touched module.
4. The main path is still easy to trace top-to-bottom.
5. Compatibility and existing behavior were preserved unless the task explicitly changed them.
6. The chosen style lens matches the task: cleanup, feature landing, or dev integration.
