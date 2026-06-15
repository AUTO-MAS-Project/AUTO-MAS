---
name: mas-frontend-standards
description: Use when working on AUTO-MAS frontend Vue, TypeScript, Vite, Electron renderer, routing, API composables, state, styles, forms, validation, or frontend verification tasks.
---

# MAS Frontend Standards

## Objective
Keep AUTO-MAS frontend changes aligned with the current Vue 3, TypeScript, Vite, Electron, Ant Design Vue, Vue Router, OpenAPI, ESLint, Prettier, and Yarn 4 project conventions.

## Required Source Documents
Before frontend work, read these files in the main repository:

1. `frontend/docs/frontend-standard.md`
2. `frontend/docs/frontend-ui-standard.md`

This skill is a routing and execution summary. If details differ, follow the source documents and existing code in the touched module.

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
| Global style token | `src/style.css` or future `src/styles` | Repeated page-local variables |
| Electron capability | `electron` and preload types | Direct renderer Node access |

Use the narrowest module boundary first. Promote to shared directories only after real cross-module reuse.

## Vue Component Rules

1. Use `<script setup lang="ts">` unless a compatibility reason exists.
2. Order code as imports, types, props/emits, composables, state, computed, watchers, lifecycle, functions.
3. Type props and emits explicitly.
4. Keep computed values for derived state; keep watchers for side effects only.
5. Split components that exceed 500 lines or contain multiple independent business regions.
6. Extract repeated logic into composables or module logic files instead of growing templates.

## API And Data Flow

1. Never hand-edit generated files under `src/api`.
2. Do not write business `axios` or `fetch` calls directly in Vue pages.
3. Use generated `src/api` types and services through `src/composables/useXxxApi.ts` or module logic.
4. Treat `response.code !== 200` as failure unless the local contract proves otherwise.
5. API composables should expose loading, error, and business functions.
6. Pages own business flow such as navigation, closing dialogs, and local state updates.
7. Static-resource checks such as audio `HEAD` requests are not precedent for backend business API calls.

## Routing, State, Config

1. Route paths use lowercase kebab-case; route names use PascalCase.
2. Route components are lazy-loaded and business routes include `meta.title`.
3. Prefer `navigateTo` or `navigateToByName`; avoid scattered hardcoded paths.
4. The project has Pinia as a dependency but does not currently use registered stores. Do not introduce stores just because Pinia exists.
5. Prefer local state first; use composables for cross-component, persistent, or coordinated state.
6. Do not invent token, login, permission, or security storage in pages.
7. API and WebSocket endpoints come from Electron config helpers; do not hardcode backend addresses in business pages.

## Style And Code Quality

1. Component styles default to `<style scoped>`.
2. Global styles are only for tokens, root layout, or deliberate Ant Design Vue global fixes.
3. Use CSS variables or Ant Design tokens for color, spacing, radius, shadow, and typography.
4. Use kebab-case class names and a semantic page root such as `.queue-page`.
5. Prefer `@/` imports over deep relative paths.
6. Avoid `any`; if unavoidable, narrow the scope and explain why.
7. Do not use `console.log` in business code; use `window.electronAPI.getLogger('module')`.
8. Extract magic values such as intervals, timeouts, status codes, and route names into constants when they repeat or carry meaning.

## Verification Gate

Use verification proportional to the touched surface:

1. Business code changes: run `yarn lint` at minimum.
2. Build, routing, type, or Electron entry changes: run `yarn build` or the relevant type/build command.
3. Documentation-only changes: check file existence, headings, section completeness, and `git status --short`.
4. UI changes: also follow `mas-frontend-ui` verification.
5. If a command cannot run, state the exact command and reason.

Never claim "complete", "fixed", or "passed" without verification evidence.

## Red Lines

| Temptation | Reality |
| --- | --- |
| "I can generate a fresh page faster." | Inspect and reuse local page, component, and composable patterns first. |
| "The API call is tiny, so direct fetch is fine." | Business API calls go through generated services and composables. |
| "Pinia is installed, so I can add a store." | Current app does not use registered stores; use local state or composables unless enabling Pinia is the task. |
| "I can tweak generated API files." | `src/api` is generated; regenerate through the project command instead. |
| "This UI-only change can ignore engineering rules." | UI tasks still obey module, state, API, and verification boundaries. |

## Final Response
For frontend tasks, report:

1. Changed files.
2. Verification commands and results.
3. UI checks when applicable.
4. Known risks or "no known residual risk".

State that no business code was changed when the task is documentation-only.
