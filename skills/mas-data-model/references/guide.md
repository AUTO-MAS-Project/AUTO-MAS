# mas-data-model（完整说明）

对应 Skill：`mas-data-model`。来源：AUTO-MAS-Project/skills。

---

# MAS Data Model

## Objective
Build backend data models that are explicit, consistent, and evolution-friendly.

## Global Constraints
Apply these constraints while using this skill.

1. Make minimal necessary changes first; avoid broad refactors unless explicitly requested.
2. Align with current code style and existing project conventions in the touched module.
3. Avoid over-engineering, over-abstraction, and defensive programming that does not match existing code patterns.
4. Study similar existing implementations deeply before coding and follow established local patterns.

## Scope
Apply to model definitions under `app/models`, including:

1. API contract models (schema).
2. persistent/runtime config models.
3. task/runtime state models.

Current `dev` baseline:
1. API schemas are primarily in `app/models/schema.py` and use `OutBase` response envelopes.
2. Persisted config modeling is centered on `app/models/config.py` + `app/models/ConfigBase.py`.
3. Runtime execution state models are in `app/models/task.py`.

## Model Ownership
1. `schema` models define external API contracts only.
2. `config` models define persisted configuration structure and validation behavior.
3. `task` models define runtime execution state and orchestration-facing status.
4. Do not mix transport, persistence, and runtime concerns in one model class.

## Canonical Model Structure
1. Use nested group models for meaningful domains (`Info`, `Run`, `Notify`, `Data`).
2. Keep shared semantics with canonical names from `mas-schema-naming`.
3. Keep domain-specific fields inside dedicated domain blocks.
4. Keep index items and data payload models separated.

## Type Design Rules
1. Prefer concrete types over `Any` whenever possible.
2. Use `Literal` or explicit enums for bounded value sets.
3. Use optional types only when missing value has real semantic meaning.
4. Avoid stringly-typed booleans/numbers in new model fields.
5. Keep datetime/time fields format-stable and documented.

## Default Value Rules
1. Use safe defaults for collection fields (`default_factory` when mutable).
2. Use `None` defaults only for truly optional business semantics.
3. Avoid hidden behavior in defaults that changes execution policy.
4. Keep default value meaning stable across versions.

## Validation And Constraints
1. Keep validation close to model definition.
2. Use constrained fields (`Literal`, range constraints, format constraints) for contract safety.
3. Keep correction/normalization deterministic.
4. Do not encode high-level business workflow in low-level field validators.

## ID And Relationship Rules
1. Keep IDs typed consistently as strings in API-facing schema unless migration is planned.
2. Keep relation fields explicit (`scriptId`, `userId`, `queueId`, etc.).
3. Keep index models lightweight and independent of heavy payload models.
4. Avoid duplicating relationship semantics with synonym fields.

## Sensitive Data Rules
1. Mark and isolate sensitive fields clearly (password/token/key).
2. Avoid exposing sensitive values in response models unless explicitly required.
3. Keep serialization/logging paths sanitized.
4. Keep encryption/decryption policy out of schema contracts and in proper model/service layers.

## Evolution And Compatibility
1. Prefer additive model changes over breaking removals.
2. Keep backward read compatibility during rename migrations.
3. Deprecate old fields with clear transition strategy.
4. Keep API layer conversion logic explicit when old/new fields coexist.

## Serialization Rules
1. Keep serialization shape stable for API consumers.
2. Avoid implicit cross-layer transformations inside model classes.
3. Keep model-to-model mapping explicit at boundary functions.
4. Use consistent naming style per model family and contract.

## Anti-Patterns (Reject In Review)
1. One model serving unrelated responsibilities across layers.
2. New fields duplicating existing semantics with different names.
3. Validator logic performing network/file/process side effects.
4. Unbounded `Dict[str, Any]` replacing known structured fields.
5. Large domain policies hidden in model defaults.

## Data Model Review Checklist
1. Model belongs to the correct layer (`schema/config/task`).
2. Field naming aligns with canonical shared semantics.
3. Types and optionality express real business meaning.
4. Defaults are safe and behaviorally stable.
5. Constraints are explicit and deterministic.
6. Sensitive fields are protected from accidental exposure.
7. Change is backward-compatible or includes migration handling.
8. Placement follows `mas-module-boundary` and API usage follows `mas-api-contract`.
