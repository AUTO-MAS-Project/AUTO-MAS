---
name: mas-api-contract
description: Define FastAPI HTTP/WebSocket contracts in app/api and shared app/models/schema.py, including config-derived payloads, partial updates, stable envelopes, errors, and client compatibility.
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
2. Endpoint-local request/response models in `app/api/` and shared contracts in `app/models/schema.py`.
3. WebSocket message contracts used by backend services.

Current `dev` baseline:
1. Keep FastAPI responses aligned with `OutBase`-style envelopes used in `app/models/schema.py`.
2. Keep WebSocket contracts aligned with current envelope conventions already used by `app/api/core.py` and WS command routes.

## MCP Surface
The backend exposes an MCP server derived from the live OpenAPI schema. Know these facts before changing API surface:

1. `main.py` mounts it with `fastapi_mcp.FastApiMCP(...).mount_http()`, so the transport is streamable HTTP at `/mcp`. It is not an SSE endpoint; do not describe or document it as one.
2. Mounting is gated by `AUTO_MAS_ENABLE_MCP` (default `"1"`) and happens in background initialization after `lifespan` yields. The route is absent until that finishes, so an early request can legitimately 404.
3. MCP tools are generated from the full OpenAPI schema with `describe_full_response_schema=True` and `describe_all_responses=True`. Every route you add, rename, or retype becomes an MCP tool signature automatically, and schema churn is user-visible through this surface as well as through the generated frontend client.
4. `exclude_tags=["Delete"]` keeps destructive routes out of MCP. A destructive endpoint must carry `tags=["Delete"]` to stay excluded; path or method naming alone does not exclude it.
5. Treat `/mcp` and its tool names as an external contract. Route path, `operation_id`, and tag changes are breaking for MCP clients even when the HTTP API stays compatible.

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
7. Define endpoint-specific `*In`/`*Out` and private submodels at the top of their owning API module, before route functions. Cross-module or business-layer contracts remain in single-file `app/models/schema.py`; routers do not import other routers for shared models.
8. Create routes in the corresponding `app/api/` module and keep route handlers as thin transport adapters around schema models and backend calls.

## Config Payload Contracts
For config endpoints, read [the configuration framework reference](../mas-data-model/references/config-framework.md).

1. Derive fields from the actual config class using `ConfigInput[T]`, `StrictConfigInput[T]`, `ConfigPayload[T]` or `config_contract()` in `app/config/wire.py`; no duplicate config field/group models or `schema_class` registry entries.
2. Validate requests with pure contracts; request parsing does not activate or persist configs. Convert patches with `model_dump(exclude_unset=True)` so omission and explicit null remain distinct. Do not use a full default-filled dump or `exclude_none=True` for partial updates.
3. Apply the patch through the existing endpoint's permitted entry/collection operations. Preserve hidden/disabled/virtual-field rules, masked-value retention and business locks. `update()` changes provided Entry fields, not nested collections; batch atomicity requires an explicit transaction.
4. Output types must describe actual recursive payloads and `order/data` collection structure. JSON paths are strings or null; date/time storage exports UTC with timezone information. Keep existing route paths, envelopes, tags and MCP semantics.
5. A successful commit is not a disk-save guarantee. `flush()` and manager export run outside transactions; exports read registered stable live configs rather than stale files. Framework UI metadata does not by itself authorize new frontend interactions.

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
6. Treat documented local integration entrypoints as compatibility surfaces too; do not rename or repurpose stable paths such as the MCP endpoint without an explicit migration plan.
7. After backend API changes, regenerate frontend API clients by running `yarn openapi` in `frontend/` (it targets the development backend port) instead of hand-editing generated TypeScript.
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
