---
name: mas-api-contract
description: Define backend API contract standards for FastAPI services. Use when adding or refactoring HTTP/WebSocket endpoints in app/api, designing request/response schemas in app/models/schema.py, standardizing status/error contracts, and maintaining backward compatibility for clients.
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
5. For `POST` query-style endpoints such as combobox/list options, prefer one endpoint with an explicit request-body discriminator over splitting equivalent endpoints by implementation type.
6. Do not create parallel paths like `/xxx-foo` and `/xxx-bar` solely because the backend reads different config books; keep the path semantic stable and put the selected type in the body.

## Request/Response Schema Rules
1. Use `*In` for request models.
2. Use `*Out` for response models.
3. Use shared `OutBase` for common response envelope fields when applicable.
4. Bind endpoint `response_model` explicitly.
5. Do not return raw untyped dicts if a schema model exists.
6. When a request needs to choose between known plan/script/config families, model that selector explicitly instead of encoding it in the URL path or handler name.
7. Define or update request/response data models in `app/models/schema.py` before wiring a new route.
8. Create routes in the corresponding `app/api/` module and keep route handlers as thin transport adapters around schema models and backend calls.

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
5. For OpenAPI-exposed schema fields already consumed by generated frontend clients, avoid rewriting a stable flat `Literal[...]` field into `Union[...]` plus shared type aliases unless you have verified that the generated TypeScript runtime exports remain unchanged.
6. Treat documented local integration entrypoints as compatibility surfaces too; do not rename or repurpose stable paths such as the documented MCP SSE endpoint without an explicit migration plan.
7. After backend API changes, regenerate frontend API clients from `http://127.0.0.1:36163/openapi.json` with `openapi --output ./src/api --client axios` instead of hand-editing generated TypeScript.
8. When testing new API calls from the frontend, remember that plain `yarn dev` can use the remote `dev` backend; start the local backend first when verifying local API changes.

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
8. `POST` endpoints do not multiply paths when a body selector would keep the contract simpler.
9. Changes to documented localhost endpoints or startup assumptions were reviewed for user- and tool-facing compatibility, not just backend correctness.
10. OpenAPI regeneration is handled as a separate generated-code step, and generated files are not manually edited.
