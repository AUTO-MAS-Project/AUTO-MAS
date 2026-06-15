# Style Observations

## Evidence Base
Primary commit evidence for this skill:

1. `e541fa5f923dae8e6e6c24493a09d4d243aa2186`
2. `727aafbaf5e21fc81e85e795a5cd5b77ac508e60`
3. `e5d72bdb6f7bcade4ea6bf7dbcbfdaa55918ca7c`

The clearest file-level samples from those commits and surrounding `dev` code are:

1. `frontend/electron/services/backendService.ts`
2. `frontend/electron/services/dependencyService.ts`
3. `frontend/electron/services/environmentService.ts`
4. `frontend/electron/services/mirrorService.ts`
5. `frontend/electron/services/mirrorRotationService.ts`
6. `frontend/electron/services/initializationService.ts`
7. `frontend/electron/ipc/initializationHandlers.ts`
8. `frontend/src/views/Initialization/index.vue`
9. `app/task/MaaEnd/AutoProxy.py` at `e541fa5f`
10. `app/core/config.py`, `app/models/config.py`, `app/models/schema.py`, `app/task/SRC/manager.py`, `app/task/SRC/tools/notify.py` at `727aafb`
11. `frontend/src/views/EditView/Script/SRCScriptEdit.vue` and `frontend/src/views/SRCUserEdit/BasicInfoSection.vue` at `727aafb`
12. `app/api/scripts.py`, `app/core/config.py`, `app/core/maa_manager.py`, `frontend/src/composables/useScriptApi.ts`, `frontend/src/views/Scripts.vue` as integrated on first-parent diff of `e5d72bdb`

The initialization refactor introduced in commit `30eb8504` is still a useful secondary reference for Electron service style, but the three commits above should take precedence for this skill.

## Commit Lenses

### `e541fa5f` - Small Refactor Lens
This commit shows how small cleanup work is handled in the project:

1. Remove a helper when it is used once and forces the reader to jump away from the live branch condition.
2. Expand the condition inline if that makes the decisive behavior more obvious in the hot path.
3. Keep the edit narrow: no broad renaming, no reshaping of adjacent logic, no speculative cleanup.
4. Preserve behavior first; the style move is simplification, not redesign.

Signal example:
- `AutoProxy.py` deletes `_has_stop_sequence_completed()` and folds the stop markers directly into the `elif`, keeping the runtime decision in one place.

### `727aafb` - Feature Landing Lens
This commit shows how a new domain type is added without disturbing the existing project skeleton:

1. Reuse existing naming families and parallel structures: `SrcConfig`, `SrcUserConfig`, `SrcManager`, `METHOD_BOOK`, `SCRIPT_BOOK`, `USER_BOOK`.
2. Extend unions, registries, and existing branching logic instead of creating a separate subsystem.
3. Carry the feature across all required layers in one coherent pass:
   - model and schema
   - config loading and saving
   - task manager and handlers
   - notification and logs
   - frontend types, composables, routing, and edit pages
4. Keep module responsibilities explicit: managers orchestrate, tools push notifications, config classes hold grouped fields, UI sections own one form slice.
5. Favor readable repetition over over-generalizing the new type away.
6. Use docstring cleanup opportunistically when already touching the file, but do not let documentation refactoring dominate the functional change.

Signal examples:
- `app/core/config.py` extends typed unions and branch handling in place.
- `app/task/SRC/manager.py` mirrors the existing task lifecycle shape with `check`, `prepare`, `main_task`, `final_task`, and `on_crash`.
- `frontend/src/views/EditView/Script/SRCScriptEdit.vue` keeps one large explicit page component with local state, direct handlers, and segmented form sections.
- `frontend/src/views/SRCUserEdit/BasicInfoSection.vue` uses small focused UI sections with explicit save emits and descriptive labels.

### `e5d72bdb` - Dev Integration Lens
This merge commit is useful less as a source of fresh logic and more as a signal for how a feature branch is integrated back into `dev`:

1. Keep the feature branch structure largely intact.
2. Adjust shared integration points in place:
   - registry books
   - union types
   - version or metadata
   - logging levels
   - shared API and composable branching
3. Prefer compatibility edits over architectural consolidation during the merge.
4. Let `dev` absorb the feature by extending established chokepoints, not by re-laying the whole codebase.

Signal examples:
- `app/api/scripts.py` adds `SrcConfig` and `SrcUserConfig` directly into the existing `SCRIPT_BOOK` and `USER_BOOK`.
- `frontend/src/composables/useScriptApi.ts` extends current type mapping logic instead of replacing it with a more generic mapper.
- `frontend/src/views/Scripts.vue` adds `SRC` handling by continuing the existing branch-by-type UI flow.

## Structural Patterns
1. Files are laid out in obvious sections:
   - module header
   - imports
   - logger
   - type definitions
   - class or function implementation
2. Section dividers are used liberally to keep long files scan-friendly.
3. Public interfaces are defined before the main class or orchestrator.

## Service Layer Style
1. Services are explicit classes with named responsibilities such as `BackendService`, `DependencyService`, `RepositoryService`.
2. Constructors wire concrete dependencies directly; dependency injection stays simple.
3. Long flows are written as ordered steps with comments like "第一步", "第二步".
4. Helper methods usually stay private and narrowly scoped.
5. The main method remains readable without chasing too many indirections.

## Control Flow Preferences
1. Prefer serial, imperative orchestration for setup or deployment tasks.
2. Prefer early returns for already-satisfied states or failure branches.
3. Handle branchy progress updates explicitly instead of compressing them into dense expressions.
4. Use callback-based progress reporting with typed payloads for long-running tasks.
5. When the task is a small refactor, bias toward local simplification over helper extraction.
6. When the task is a new type landing, bias toward extending current branches and registries rather than introducing polymorphic frameworks.
7. When several variants share the same operation shape, use an existing book/registry/dict mapping instead of adding parallel methods for each variant.
8. Keep one-off, frequently inspected task mutation logic inline in the owner function; mark the block with a short comment and blank lines.

## Error And Result Style
1. Cross-service operations usually return stable objects such as:
   - `{ success: boolean; error?: string }`
   - `{ success: boolean; skipped?: boolean; error?: string }`
2. Exceptions are caught near the service boundary and converted into user-facing result objects.
3. Logs include the failure reason in Chinese and enough context to diagnose the stage.

## Logging And Comment Voice
1. Logger names are Chinese and tied to module responsibility, for example `后端服务`, `初始化服务`, `镜像源服务`.
2. Log messages are operational and short.
3. Comments explain purpose, stage, or compatibility intent; they do not narrate trivial syntax.
4. Cleanup preserves useful comments. Remove or rewrite comments only when they are stale, misleading, purely mechanical, or attached to code being removed.

## UI Style Notes
1. Initialization UI keeps one central state map for steps.
2. Computed properties shape component props instead of scattering UI derivation.
3. Formatting helpers such as speed and size conversion stay small and local.
4. Progress handling is explicit and readable, even if slightly repetitive.
5. Large edit pages often stay in one explicit component first, then split into section components only where the form naturally divides.
6. User-facing labels and tooltips are descriptive and domain-specific; they are not abstract placeholders.

## Important Boundaries
1. The style values clarity over abstraction density.
2. Duplication is acceptable when it keeps one flow understandable.
3. File-local consistency beats forcing a global formatting preference.
4. Recent Electron and initialization code is the strongest reference. Do not assume every older Python file matches it exactly.
5. For this skill, the three named commits override more generic style assumptions when they conflict.
6. Config manager/container layers own type safety for stored instances; downstream validators should not repeat those checks unless an unsupported input path can bypass the container.
7. Avoid duplicating user-facing config choices. Merge mutually exclusive modes into one selector, or keep the existing selector and apply behavior to the relevant first matching task.
8. Product architecture is config-swap plus log-monitor driven: AUTO-MAS imports a script's config before task start, restores it after completion, and judges run state through log text, log timestamp, and process-exit signals. Refactors should preserve that explicit operating model.
9. Documented localhost integration surfaces such as the MCP SSE endpoint are part of the product contract; avoid casual renames or hidden behavior changes at those entrypoints.
10. Developer documentation treats config, schema, API, task dispatch, task folder, and frontend page work as one complete script-adaptation path. Partial adaptation is a review smell even when the edited layer is internally correct.
11. Function calls should stay readable at the call site: positional arguments are fine for tiny obvious calls, while boolean arguments and calls with more than two arguments should use keywords.
12. Commit messages follow the documented Conventional Commits shape, but local history often uses concise Chinese subjects; match both the formal structure and the nearby tone.
