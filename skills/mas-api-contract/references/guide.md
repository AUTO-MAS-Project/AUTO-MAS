# mas-api-contract（完整说明）

对应 Skill：`mas-api-contract`。来源：AUTO-MAS-Project/skills。

---

# MAS API Contract

## Objective
Keep backend API interfaces stable, consistent, and easy to consume.

## Global Constraints
Apply these constraints while using this skill.

1. Make minimal necessary changes first; avoid broad refactors unless explicitly requested.
2. Align with current code style and existing project conventions in the touched module.
3. Avoid over-engineering, over-abstraction, and defensive programming that does not match existing code patterns.
4. Study similar existing implementations deeply before coding and follow established local patterns.

## Scope
Apply to:

1. HTTP endpoints under `app/api/*`.
2. Request/response schema models in `app/models/schema.py`.
3. WebSocket message contracts used by backend services.

Current `dev` baseline:
1. Keep FastAPI responses aligned with `OutBase`-style envelopes used in `app/models/schema.py`.
2. Keep WebSocket contracts aligned with current envelope conventions already used by `app/api/core.py` and WS command routes.

## Contract Principles
1. Keep one clear contract per endpoint action.
2. Keep request and response types explicit and version-safe.
3. Keep error semantics predictable across endpoints.
4. Keep compatibility-first behavior for public contract changes.

## Endpoint Naming Rules
1. Use resource-oriented prefixes: `/api/<resource>`.
2. Keep action suffixes explicit for non-CRUD operations (`/start`, `/stop`, `/reorder`).
3. Keep endpoint names concise and unambiguous.
4. Avoid introducing equivalent endpoints with different verbs/paths.

## Request/Response Schema Rules
1. Use `*In` for request models.
2. Use `*Out` for response models.
3. Use shared `OutBase` for common response envelope fields when applicable.
4. Bind endpoint `response_model` explicitly.
5. Do not return raw untyped dicts if a schema model exists.

## Field Naming Rules
1. Keep external API fields stable and consistent per established style.
2. Reuse canonical shared semantic names via `mas-schema-naming`.
3. Avoid introducing synonym fields for the same semantic.
4. Keep ID fields consistent by entity (`scriptId`, `queueId`, `userId`, etc.).

## Error Contract Rules
1. Return deterministic error structure (`code`, `status`, `message`) for handled failures.
2. Convert domain exceptions at API boundary only.
3. Keep human-readable message plus machine-usable code.
4. Avoid leaking internal stack details in API response payloads.

## Status Code And Result Semantics
1. Use API-level success response only when operation contract succeeds.
2. Keep business-level failure represented in standardized error response.
3. Keep the same endpoint semantics across modules (scripts/queue/plan/emulator).

## WebSocket Contract Rules
1. Keep message envelope stable (`id`, `type`, `data`).
2. Keep signal/update/info/message type semantics explicit and documented.
3. Keep WS command payload contract aligned with HTTP command equivalents when both exist.
4. Keep heartbeat and close semantics centralized in core WS flow.

## Compatibility And Evolution
1. Prefer additive changes over breaking changes.
2. Deprecate fields/endpoints with transition period.
3. Keep backward read compatibility when renaming request fields.
4. Document any breaking contract change before merge.

## Layer Boundary Rules
1. `api` layer owns transport contract mapping only.
2. `schema` layer owns model definitions only.
3. `core/task/services` own business execution and integration logic.
4. Apply `mas-module-boundary` for placement and dependency checks.

## API Review Checklist
1. Endpoint path/action naming is clear and non-duplicative.
2. `*In/*Out` models are present and explicit.
3. `response_model` is declared.
4. Error contract shape is consistent.
5. Field names align with existing canonical semantics.
6. WebSocket payload changes preserve envelope compatibility.
7. Contract changes include compatibility notes.
