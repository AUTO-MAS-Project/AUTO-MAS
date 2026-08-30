---
name: mas-frontend-standards
description: Use when working on AUTO-MAS frontend Vue, TypeScript, Vite, Electron renderer, routing, API composables, state, styles, forms, validation, or frontend verification tasks.
---

# MAS Frontend Standards

## Objective
Keep AUTO-MAS frontend changes aligned with the current Vue 3, TypeScript, Vite, Electron, Ant Design Vue, Vue Router, OpenAPI, ESLint, Prettier, and Yarn 4 project conventions.

## Dependency Installation

1. Run frontend dependency commands from the `frontend/` directory.
2. Use `yarn install` by default.
3. If the Electron binary download is slow or fails, use the one-shot mirror command: `yarn cross-env ELECTRON_MIRROR="https://npmmirror.com/mirrors/electron/" yarn install`.

## Authority
This skill is self-contained for frontend engineering rules. If local code differs from this summary, inspect neighboring implementations and prefer the current module pattern unless it violates a red line here.

## Mandatory Intake
Before editing frontend code:

1. Confirm branch, remote, and working tree status.
2. Inspect the target page, adjacent pages, related components, composables, API wrappers, router entries, and styles.
3. Classify the task as new page, fix, refactor, style/UI adjustment, API integration, route change, or documentation-only.
4. Select `mas-frontend-ui` as a required companion for any UI, layout, component, form, table, modal, feedback, or visual-state change.
5. Keep changes limited to files directly required by the task.

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
5. Split components that exceed 500 lines or contain multiple independent business regions.
6. Extract repeated logic into composables or module logic files instead of growing templates.
7. Do not introduce a new UI, state, request, or routing library for a small task.

## API And Data Flow

1. Never hand-edit generated files under `src/api`.
2. Do not write business `axios` or `fetch` calls directly in Vue pages.
3. Use generated `src/api` types and services through `src/composables/useXxxApi.ts` or module logic.
4. Treat `response.code !== 200` as failure unless the local contract proves otherwise.
5. API composables should expose loading, error, and business functions.
6. Pages own business flow such as navigation, closing dialogs, and local state updates.
7. Static-resource checks such as audio `HEAD` requests are not precedent for backend business API calls.
8. Backend schema changes require regenerating frontend API clients; do not manually patch OpenAPI output.

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
10. Keep project-wide browser UI rules such as scrollbar styling in one renderer-global stylesheet, imported once from the application entry and driven by light/dark theme variables.
11. Derived filters and searches must preserve the source data order. A reduced search result must not be passed to persistence or reorder APIs as if it were the complete collection.

## Verification Gate

All commands run from `frontend/`.

**The repo-wide baseline is clean.** On untouched `dev` (verified 2026-08-30), `yarn lint` reports 0 errors and 1 long-standing `vue/no-v-html` warning, `yarn typecheck` reports 0 errors, and `yarn test` is fully green. `weekly-format.yml` re-runs `ruff format`, `yarn lint:fix` and `yarn format` on `dev` every Monday, so formatting drift does not accumulate.

**Therefore any lint or typecheck error you see is almost certainly yours.** Do not dismiss it as pre-existing noise without first checking the same command on an untouched checkout.

| Touched surface | Command | Passing criterion |
| --- | --- | --- |
| Any business code | `yarn eslint . --max-warnings 1` | exit 0. Warnings count: the budget of 1 is the single pre-existing `vue/no-v-html`, so any new warning fails the gate. `yarn lint` alone only surfaces errors — Yarn does not forward `--max-warnings` to the script, hence the direct `yarn eslint` form. |
| Types, props/emits, API usage, generated-client consumption | `yarn typecheck` | 0 errors |
| A module with a sibling `*.test.ts`, or shared logic/styles under test | `yarn test` | fully green |
| Build, routing, or Electron entry | `yarn build` | succeeds |
| Documentation only | file existence, headings, sections, `git status --short` | — |
| UI | also follow `mas-frontend-ui` verification | — |

Rules:

1. Run `yarn lint`, `yarn typecheck` and `yarn test` whole. All three can and should pass; there is no baseline to subtract.
2. Lint and typecheck are still orthogonal — they check different things, so passing one says nothing about the other. Run both.
3. `yarn lint:fix` resolves `prettier/prettier` findings; use it rather than hand-formatting. Warnings are part of the gate — do not leave a new one behind.
4. A failure in any of the three is yours until proven otherwise. If you believe it pre-exists, verify on an untouched checkout and say so explicitly in your result.

Prefer `yarn typecheck` over a full `yarn build` for type validation; it is much faster and covers the renderer via `tsconfig.app.json`.

If a command cannot run, state the exact command and the reason. Never claim "complete", "fixed", or "passed" without verification evidence.

## Frontend Tests

Vitest runs with **no config file and no DOM environment**. There is no `vitest.config.ts`, no `jsdom`, and no `@vue/test-utils`. Tests execute in the default node environment and are colocated next to their subject as `*.test.ts`.

Three established patterns, in order of preference:

1. **Pure logic** — extract the logic out of the `.vue` file into a sibling `.ts`, then import and test it directly. `views/scripts/scriptSearch.ts` with `scriptSearch.test.ts` is the reference. This is the main reason to extract logic from a component: testability.
2. **Composables** — test in node with `vi.mock()` for boundaries. Mock `@/api` (the generated `Service`) and `ant-design-vue` (`message`) rather than reaching for a DOM. See `composables/useEmulatorDeviceOptions.test.ts`.
3. **Component structure** — `readFileSync` the `.vue` (or `.css`) source and assert on its text. Used to lock in constraints that have no runtime assertion point, such as overlay `z-index`, viewport-height clamps, and stylesheet imports. See `views/scripts/components/ScriptCreateDialog.test.ts` and `styles/scrollbar.test.ts`.

Do not introduce `mount()`, `jsdom`, `happy-dom`, or `@vue/test-utils` for a routine change; that is a project-wide testing-stack decision, not a task-level one. If a behavior genuinely cannot be covered by these three patterns, say so in your result instead of adding a test dependency.

Pattern 3 is how several `mas-frontend-ui` layout rules are actually enforced. When you change an overlay's `z-index`, a dialog's height clamp, or a global stylesheet import, expect a source-text test to assert on the exact string you edited, and update it in the same change.

## Red Lines

| Temptation | Reality |
| --- | --- |
| "I can generate a fresh page faster." | Inspect and reuse local page, component, and composable patterns first. |
| "The API call is tiny, so direct fetch is fine." | Business API calls go through generated services and composables. |
| "Shared state is easiest to put in localStorage." | Shared reactive application state belongs in Pinia; `localStorage` is only the narrow fallback for durable, non-sensitive local preferences. |
| "Pinia should hold every frontend value." | Keep isolated short-lived state local, and keep persistent authoritative data in its backend or Electron configuration owner. |
| "I can tweak generated API files." | `src/api` is generated; regenerate through the project command instead. |
| "This UI-only change can ignore engineering rules." | UI tasks still obey module, state, API, and verification boundaries. |
| "`yarn lint` is failing, but the repo baseline is dirty anyway." | It is not. Clean `dev` passes lint, typecheck and tests. A failure is yours until you verify otherwise on an untouched checkout. |
| "Lint passed, so the types are fine." | The two are orthogonal and check different things. Run both. |
| "I'll fix the surrounding lint noise while I'm here." | `weekly-format.yml` already formats `dev` every Monday. Unrelated cleanup buries your real diff. |
| "I need jsdom to test this component." | Tests run in node with no DOM. Extract logic to a sibling `.ts`, or assert on source text. |

## Final Response
For frontend tasks, report:

1. Changed files.
2. Verification commands and results.
3. UI checks when applicable.
4. Known risks or "no known residual risk".

State that no business code was changed when the task is documentation-only.
