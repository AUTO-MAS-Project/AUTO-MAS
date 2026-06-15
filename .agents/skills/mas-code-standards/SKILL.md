---
name: mas-code-standards
description: Use when a task asks for AUTO-MAS project code style, DLmaster_361 maintainer style, Conventional Commit wording, backend docstrings, config-item comments, or general code convention review.
---

# MAS Code Standards

## Objective
Reproduce the practical implementation style used by `DLmaster_361` in current `dev` without copying obsolete behavior or broadening scope unnecessarily.

## Scope
Primary style reference samples:
1. `frontend/electron/services`
2. `frontend/electron/ipc`
3. `frontend/src/views/Initialization`

Use these samples as style lenses only. For frontend engineering or UI decisions, prefer `mas-frontend-standards` and `mas-frontend-ui`; for Python modules, carry over the same values of explicit orchestration, compatibility-first changes, and operational logging, but always compare nearby files before applying style assumptions.

## Workflow
1. Read [references/style-observations.md](references/style-observations.md), with priority on commit lenses `e541fa5f`, `727aafb`, and `e5d72bdb`.
2. Sample 2 to 3 sibling files in the same module before editing.
3. Keep the main execution path obvious; extract helpers only when they make the flow easier to follow.
4. Match nearby naming, logging tone, comment style, and result contracts.
5. Prefer minimal edits that blend into surrounding code rather than style-driven rewrites.
6. If recent maintainer review comments are available for the same area, treat them as the strongest style signal.

## Commit Lenses
1. `e541fa5f`: small cleanup.
   Keep logic local, remove one-off indirection, simplify conditions without changing outcome.
2. `727aafb`: feature landing.
   Extend existing books, models, managers, routes, forms, and logs in parallel instead of inventing a separate architecture for the new type.
3. `e5d72bdb`: dev integration.
   Preserve the feature branch structure, then consolidate at integration points instead of rewriting during merge.

## Core Traits
1. Use clear file sections such as `// ==================== 类型定义 ====================`.
2. Keep module headers and comments short, Chinese, and purpose-driven.
3. Prefer explicit orchestration over generic abstractions or clever helpers.
4. Use `getLogger('中文名')` and short operational log lines.
5. Allow light duplication when it keeps each step readable and local.
6. Respect file-local formatting; do not normalize unrelated code.
7. When adding a new script or domain type, extend config model, schema, routing, task registration, frontend types, composables, and edit views together.
8. Prefer compatibility edits at registration points such as `BOOK`, union types, routing branches, and progress payloads before deeper refactors.
9. For finite variants, prefer a small dict/registry mapping instead of many near-identical branches.
10. Keep frequently edited task-configuration logic visible in the owning flow with a short comment instead of hiding it behind one-off helpers.
11. Do not copy another script/domain's special-case logs, timeout exemptions, ignore lists, or workaround branches into a new module until that behavior is confirmed locally.
12. If a new capability is used only once, default to an inline block or local helper; split into `builder`, `loader`, or extra services only after real reuse or boundary pressure appears.
13. Trust existing validators, config containers, and task bases when they already guarantee an invariant; do not add a second layer of fallback or correction.
14. For new Python-heavy flows, keep signatures and call sites compatible with at least basic static type checking.
15. Prefer deleting redundant imports, waits, and wrappers over preserving "explicit" but noisy scaffolding.
16. Use Conventional Commits for commit messages: `<type>(<scope>): <subject>`, with documented types such as `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `chore`, `build`, and `ci`.
17. Choose commit scope from the touched file name when one file changes, or from the parent folder name when multiple related files change.
18. For backend docstrings, use Google-style sections for summary, `Args`, `Returns`, and `Raises` when a function needs explanation.
19. For `ConfigBase` subclasses, comment every `ConfigItem` and group config items by clear section markers before `super().__init__()`.

## Comment Preservation
Do not treat cleanup as permission to strip comments. Preserve comments that explain business intent, operational steps, compatibility decisions, non-obvious invariants, maintainer context, or config-field meaning.

Only remove or rewrite a comment when it is stale, misleading, mechanically restates the next token of code, or refers to code that is being deleted in the same edit. When rewriting, keep the useful intent and make it shorter or more accurate instead of dropping it.

Protect these comments especially:
1. `ConfigItem` comments and section markers in `ConfigBase` subclasses.
2. Ordered workflow comments such as "第一步" and "第二步" in long service flows.
3. Task-injection, config-swap, log-monitoring, and compatibility notes in runtime code.
4. Frontend section comments that help scan large edit pages or distinguish type-specific logic.

## Avoid
1. Do not introduce framework-heavy abstractions or generic factories unless the surrounding module already uses them.
2. Do not hide the main workflow inside too many helper layers.
3. Do not switch comment or logging language inconsistently inside a file.
4. Do not turn a small fix into a broad refactor for stylistic purity.
5. Do not confuse "explicit" with "verbose".
6. Do not modify OpenAPI-generated files. Ask the developer to regenerate them manually when updates are required.
7. Do not split equivalent behavior into multiple methods or API routes when a dict selector or type field represents the difference directly.
8. Do not leave dead support paths for future detailed/raw config when there is no complete UI-to-runtime path yet.
9. Do not add maintainer-facing "safety" code that only repeats guarantees already enforced by base classes or validators.
10. Do not submit a versioned feature or fix without considering whether `res/version.json` needs a matching version-info entry under the next unreleased version.
11. Do not delete useful comments just to make a diff look cleaner.

## Review Checklist
1. The new code reads like neighboring `DLmaster_361` files.
2. Logs and comments are concise, operational, and consistent with the touched module.
3. The main path is still easy to trace top-to-bottom.
4. Compatibility and existing behavior were preserved unless the task explicitly changed them.
5. The chosen style lens matches the task: cleanup, feature landing, or dev integration.
6. Finite variant selection uses existing books/registries/dicts where that is clearer than method proliferation.
7. Config choices have one source of truth and do not duplicate existing mode/tab selectors.
8. New special cases were verified for this domain instead of cargo-culted from another module.
9. New code would survive basic static type checking without relying on `None` or fallback branches that conflict with declared types.
10. Commit messages and scopes follow the project convention when preparing commits.
11. Backend comments and config-class annotations use the project style rather than ad hoc prose.
12. Existing useful comments were preserved or updated accurately, not removed as noise.
