---
name: mas-data-model
description: Define backend data modeling standards for Python services. Use when designing or refactoring models in app/models (schema/config/task), normalizing shared fields, choosing types/defaults/validation strategy, and evolving model contracts with backward compatibility.
---

# MAS Data Model

## Objective
Build backend data models that are explicit, consistent, and evolution-friendly.

## Scope
Apply to model definitions under `app/models`:
1. API contract models (`schema`)
2. persisted/runtime config models (`config`, `ConfigBase`)
3. task/runtime state models (`task`)

## Model Ownership
1. `schema` models define external API contracts only.
2. `config` models define persisted configuration structure and validation behavior.
3. `task` models define runtime execution state and orchestration-facing status.
4. Do not mix transport, persistence, and runtime concerns in one model class.
5. `ConfigBase` subclasses define real persisted config templates; every `ConfigItem` must be declared before `super().__init__()` to be indexed, settable, and saved.
6. `MultipleConfig` represents a dictionary-like collection of `ConfigBase` instances and must be declared with all allowed concrete config classes.

## Structure And Types
1. Use nested group models for meaningful domains (`Info`, `Run`, `Notify`, `Data`).
2. Keep shared semantics aligned with `mas-schema-naming`.
3. Keep domain-specific fields inside dedicated domain blocks.
4. Keep index items and payload models separated.
5. Prefer concrete types over `Any`.
6. Use `Literal` or explicit enums for bounded value sets.
7. Use optional types only when missing value has real business meaning.
8. Avoid stringly-typed booleans/numbers in new model fields.
9. Keep datetime/time fields format-stable and documented.
10. When a field is optional by omission, prefer absence over sentinel values that violate the declared type.

## Defaults And Validation
1. Use safe defaults for collection fields (`default_factory` when mutable).
2. Use `None` defaults only for truly optional semantics.
3. Avoid hidden execution-policy changes in defaults.
4. Keep validation close to model definition.
5. Keep correction/normalization deterministic.
6. Do not encode high-level business workflow in low-level field validators.
7. Do not duplicate validation already guaranteed by config manager or collection base classes; validate only the invariant still at risk, such as referenced `uuid` existence.
8. Favor validators that reject or normalize one missing invariant, not "just in case" fallbacks for impossible states.
9. Treat config validators as auto-correction behavior, not just passive checks: `RangeValidator`, `OptionsValidator`, `BoolValidator`, path validators, `EncryptValidator`, `VirtualConfigValidator`, and `MultipleUIDValidator` can rewrite stored values.
10. Use `VirtualConfigValidator(function)` for computed display/config fields that should be read through normal config access but must not be set or persisted as user input.

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
3. Keep API conversion logic explicit when old/new fields coexist.
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
9. Defining config fields after `super().__init__()` and expecting them to participate in normal config load/save behavior.
10. Adding a config class to one layer while forgetting the corresponding `GlobalConfig` collection, `CLASS_BOOK`/registry entry, schema type, or API handling.

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
12. Config classes document every `ConfigItem` with nearby comments and are grouped by `Info`, `Run`, `Task`, `Data`, `Notify`, or the local domain grouping used by neighbors.
13. New multi-config relationships include the allowed classes in `MultipleConfig([...])` and any needed UID-reference field points at the owning collection.
