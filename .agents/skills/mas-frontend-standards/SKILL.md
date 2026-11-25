---
name: mas-frontend-standards
description: Use when working on AUTO-MAS frontend Vue, TypeScript, Vite, Electron renderer, routing, API composables, Vue Query, queued immediate saves, state, styles, forms, validation, or frontend verification tasks.
---

# MAS Frontend Standards

Vue 3 + TypeScript + Vite+ (Vite, Vitest, Oxlint, Oxfmt) + Electron + Ant Design Vue 4 + Vue Router 4 + OpenAPI + Yarn 4. Run all frontend commands from `frontend/`.

- **Install**: `yarn install` (slow Electron download fallback: `yarn cross-env ELECTRON_MIRROR="https://npmmirror.com/mirrors/electron/" yarn install`).
- **Companions**: Load `mas-frontend-ui` (and its Concept Preview gate) for any UI/layout/visual change; load `mas-telemetry` for user-visible workflow changes.

## Directory Ownership

| Code | Put in | Never put in |
| --- | --- | --- |
| Route page | `src/views/<mod>/index.vue` or `src/views/Xxx.vue` | `src/components` |
| Single-module / shared component | `src/views/<mod>/components` / `src/components` | Copied across views |
| Shared UI primitives & confirms | `src/components/ui` (`@/components/ui`), `src/composables/useConfirm.ts` | Ad hoc `a-modal` / `Modal.confirm` wrappers |
| Business API wrapper / page logic | `src/composables/useXxxApi.ts`, `src/views/<mod>/useXxxLogic.ts` | Vue templates or `src/api` |
| Client state / server cache | Pinia (`src/stores`) / `@tanstack/vue-query` (`src/services/queryClient.ts`) | `localStorage` or duplicated Pinia mirrors |
| Global tokens / browser UI styles | `src/style.css`, `src/styles` (imported once in `main.ts`) | Per-component global overrides |
| Electron capabilities | `electron/` + preload types | Direct renderer Node access |

## Component Size Policy (Red Line)

Measure total `.vue` lines via `len(Path(path).read_bytes().splitlines())` (baseline via `git show <base-commit>:<path>`; moving/renaming does not reset baseline):

- **New or ≤ 500 lines**: keep every resulting `.vue` file **≤ 500 lines**.
- **> 500 lines + new/expanded behavior**: MUST extract the affected responsibility first; original file MUST end shorter than baseline and each new file ≤ 500 lines.
- **> 500 lines + local fix only**: MUST end ≤ baseline with no new independent business region.
- **No gaming**: Do not strip whitespace, minify formatting, or dump the whole script into a broad `useXxx()` wrapper just to pass line count. Exceptions require explicit user instruction.

## Vue, State & Routing Rules

- Use `<script setup lang="ts">` with typed props/emits; `computed` for derived state, `watch` for side effects only.
- Read [references/vue-state-and-lifecycle.md](references/vue-state-and-lifecycle.md) when changing component boundaries, reactive inputs, async watchers, or route reuse (`onBeforeRouteUpdate` / targeted watch; never force remount with `route.fullPath`).
- **State boundaries**: Component-local state stays local; shared client state in Pinia; shared backend reads in Vue Query; `localStorage` ONLY for small, non-sensitive, namespaced preferences (NEVER tokens, credentials, or authoritative data).
- **Routing**: kebab-case paths, PascalCase names, lazy-loaded routes with `meta.title`; use `navigateTo` / `navigateToByName`.
- **Style & logs**: Default `<style scoped>`, kebab-case classes, `@/` imports, AntD tokens/CSS vars, `window.electronAPI.getLogger('mod')` (NO `console.log`). Shared Electron modal chrome offset lives in `src/styles/appOverlays.css`. Filtered/searched lists MUST preserve source order and MUST NOT be sent to reorder/save APIs as the full list.

## API, Config & i18n Rules

- **Generated client (`src/api`)**: NEVER hand-edit; regenerate after backend schema changes. NEVER call `axios`/`fetch` directly in views or composables — use generated services + generated enums (not cast string literals).
- **Errors**: Narrow `ApiError` (`instanceof ApiError` → `error.body.message`) and rethrow `Error` (ref: `useMaaFWUpdateApi.ts`, `useHSRPluginApi.ts`). Treat `response.code !== 200` as failure.
- **Immediate saves & caches**: Read [references/request-state-and-saves.md](references/request-state-and-saves.md) before changing query invalidation or queued saves.
- **Config payloads**: Keep omitted vs explicit `null` distinct; paths are `string | null` (no `""` sentinel); use `src/utils/configDateTime.ts` for ISO timezone values; keep masked secrets intact; never mutate collection order via Entry update. (Full contract: `../mas-data-model/references/config-framework.md`.)
- **i18n**: Put all user-facing text in `src/i18n/locales` and update `zh-CN.ts`, `en-US.ts`, `ja-JP.ts` together (`yarn audit:i18n` / `locales.test.ts`). **NEVER translate Chinese literals that drive logic** (e.g. `tab.status === '运行'`, `result.includes('异常')`).

## Frontend Tests (Node-Only)

Tests run in Node (`frontend/vite.config.ts`) as colocated `*.test.ts` — **NO `jsdom`, `happy-dom`, or `@vue/test-utils`**. Follow `mas-testing` retention rules and `frontend/TESTING.md`.

1. **Preferred patterns**: pure logic imports (`ndjson.test.ts`) → composables with `vi.mock()` (`useSaveQueue.test.ts`) → component rendering in Node via `@vue/server-renderer` (`createSSRApp` + `renderToString` with stubbed AntD slots). Lack of `jsdom` does NOT mean component tests must read source files.
2. **NO source-text tests**: NEVER `readFileSync` `.vue`/`.ts`/`.css` to grep implementation details. Only allowed for cross-language protocol contracts and repo-wide i18n scans (`i18n/locales.test.ts`). Delete broken legacy source-text tests on refactor.

## Verification Gate (from `frontend/`)

| Change | Required commands |
| --- | --- |
| Any frontend code | `yarn lint`, `yarn typecheck`, `yarn format:check` (all exit 0; scope fixes to touched files) |
| `.vue` added/modified | Measure & report baseline/final line counts against Component Size Policy |
| `electron/` main/preload | Also `node node_modules/typescript/bin/tsc -p tsconfig.electron.json --noEmit` |
| Tested behavior / infra | `yarn test <file>` (or `yarn test` for shared infra) |
| Build / routing / Electron entry | `yarn build` |
| Docs only | `git diff --check`, relative links, Skill frontmatter |

Never assume a failure is pre-existing without reproducing on the untouched base commit. Never claim completion without executed evidence.

## Final Response Checklist

Report: (1) changed files, (2) verification commands & results, (3) Vue component baseline → final line counts & size-policy case, (4) UI checks if applicable, (5) known risks or "no known residual risk".
