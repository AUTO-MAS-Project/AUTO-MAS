---
name: mas-data-model
description: Define AUTO-MAS backend models and configuration framework usage. Use for app/models, app/config, config field declarations, stage/commit callers, transactions, signals, locks, persistence, and config contract evolution.
---

# MAS Data Model

## Objective
Build backend data models that are explicit, consistent, and evolution-friendly.

## Scope
Apply to model definitions and configuration usage:
1. Shared API contracts (`app/models/schema.py`) and endpoint-local contracts (`app/api/`)
2. Persisted/runtime config models (`app/models/config/`) and framework/callers (`app/config/`)
3. task/runtime state models (`task`)

## Configuration Framework
For config definitions, reads/writes, lifecycle, transactions, locks, signals, persistence, API projections or historical upgrades, read [config-framework.md](references/config-framework.md) before implementation. It records the framework invariants and points to current source and the developer manual. Ordinary schema/task-only work does not require this reference.

Configuration fields are declared once in `ConfigEntry`/`ConfigGroup`; collections use `ConfigCollection[T]`. Hot writes stage whole-field or collection operations, then await `commit()`. Per-op transactions, explicit transaction boundaries and persistence completion are distinct contracts. Framework design changes follow existing user authorization; explain and obtain a decision for unapproved design changes before editing the base implementation.

## Model Ownership
1. Shared `schema.py` and endpoint-local models define external API contracts; config projections derive from config classes through `app/config/wire.py`.
2. `config` models define persisted configuration structure and validation behavior.
3. `task` models define runtime execution state and orchestration-facing status.
4. Do not mix transport, persistence, and runtime concerns in one model class.
5. `ConfigEntry` subclasses contain `ConfigGroup` fields declared with typed Pydantic `Field` definitions and Chinese descriptions. Defaults and mutable values use suitable factories.
6. `ConfigCollection[T]` records allowed concrete entry types; nested collections are declared through `collection(...)`. Runtime state belongs in `PrivateAttr`, class constants in `ClassVar`.

## Structure And Types
1. Use nested group models for meaningful domains (`Info`, `Run`, `Notify`, `Data`).
2. Keep shared semantics aligned with `mas-schema-naming`.
3. Keep domain-specific fields inside dedicated domain blocks.
4. Keep index items and payload models separated.
5. Prefer concrete types over `Any`.
6. Use `Literal` or explicit enums for bounded value sets.
7. Use optional types only when missing value has real business meaning.
8. Avoid stringly-typed booleans/numbers in new model fields.
9. Config date/time fields use complete `datetime`: UTC storage, naive input interpreted as UTC, `tz(...)` controls attribute reads, and serialization exports stored UTC. UI formatting does not truncate values.
10. When a field is optional by omission, prefer absence over sentinel values that violate the declared type.

## Defaults And Validation
1. Use safe defaults for collection fields (`default_factory` when mutable).
2. Use `None` defaults only for truly optional semantics.
3. Avoid hidden execution-policy changes in defaults.
4. Keep validation close to model definition.
5. Keep correction/normalization deterministic.
6. Do not encode high-level business workflow in low-level field validators.
7. Reuse guarantees from config containers and declarative fields, including reference existence/type validation through `ref(...)`; validate only business invariants not already covered.
8. Favor validators that reject or normalize one missing invariant, not "just in case" fallbacks for impossible states.
9. Pydantic constraints reject invalid input; standard `Annotated` types provide explicitly defined normalization/default fallback. Keep those semantics distinct and avoid external corrector arguments.
10. Computed config fields use `Virtual[T]` plus `@virtual_field(...)`. Reactive fields, UI visibility, encryption and legacy conversion have separate declarations described in the config reference.

## Relationships And Sensitive Data
1. Keep IDs typed consistently as strings in API-facing schema unless migration is planned.
2. Keep relation fields explicit (`scriptId`, `userId`, `queueId`).
3. Keep index models lightweight and independent of heavy payload models.
4. Avoid duplicating relationship semantics with synonym fields.
5. Mark and isolate sensitive fields clearly (`password`, `token`, `key`).
6. Avoid exposing sensitive values in response models unless explicitly required.
7. Keep encryption/decryption policy out of schema contracts and in proper model/service layers.

## Evolution And Compatibility
1. Prefer additive model changes over breaking removals.
2. Keep backward read compatibility during rename migrations.
3. Config field compatibility uses `legacy(group=..., name=..., convert=...)`; document-structure and database upgrades belong to startup upgrade orchestration.
4. Avoid adding a second config field for the same user choice.
5. If modes are mutually exclusive, merge them into one selector and make downstream toggling explicit.
6. If modes are not mutually exclusive, keep one existing selector as the source of truth.
7. Do not introduce future raw-config save fields or detailed-mode markers until persistence, UI, and runtime consumption all exist.
8. Do not add placeholders for a future config surface when the product still lacks the corresponding edit entry or consumer.

## Anti-Patterns
1. One model serving unrelated responsibilities across layers.
2. New fields duplicating existing semantics with different names.
3. Validator logic performing network/file/process side effects.
4. Unbounded `Dict[str, Any]` replacing known structured fields.
5. Large domain policies hidden in model defaults.
6. Defensive validators re-checking invariants enforced by lower-level config containers.
7. Separate config options forcing users to choose the same domain concept twice.
8. Optional fields represented by invalid placeholder values instead of omission or a correct union type.
9. In-place container mutations, direct `order/data` edits, or whole-group replacement that bypass field staging, locks, signals and rollback.
10. Adding a config class without its owning collection/registry, dependency activation order, derived API contract or actual consumer.

## Review Checklist
1. Model belongs to the correct layer (`schema/config/task`).
2. Field naming aligns with canonical shared semantics.
3. Types and optionality express real business meaning.
4. Defaults are safe and behaviorally stable.
5. Constraints are explicit and deterministic.
6. Sensitive fields are protected from accidental exposure.
7. Change is backward-compatible or includes migration handling.
8. Placement follows `mas-module-boundary` and API usage follows `mas-api-contract`.
9. New validators check only missing invariants, not guarantees already provided by base containers.
10. New config fields do not duplicate an existing selector or tab/mode choice.
11. Optionality is expressed by the type system or field absence, not by values that conflict with the declared type.
12. Config fields have exact types/defaults/Chinese descriptions in semantic `ConfigGroup` blocks and remain the single source for API projections.
13. Collections declare allowed entry types, reference targets are registered before dependent activation, and partial updates preserve omission/null/masked-value semantics.
14. Changes respect the transaction, whole-field assignment, signal, lock and persistence invariants in the config reference; verification uses isolated files and external-service substitutes.
