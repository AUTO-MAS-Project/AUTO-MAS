---
name: mas-schema-naming
description: Define canonical naming for future backend schema domains. Use when creating new specialized schema models or extending Pydantic contracts in app/models/schema.py, standardizing shared Info/Data/Notify/Run semantics, and avoiding new naming drift without forcing retroactive changes on legacy modules.
---

# MAS Schema Naming

## Objective
Standardize naming for future specialized backend schema implementations.

This skill constrains new domain work by default. It does not require retroactive renaming of existing legacy modules unless explicitly requested.

## Global Constraints
Apply these constraints while using this skill.

1. Make minimal necessary changes first; avoid broad refactors unless explicitly requested.
2. Align with current code style and existing project conventions in the touched module.
3. Avoid over-engineering, over-abstraction, and defensive programming that does not match existing code patterns.
4. Study similar existing implementations deeply before coding and follow established local patterns.

## Apply Workflow
1. Determine whether the field is shared semantic or domain-specific semantic.
2. For shared semantic, use the canonical name from this skill.
3. For domain-specific semantic, keep naming local to the domain block.
4. Keep public config-model field style consistent: `PascalCase`.
5. When touching legacy modules, prefer compatibility-first edits and avoid broad rename-only refactors.

## Canonical Structure For New Domains
Use this top-level structure for new script/user schema models.

```python
class XxxConfig(BaseModel):
    Info: XxxConfig_Info | None
    Run: XxxConfig_Run | None
    Emulator: XxxConfig_Emulator | None  # only if emulator semantics exist

class XxxUserConfig(BaseModel):
    Info: XxxUserConfig_Info | None
    Data: XxxUserConfig_Data | None
    Notify: XxxUserConfig_Notify | None
    # optional domain blocks, e.g. Task/Stage/Game
```

## Shared Naming Matrix
Use these names when semantics are the same.

| Semantic | Canonical name | Block |
| --- | --- | --- |
| Script display name | `Name` | `Info` |
| Script runtime path | `Path` | `Info` |
| Emulator id | `Id` | `Emulator` |
| Emulator index | `Index` | `Emulator` |
| Transition strategy | `TaskTransitionMethod` | `Run` |
| Daily proxy limit | `ProxyTimesLimit` | `Run` |
| Retry limit | `RunTimesLimit` | `Run` |
| Runtime timeout | `RunTimeLimit` | `Run` |
| User display name | `Name` | `User.Info` |
| User id | `Id` | `User.Info` |
| User enabled status | `Status` | `User.Info` |
| Remaining day budget | `RemainedDay` | `User.Info` |
| User note | `Notes` | `User.Info` |
| User tag payload | `Tag` | `User.Info` |
| Last proxy date | `LastProxyDate` | `User.Data` |
| Proxy run count | `ProxyTimes` | `User.Data` |
| Manual-check result | `IfPassCheck` | `User.Data` |
| Notify enabled | `Enabled` | `User.Notify` |
| Send statistic | `IfSendStatistic` | `User.Notify` |
| Send mail | `IfSendMail` | `User.Notify` |
| Mail receiver | `ToAddress` | `User.Notify` |
| ServerChan enabled | `IfServerChan` | `User.Notify` |
| ServerChan key | `ServerChanKey` | `User.Notify` |

## Boundary For Domain-Specific Names
1. Keep domain-specific semantics inside dedicated domain blocks.
2. Do not force shared naming when semantics differ.
3. Do not add synonym fields for the same semantic in one block.

## Drift To Avoid In New Work
1. Same semantic, different names (`Path` vs `RootPath`).
2. Same semantic, different block placement (`Data` vs `Info`).
3. Same semantic, mixed boolean style in the same block.

## Compatibility Rule
When canonicalizing an existing public field:

1. Keep read compatibility for legacy payloads during migration.
2. Prefer writing canonical names in new responses.
3. Remove legacy names only after consumer migration is complete.

## PR Checklist
1. New specialized schema models follow this canonical matrix for shared semantics.
2. Domain-specific fields stay in domain-specific blocks.
3. No new synonym names are introduced for existing shared semantics.
4. Legacy modules are not renamed in bulk unless explicitly in scope.
