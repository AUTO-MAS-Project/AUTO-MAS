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
   Defines API-facing schedule schemas and shared aliases:
   `WeeklyPlanConfig`, `PlanConfigType`, `PlanCreateType`, `PlanConfigData`, `PlanComboxConsumer`.
2. `app/models/config.py`
   Defines concrete `ConfigBase` schedule classes such as `MaaPlanConfig` and `MaaEndPlanConfig`.
   Registers them in `PLAN_BOOK`.
3. `app/core/config.py`
   Uses `PLAN_BOOK` to create plans, delete referenced plans, filter combobox options by consumer, and wire `GlobalConfig.PlanConfig`.
4. `app/api/plan.py`
   Uses schema models plus `PLAN_BOOK` for plan CRUD serialization.
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
   Create a concrete `ConfigBase` plan class in `app/models/config.py`.
   Add `ConfigItem` fields before `super().__init__()`.
   Reuse `WeeklyPlanConfig` only if the new type has the same `Info + ALL + weekdays` shape.
2. Add backend schema
   Create the matching Pydantic schema item/info classes in `app/models/schema.py`.
   Extend `PlanConfigType`, `PlanCreateType`, and `PlanConfigData`.
   Keep `model_config = ConfigDict(extra="forbid")` on schedule config models.
3. Register in `PLAN_BOOK`
   Add `create_type`, `config_class`, `schema_class`, `consumer`, `script_class`, and `field_name`.
   This is the backend source of truth for plan CRUD, deletion reference cleanup, and combobox filtering.
4. Wire the user consumer
   Add or extend the user config field that stores the selected plan ID.
   Use type-specific validation or runtime type checks before dereferencing the plan as a concrete class.
   When deleting a plan, `field_name` should be reset only for the bound consumer type.
5. Add frontend descriptor
   Register the type in `frontend/src/utils/planTypeRegistry.ts`.
   Use generated OpenAPI enum values from `@/api`.
   Point `tableComponent` to the type-specific table component.
6. Add frontend table
   Create a dedicated table component under `frontend/src/views/plan/tables/`.
   Keep per-type field logic in the table or a type-specific utility/composable.
   Do not build a generic field renderer unless multiple real schedule types share the same behavior.
7. Regenerate OpenAPI client
   Never edit generated files under `frontend/src/api/` by hand.
   Ask the developer to run the project API generation command after backend schema changes.

## Review Checklist
Use this checklist for plan schedule PRs.

1. `PLAN_BOOK` is the only backend registration source for supported plan config classes.
2. `PlanConfigType`, `PlanCreateType`, and `PlanConfigData` match registered backend types.
3. Plan CRUD does not default unknown types to `MaaPlan`.
4. Consumer comboboxes only return plans of the matching config class.
5. Deleting a plan only clears the matching user reference field.
6. Frontend type labels, default names, create types, and table components come from `planTypeRegistry.ts`.
7. Unknown plan types fail clearly instead of rendering as a different known type.
8. Type-specific table behavior stays in the type-specific table or nearby type-specific utility.
9. No plan schedule types are redefined in `script.ts` or generated OpenAPI files.
10. New fallback paths are justified by production compatibility needs, not by non-production leftovers.

## Avoid
1. Do not add `GeneralPlan`, `CustomPlan`, or placeholder mappings without a complete backend, frontend, and user consumption path.
2. Do not add a shared schedule field engine for one or two unrelated tables.
3. Do not create a new wrapper/helper that is only called once if the current flow stays clearer inline.
4. Do not preserve deleted compatibility routes unless the feature has shipped and needs migration support.
5. Do not duplicate generated API types in hand-written frontend files.
