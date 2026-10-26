---
name: mas-frontend-standards
description: Use when working on AUTO-MAS frontend Vue, TypeScript, Vite, Electron renderer, routing, API composables, state, styles, forms, validation, or frontend verification tasks.
---

# MAS Frontend Standards

## Objective

Keep AUTO-MAS frontend changes aligned with Vue 3, TypeScript, Vite Plus (Vite, oxlint, oxfmt, and tests), Electron, Ant Design Vue, Vue Router, OpenAPI, and Yarn 4.

## Dependency Installation

1. Run frontend dependency commands from the `frontend/` directory.
2. Use `yarn install` by default.
3. If the Electron binary download is slow or fails, use the one-shot mirror command: `yarn cross-env ELECTRON_MIRROR="https://npmmirror.com/mirrors/electron/" yarn install`.

## Authority

This skill is self-contained for frontend engineering rules. If local code differs from this summary, inspect neighboring implementations and prefer the current module pattern unless it violates a red line here. The component size policy below is a red line; existing oversized files are not precedent for new code.

## Mandatory Intake

Before editing frontend code:

1. Confirm branch, remote, and working tree status.
2. Inspect the target page, adjacent pages, related components, composables, API wrappers, router entries, and styles.
3. Classify the task as new page, fix, refactor, style/UI adjustment, API integration, route change, or documentation-only.
4. Select `mas-frontend-ui` as a required companion for any UI, layout, component, form, table, modal, feedback, or visual-state change.
5. Keep changes limited to files directly required by the task. Before editing a `.vue` file, record its line count at the task base commit and choose the applicable case in [Component Size Policy](#component-size-policy).
6. For a new or changed user-visible workflow, page, API result or lifecycle operation, load [mas-telemetry](../mas-telemetry/SKILL.md) proactively. Reuse existing observation or add missing telemetry with the feature; document intentional omissions. Do not add a second event merely because a new component calls an already observed wrapper.

## Directory And Ownership

| Code type | Place it here | Do not place it here |
| --- | --- | --- |
| Route page | `src/views/<module>/index.vue` or `src/views/Xxx.vue` | `src/components` |
| Single-module component | `src/views/<module>/components` | `src/components` root |
| Cross-module component | `src/components` | Copied across page folders |
| Business API wrapper | `src/composables/useXxxApi.ts` | Vue page or `src/api` |
| Reusable page flow | `src/views/<module>/useXxxLogic.ts` or composable | Template expressions |
| Pure utility | `src/utils` | Copied inside components |
| Domain type | `src/types` or generated `src/api/models` | Repeated local component types |
| Shared reactive application state | `src/stores` with Pinia | Page-level `localStorage` access |
| Global style token | `src/style.css` or future `src/styles` | Repeated page-local variables |
| Global browser UI style such as scrollbars | `src/styles`, imported once by the renderer entry | Repeated component-level browser pseudo-elements |
| Electron capability | `electron` and preload types | Direct renderer Node access |

Use the narrowest module boundary first. Promote to shared directories only after real cross-module reuse.

## Vue Component Rules

1. Use `<script setup lang="ts">` unless a compatibility reason exists.
2. Order code as imports, types, props/emits, composables, state, computed, watchers, lifecycle, functions.
3. Type props and emits explicitly.
4. Keep computed values for derived state; keep watchers for side effects only.
5. Follow [Component Size Policy](#component-size-policy). Choose extraction boundaries by responsibility, state ownership, and lifecycle.
6. Extract substantial independent UI or stateful workflows when the boundary hides useful complexity, even with one consumer. Keep simple local state local and pure calculations in ordinary functions. Moving an entire page script into `useXxx()` or forwarding most of its refs and callbacks does not establish a useful boundary.
7. Do not introduce a new UI, state, request, or routing library for a small task.

When changing component boundaries, reactive inputs, component models, async watchers, or lifecycle handling, read [Vue state and lifecycle](references/vue-state-and-lifecycle.md). It covers state scope, Vue 3.5 props, Pinia destructuring, typed component contracts, stale reads, cleanup, and route reuse. Apply only the relevant sections; preserve existing working contracts during local fixes.

## Component Size Policy

Count the entire `.vue` file, including template, script, styles, comments, and blank lines; count a final unterminated line too. Use `len(Path(path).read_bytes().splitlines())` in Python, and the same count on `git show <base-commit>:<path>` for the baseline. Record the task base commit once; renaming or moving a component does not reset its baseline.

- **New components and existing components at or below 500 lines:** keep each resulting component at or below 500 lines. Split independent business regions even below the limit.
- **Existing components above 500 lines, with new or expanded business behavior:** extract the affected responsibility before adding that behavior. The original component must become shorter than its baseline, and each new component must meet the limit. Unrelated regions may remain for later work; report the remaining oversized file explicitly.
- **Existing components above 500 lines, with a local fix or maintenance only:** keep the final count at or below its baseline and add no independent business region. Report the baseline and final count plus why the change fits this case. A larger final count requires extracting the affected responsibility.

These requirements take precedence over following local patterns, minimizing diffs, and avoiding unrequested broad refactors. Perform only the extraction needed for the affected responsibility; preserve behavior and leave unrelated files alone. Any exception requires an explicit user instruction; cohesion or passing lint alone is not an exception.

Extract a meaningful UI region or workflow with clear ownership and a narrow interface. Preserve readable formatting and useful comments. Compressing code, removing whitespace to meet the count, or moving the whole script into a composable with the same broad interface does not satisfy this policy.

## API And Data Flow

1. Never hand-edit generated files under `src/api`.
2. Do not write business `axios` or `fetch` calls directly in Vue pages.
3. Use generated `src/api` types and services through `src/composables/useXxxApi.ts` or module logic.
4. Treat `response.code !== 200` as failure unless the local contract proves otherwise.
5. API composables should expose loading, error, and business functions.
6. Pages own business flow such as navigation, closing dialogs, and local state updates.
7. Static-resource checks such as audio `HEAD` requests are not precedent for backend business API calls.
8. Backend schema changes require regenerating frontend API clients; do not manually patch OpenAPI output.
9. Do not hand-roll `axios` + `OpenAPI.BASE` URLs in composables either. If the endpoint is in the generated `Service`, call it; if it is missing, regenerate the client rather than bypass it.
10. Generated services throw `ApiError` on non-2xx responses. Read the backend's message from `error.body` after narrowing it (`instanceof ApiError`, object check, `typeof message === 'string'`), then rethrow as `Error`. Wanting `AxiosError.response.data` is not a reason to skip the generated client. `useMaaFWUpdateApi.ts` and `useHSRPluginApi.ts` are the reference.
11. Pass generated enums (e.g. `MaaFWProjectUpdateIn.action.CHECK`) instead of string literals cast to the request type.

## Backend Config Payloads

Config integration follows [the configuration framework reference](../mas-data-model/references/config-framework.md). Backend config fields are the single contract source; use generated `ConfigInput`/`ConfigPayload` projections through the actual generated client types.

1. Keep omission and explicit `null` distinct in patches. Omitted fields preserve values; null is validated by the backend field. Paths are strings or null, not empty-string sentinels. Preserve masked placeholders as retention values and avoid logging decrypted credentials.
2. Collections use typed `order` items (`uid/type`) and `data` keyed by UUID; collection structural changes use their existing APIs rather than an Entry update or a filtered list passed as complete order.
3. Config date/time state and requests carry full ISO values with timezone offsets. Reuse `src/utils/configDateTime.ts`; non-null clock fields clear to a full timestamp for 00:00 under the field's offset. Nullable date fields retain their own clearing semantics. Fixed-offset/DST boundaries remain documented follow-up work.
4. Metadata support is not authorization to add dynamic forms, trigger controls or new UI flows. Scope those features to explicit requirements; current pages own component selection and field mapping.
5. Electron direct config reads use the shared backend-config reader and YAML shape. JSON fallback belongs only to the pre-upgrade startup path; normal YAML operation does not re-import reintroduced JSON.

## Routing, State, Config

1. Route paths use lowercase kebab-case; route names use PascalCase.
2. Route components are lazy-loaded and business routes include `meta.title`.
3. Prefer `navigateTo` or `navigateToByName`; avoid scattered hardcoded paths.
4. Prefer Pinia for reactive application data shared across components or pages, coordinated state with multiple readers or writers, and state that should survive component unmounts or route changes during the current session.
5. Do not store Pinia-suitable state directly in `localStorage`, and do not keep Pinia and `localStorage` as competing sources of truth.
6. Keep truly component-local, short-lived state in the owning component. Do not create a store for a single isolated control or form draft with no cross-component lifecycle.
7. Use `localStorage` only for small, non-sensitive browser-local preferences that must survive application restarts and do not belong to Pinia, backend data, or Electron configuration. Namespace keys, validate parsed values, and provide safe defaults for missing or invalid data.
8. When shared Pinia state also needs durable persistence, prefer an existing backend or Electron configuration owner instead of adding ad hoc `localStorage` mirroring.
9. Never place tokens, credentials, permissions, secrets, large business datasets, or server-authoritative data in `localStorage`.
10. API and WebSocket endpoints come from Electron config helpers; do not hardcode backend addresses in business pages.
11. Vite-exposed environment variables use the `VITE_` prefix.
12. Same-component navigation can reuse the instance when params or query change. Watch the specific input or use `onBeforeRouteUpdate` when data must follow it; `onMounted` alone does not cover that transition. Keep draft and pending-save behavior explicit rather than forcing global remounts with `route.fullPath`.

## Style And Code Quality

1. Component styles default to `<style scoped>`.
2. Global styles are only for tokens, root layout, or deliberate Ant Design Vue global fixes.
3. Use CSS variables or Ant Design tokens for color, spacing, radius, shadow, and typography.
4. Use kebab-case class names and a semantic page root such as `.queue-page`.
5. Prefer `@/` imports over deep relative paths.
6. Avoid `any`; if unavoidable, narrow the scope and explain why.
7. Do not use `console.log` in business code; use `window.electronAPI.getLogger('module')`.
8. Extract magic values such as intervals, timeouts, status codes, and route names into constants when they repeat or carry meaning.
9. Keep Ant Design Vue default CSS unless a local layout or readability need requires scoped customization.
10. Keep project-wide browser UI rules such as scrollbar styling in one renderer-global stylesheet, imported once from the application entry and driven by light/dark theme variables. Shared Electron modal chrome reservation belongs in `src/styles/appOverlays.css`, imported once by `src/main.ts`; module dialogs should reuse it instead of duplicating title-bar offsets. Portal overrides must target the rendered DOM; see the companion UI skill's [overlay layout reference](../mas-frontend-ui/references/electron-overlays.md).
11. Derived filters and searches must preserve the source data order. A reduced search result must not be passed to persistence or reorder APIs as if it were the complete collection.

## Verification Gate

All commands run from `frontend/`.

Resolve commands from the current `frontend/package.json` and CI configuration. `yarn lint` uses oxlint, `yarn format:check` uses oxfmt, and `yarn typecheck` uses vue-tsc. The `dev` PR format workflow runs these three checks; see [MAS CI checks](../mas-ci-checks/SKILL.md) for the full gate map. Do not carry a dated clean-baseline claim or a warning allowance from a retired toolchain into a new task.

| Touched surface | Command | Passing criterion |
| --- | --- | --- |
| Frontend code | `yarn lint`, `yarn typecheck`, `yarn format:check` | All exit 0; inspect diagnostics and leave no new warnings |
| Added or modified Vue components | Count every resulting `.vue` file and compare existing files with the task base commit | Each file satisfies [Component Size Policy](#component-size-policy); lint/typecheck do not establish this |
| Electron main/preload code | Also `node node_modules/typescript/bin/tsc -p tsconfig.electron.json --noEmit` | 0 errors; renderer typecheck does not cover `electron/` |
| Behavior covered by existing tests | `yarn test <test-file>`; use `yarn test` for changes spanning shared infrastructure or multiple tested flows | Relevant checks pass; report which scope ran |
| Build, routing, or Electron entry | `yarn build` | succeeds |
| Documentation only | Markdown checks, relative links, `git diff --check`, `git status --short`; validate Skill frontmatter when editing Skills | Changed documents are valid; no app build or test run solely for prose |
| UI | also follow `mas-frontend-ui` verification | — |

Rules:

1. For frontend code changes, run the lint, renderer typecheck, and format checks in full. Lint, types, formatting, and behavior tests prove different things; one does not replace another.
2. Use oxlint fixes for lint findings and oxfmt for formatting, scoped to touched files. Inspect the diff afterward; do not run repository-wide auto-fixes for a local change.
3. Investigate failures instead of assuming the baseline is clean or dirty. Before calling a failure pre-existing, reproduce the same command on an untouched checkout of the task's base commit with matching dependencies and configuration. Report that evidence separately from change validation.
4. Select behavior tests by the affected flow and shared boundaries. Keep the permanent-suite policy below; a prose-only change does not require frontend runtime tests.

Prefer `yarn typecheck` over a full `yarn build` for type validation; it is much faster and covers the renderer via `tsconfig.app.json`.

If a command cannot run, state the exact command and the reason. Never claim "complete", "fixed", or "passed" without verification evidence.

## Frontend Tests

Vite Plus runs tests in the default node environment, configured by `frontend/vite.config.ts`. There is no DOM environment, `jsdom`, or `@vue/test-utils`. Tests are colocated next to their subject as `*.test.ts`.

The permanent suite is intentionally small. Follow [frontend/TESTING.md](../../../frontend/TESTING.md): retain only inexpensive shared infrastructure checks whose failure would break multiple flows, lose configuration, prevent startup/shutdown, install an untrusted update, or expose secrets. Feature-specific regression tests remain local verification artifacts, even when they have some value; do not add them to the permanent suite by default. Do not retain tests just because the subject is a pure function.

Three established patterns, in order of preference:

1. **Pure logic** — import existing shared logic directly. `electron/services/runtime/ndjson.test.ts` is a reference. Do not extract a module merely to test a simple expression or mapping.
2. **Composables** — test in node with `vi.mock()` for boundaries. Mock generated services and Electron IPC rather than reaching for a DOM. See `composables/useSaveQueue.test.ts` and `composables/useTaskRuntimeState.test.ts`.
3. **Component rendering** — for local feature verification, render with `createSSRApp` + `renderToString` from `@vue/server-renderer` (ships with `vue`) and assert on the HTML. Stub Ant Design Vue components with slot-passthrough placeholders so assertions cover the component's decisions. These tests are not permanent by default.

Do not introduce `mount()`, `jsdom`, `happy-dom`, or `@vue/test-utils` for a routine change; that is a project-wide testing-stack decision, not a task-level one. If a behavior genuinely cannot be covered by these three patterns, say so in your result instead of adding a test dependency.

### Source-text tests

Do not write tests that `readFileSync` a `.vue`, `.ts`, or `.css` file and assert it contains or lacks particular code — template bindings, handler bodies, style values, imports, or "does not use X" architecture greps. They break on harmless refactors, pass on broken behavior, and were removed in bulk for that reason. Cover the behavior with one of the three patterns above, or leave it to review and say so.

Reading source text is acceptable only when nothing importable exists:

1. **Cross-language contracts** — a shared protocol value that must mirror the backend and has no importable contract; it must also meet the permanent-suite criteria above.
2. **Repo-wide scans** — such as every literal `t('ns.key')` in `src` existing in `zh-CN`. See `i18n/locales.test.ts`.

When an existing source-text test fails because you refactored the code it greps, and it guards neither kind of contract, delete it rather than re-pinning the new string.

## Red Lines

| Temptation | Reality |
| --- | --- |
| "This component is already huge; a small addition can stay inline." | Apply [Component Size Policy](#component-size-policy), including its separate rules for added behavior and local fixes. |
| "I can generate a fresh page faster." | Inspect and reuse local page, component, and composable patterns first. |
| "The API call is tiny, so direct fetch is fine." | Business API calls go through generated services and composables. |
| "Shared state is easiest to put in localStorage." | Shared reactive application state belongs in Pinia; `localStorage` is only the narrow fallback for durable, non-sensitive local preferences. |
| "Pinia should hold every frontend value." | Keep isolated short-lived state local, and keep persistent authoritative data in its backend or Electron configuration owner. |
| "I can tweak generated API files." | `src/api` is generated; regenerate through the project command instead. |
| "New UI text is just a string; inline is faster." | User-facing text goes through the i18n catalog in `src/i18n/locales`. Add the key to `zh-CN.ts` (source language); `en-US.ts` is partial by design and missing keys fall back. |
| "This Chinese literal is untranslated; I'll translate it." | **Chinese literals that drive logic must stay verbatim** — e.g. `tab.status === '运行'`, `result.includes('异常')`, `SchedulerStatus` values. Translating them breaks behaviour silently, with no error. Leave them and add a comment saying why. |
| "This UI-only change can ignore engineering rules." | UI tasks still obey module, state, API, and verification boundaries. |
| "`yarn lint` is failing, but the repo baseline is dirty anyway." | Reproduce the same check on the untouched base commit before calling it pre-existing; never assume a historical baseline still holds. |
| "Lint passed, so the types are fine." | The two are orthogonal and check different things. Run both. |
| "I'll fix the surrounding lint noise while I'm here." | `weekly-format.yml` already formats `dev` every Monday. Unrelated cleanup buries your real diff. |
| "I need jsdom to test this component." | Tests run in node with no DOM. Extract logic to a sibling `.ts`, or render with `@vue/server-renderer`. |
| "I'll lock this in with a test that greps the `.vue` source." | Source-text assertions on implementation details are not accepted. Test behavior, or leave it to review. |
| "The generated client throws `ApiError`, so I'll call axios directly to read the error message." | Read it from `ApiError.body`. Business requests always go through the generated client. |

## Final Response

For frontend tasks, report:

1. Changed files.
2. Verification commands and results.
3. UI checks when applicable.
4. Known risks or "no known residual risk".
5. For every added or modified Vue component, report baseline (or new), final line count, and the applicable size-policy case. Identify remaining oversized files and any explicit user exception; do not report the size check as passed without counting.

State that no business code was changed when the task is documentation-only.
