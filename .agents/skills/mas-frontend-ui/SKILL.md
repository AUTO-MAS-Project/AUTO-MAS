---
name: mas-frontend-ui
description: Use when working on AUTO-MAS frontend UI, Ant Design Vue components, page layout, forms, tables, modals, drawers, feedback, empty/loading/error states, drag interactions, dark mode, or visual polish.
---

# MAS Frontend UI

Companion to `mas-frontend-standards` for Electron desktop operational UI built on **Ant Design Vue 4.x** and `@ant-design/icons-vue` (never Element Plus / Naive / Arco / AntD React).

## Concept Preview Gate (Mandatory)

Before editing application UI source for **any** visual/UI change:
1. Build an isolated temporary prototype using AntD Vue + theme tokens + representative data.
2. Capture Playwright screenshots at desktop sizes and affected states (both light & dark if theme-dependent).
3. Show screenshots to the user and wait for **explicit approval** (a request to implement/PR does NOT count).
4. After implementing, capture app screenshots and compare against the approved concept. If Playwright cannot render, stop and report the blocker.

## Layout & Shared Primitives

Treat pages as quiet, dense desktop operational tools — NO marketing heroes, decorative gradients, page-specific color/button systems, or unnecessary nested cards. Use 24px/32px page margins, 4px/8px spacing (`8/16/24/32`), the type ramp below, and `8px/12px` card/modal radius.

**Type ramp (derived, not a fixed range)**: `size_n = 14 × 1.2^n`, rounded to the nearest even px, line-height `size + 8`. Base 14 is the CJK desktop body minimum; ratio 1.2 suits dense tool UI and matches AntD's default ramp (so no theme override is needed). Use only these named levels; never fractional sizes, and never set sizes by eye.

| Level | Size / line-height | Use |
| --- | --- | --- |
| caption | 12 / 20 | Hints, descriptions, meta |
| body | 14 / 22 | Body, labels, menus, controls |
| title-sm | 16 / 24 | Card / section titles (one level for both) |
| title | 20 / 28 | Sub-page or modal titles |
| page | 24 / 32 | Page header title |
| display | 30 / 38 | Stat numbers and countdowns only, with `tabular-nums` |

Separate hierarchy with weight (400/600) and text color before adding a new size. To change the ramp, change the base or ratio here and regenerate every level; do not patch individual values.

| Need | Reuse first (`@/components/ui` & AntD 4) |
| --- | --- |
| Layout | `AppPage`, `PageHeader`, `PageSurface`, `SectionCard`, `ConfigEditShell`; `a-layout`, `a-tabs`, `a-card`, `a-space`, `a-flex`, `a-row`/`a-col` |
| Forms | `SettingRow`; `a-form` (prefer `layout="vertical"` for complex config), `a-input`, `a-select`, `a-switch`, `a-checkbox`, `a-date-picker` |
| Display | `StateView`, `NoData`, `StatusChip`; `a-table`, `a-tag`, `a-statistic`, `a-typography` |
| Feedback | `AppModal`, `ConfirmActionButton`, `useConfirm` (`@/composables/useConfirm`); `message`, `a-progress`, `a-alert` |

Check [references/shared-ui-components.md](references/shared-ui-components.md) before hand-rolling raw `a-modal`, `Modal.confirm`, `a-spin`, `a-empty`, or `.form-section`. Keep AntD internal overrides inside `<style scoped>` with `:deep()` (or narrowly namespaced `:global(.mod-modal .ant-modal-body)` for portals); avoid `!important`.

## Theme, Dark Mode & CSS Variables (Red Lines)

1. **Single source of truth**: `src/composables/useTheme.ts` toggles `html.dark` and injects `--ant-*` on `:root` (`ConfigProvider` does NOT emit `cssVar`).
2. **Valid tokens only**: Only reference `--ant-*` defined in `useTheme.updateCSSVariables()` (mapped directly from `antTokens.<token>`, literal `setProperty` names). Use `--app-*` only for project-specific tokens.
3. **NEVER use**: `@media (prefers-color-scheme: ...)` in components, `[data-theme='dark']`, `.light`, or `window.matchMedia` outside `useTheme.ts`. Key dark overrides on `html.dark` (CSS) or reactive `isDark` from `useTheme()` (TS).
4. **Custom backgrounds**: New/renamed page surfaces and tabs MUST follow `frontend/src/styles/appearanceSurfaces.css` (single surface layer, transparent nested content, preserve overlay exclusions).
5. **Audit required**: After touching colors/borders/backgrounds or adding `var()`, run [references/css-variable-audit.md](references/css-variable-audit.md) and fix all undefined variables.

## Component & UX Rules (Issue 128)

- **Buttons & Forms**: One primary action per region; `danger` for destructive/irreversible actions; `loading`/`confirm-loading` on async actions; `aria-label` on icon-only buttons; validate via `a-form` `rules` (not placeholder), preserve input + show concrete error on submit failure; no editable controls in read-only views.
- **Tables & Lists**: Prefer `a-table` with explicit widths on ID/status/time/action columns; >3 row actions go in a More menu; format time as `YYYY-MM-DD HH:mm:ss`; never persist filtered subsets via full-list drag-sort APIs; search must not overwrite persisted collapse preferences.
- **Modals & Overlays**: Use `AppModal` + `useConfirm`/`ConfirmActionButton` (no native `alert`/`confirm`); protect unsaved forms on close; concrete titles (`新增/编辑/查看 XX`, `删除确认`) and footers (`取消 / 确定|保存`). In the frameless Electron window, **ordinary modals/masks/drawers MUST NOT cover the title bar or window buttons**, and low viewports MUST have a single vertical scroll owner — read [references/electron-overlays.md](references/electron-overlays.md).
- **Scrollbars**: Define globally with light/dark theme support (never hard-coded white tracks on dark surfaces; never hide scrollbars globally).
- **Page States**: Handle first load, loading (explicit container height, never zero-height spinner), error with retry, empty with context, data, disabled, and async feedback.
- **Drag**: Visible handle (`MenuOutlined`/`DragOutlined`), handle-only hot zone, `grab`/`grabbing` cursor, inner controls clickable, one drag feedback style.
- **Tooltip / Toast / Tag**: No tooltip repeating visible button text; no success toast for trivial reversible toggles; always show error feedback. Tags ONLY for finite statuses/categories (never names/IDs/paths/timestamps); one primary status per object (green=success, red=failure, orange/gold=warning, blue=processing).

## Verification & Final Response

Verify: (1) light & dark mode via app theme switch (+ custom background if touching surfaces/tabs), (2) no clipping/overflow at desktop widths, (3) affected page states, (4) Electron title-bar clickability if touching overlays, (5) `prefers-color-scheme` only in `useTheme.ts`, (6) zero undefined vars via `css-variable-audit.md`, (7) `mas-frontend-standards` checks.

Report: UI scope, AntD/token usage, states handled, light/dark checks, verification commands/results, and concept vs implementation screenshots + user approval.
