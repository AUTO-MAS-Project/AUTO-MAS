---
name: mas-plan-schedule
description: Use when adding, refactoring, or reviewing AUTO-MAS plan schedule types, including backend PlanConfig registration, plan API/schema contracts, plan combobox consumers, frontend plan type registry, and per-plan table integration.
---

# MAS Plan Schedule

## Objective
Keep AUTO-MAS plan schedules easy to extend without turning them into a generic field engine. Each schedule type owns its data model, config class, table UI, and user consumption path. Shared code should only cover type registration, API dispatch, list selection, and CRUD orchestration.

## Current Architecture
Backend has one shared multi-config collection and one lightweight registration table.

1. `app/models/schema.py`
   Holds shared plan-key payloads and `PlanComboxConsumer`, consumed across API/business modules.
2. `app/models/config/plan.py` and `app/models/config/__init__.py`
   Define concrete `DomainEntry`/`ConfigEntry` schedule classes and their `ConfigGroup` fields; the package initializer owns `PLAN_BOOK` and public exports.
3. `app/core/config/manager.py`
   Uses `PLAN_BOOK` to create plans, delete referenced plans, filter combobox options by consumer, and wire `GlobalConfig.PlanConfig`.
4. `app/api/plan.py`
   Owns plan endpoint models and `PlanConfigType/PlanCreateType/PlanConfigData/PlanConfigDataInput`. Payloads derive from config classes using `ConfigPayload` and `StrictConfigInput`, plus `PLAN_BOOK` for dispatch.
5. `app/api/info.py`
   Exposes consumer-specific plan combobox routes through `PlanComboxIn.consumer`.

Frontend has one runtime descriptor registry and separate table implementations.

1. `frontend/src/utils/planTypeRegistry.ts`
   Owns runtime plan descriptors: config type, create type, label, default name, selector tag, reload behavior, and table component.
2. `frontend/src/views/plan/index.vue`
   Orchestrates plan list state, current plan selection, CRUD calls, name editing, and table dispatch.
3. `frontend/src/views/plan/tables/*.vue`
   Owns concrete table UI and per-type field behavior.
4. `frontend/src/composables/usePlanApi.ts`
   Wraps plan API calls. Do not duplicate generated OpenAPI models here.
5. `frontend/src/utils/planNameUtils.ts`
   Reads the registry for labels/default names.

## Where Things Belong
Use `types/` for type-only shapes that are not already exported by OpenAPI.
Use `utils/` or a feature folder for runtime registries, constants, validators, and label maps.

`planTypeRegistry.ts` is runtime code because it imports Vue `defineAsyncComponent` and generated API enum values. Do not move it into `types/` unless it is split into a type-only file and a runtime registry file.

Do not put plan schedule types in `frontend/src/types/script.ts`. Script types and schedule types are separate domains.

## Adding A New Schedule Type
Follow this order.

1. Add backend config class
   Declare the plan in `app/models/config/plan.py` using typed `ConfigGroup` fields and factories. Follow [the configuration framework reference](../mas-data-model/references/config-framework.md); reuse weekly plan behavior only when the actual group/key shape matches.
2. Derive backend contracts
   Add the config class's `ConfigPayload` and `StrictConfigInput` projections in `app/api/plan.py`; extend `PlanConfigType`, `PlanCreateType`, `PlanConfigData` and `PlanConfigDataInput` there. Strict unknown-field rejection belongs to the input contract, not a global config model policy. Shared plan keys/consumer aliases stay in `schema.py`; configuration fields are not copied into it.
3. Add the consumer constant
   Append the new consumer string to `PLAN_CONSUMER_VALUES` in `app/utils/common/constants.py`.
   `PLAN_BOOK` does not hold consumer literals directly; it indexes this tuple (`PLAN_CONSUMER_VALUES[0]`, `[1]`, ...), so a new type has nothing to reference until the tuple grows.
   This tuple and the `PlanComboxConsumer` literal in `app/models/schema.py` are two independent hardcoded lists of the same values with no generated link. Update both, and keep them in the same order — existing `PLAN_BOOK` entries reference the tuple positionally, so inserting rather than appending silently repoints existing plan types at the wrong consumer.
4. Register in `PLAN_BOOK`
   Add `create_type`, `config_class`, `consumer`, `script_class`, `field_group`, and `field_name`. API contracts derive from `config_class`; the registry stores config classes and business relationships.
   This is the backend source of truth for plan CRUD, deletion reference cleanup, and combobox filtering.
5. Wire the user consumer
   Add or extend the user config field that stores the selected plan ID.
   Use a typed `ref(...)` when appropriate, plus consumer-specific runtime checks before dereferencing a concrete plan. Reference targets are registered before dependent activation.
   When deleting a plan, `field_name` should be reset only for the bound consumer type.
6. Add frontend descriptor
   Register the type in `frontend/src/utils/planTypeRegistry.ts`.
   Use generated OpenAPI enum values from `@/api`.
   Point `tableComponent` to the type-specific table component.
7. Add frontend table
   Create a dedicated table component under `frontend/src/views/plan/tables/`.
   Keep per-type field logic in the table or a type-specific utility/composable.
   Do not build a generic field renderer unless multiple real schedule types share the same behavior.
8. Regenerate OpenAPI client
   Never edit generated files under `frontend/src/api/` by hand.
   Run the project API generation command after backend contract changes; report concrete generation blockers rather than hand-editing output.
   Frontend plan types derive from generated OpenAPI (`PlanIndexItem.type`, `PlanCreateIn.type`), so the registry cannot see a new type until regeneration runs.

## Review Checklist
Use this checklist for plan schedule PRs.

1. `PLAN_BOOK` is the only backend registration source for supported plan config classes.
2. Endpoint-local type/create/input/output aliases and shared `PlanComboxConsumer` agree with registered types; config fields have one declaration source.
3. `PLAN_CONSUMER_VALUES` in `app/utils/common/constants.py` and the `PlanComboxConsumer` literal agree in both content and order, and existing `PLAN_BOOK` positional indexes still point at their original consumers.
4. Plan CRUD does not default unknown types to `MaaPlan`.
5. Consumer comboboxes only return plans of the matching config class.
6. Deleting a plan only clears the matching user reference field.
7. Frontend type labels, default names, create types, and table components come from `planTypeRegistry.ts`.
8. Unknown plan types fail clearly instead of rendering as a different known type.
9. Type-specific table behavior stays in the type-specific table or nearby type-specific utility.
10. No plan schedule types are redefined in `script.ts` or generated OpenAPI files.
11. New fallback paths are justified by production compatibility needs, not by non-production leftovers.

## Avoid
1. Do not add `GeneralPlan`, `CustomPlan`, or placeholder mappings without a complete backend, frontend, and user consumption path.
2. Do not add a shared schedule field engine for one or two unrelated tables.
3. Do not create a new wrapper/helper that is only called once if the current flow stays clearer inline.
4. Do not preserve deleted compatibility routes unless the feature has shipped and needs migration support.
5. Do not duplicate generated API types in hand-written frontend files.
