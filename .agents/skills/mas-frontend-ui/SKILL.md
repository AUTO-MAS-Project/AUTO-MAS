---
name: mas-frontend-ui
description: Use when working on AUTO-MAS frontend UI, Ant Design Vue components, page layout, forms, tables, modals, drawers, feedback, empty/loading/error states, drag interactions, dark mode, or visual polish.
---

# MAS Frontend UI

## Objective

Keep AUTO-MAS UI changes consistent with an Electron desktop business operations platform: dense enough for repeated work, quiet enough for long sessions, and aligned with Ant Design Vue 4.x.

## Authority

This skill is self-contained for AUTO-MAS UI rules. Nearby existing pages are still the authority for module-specific layout, wording, and visual rhythm when they do not conflict with this skill.

## UI Intake

Before editing UI:

1. Inspect the target page and adjacent pages to learn the module's real layout, spacing, component usage, and wording.
2. Confirm the project uses Ant Design Vue and `@ant-design/icons-vue`, not Element Plus, Naive UI, Arco, or Ant Design React.
3. Confirm theme variables come from `src/style.css` and `src/composables/useTheme.ts`.
4. Prefer existing components, layout classes, theme tokens, and wording before adding new ones.
5. Check both light and dark mode for readability when UI colors, borders, backgrounds, or status colors change.
6. Keep the UI inside the existing Electron desktop business-product language.

## Visual Direction

1. Treat pages as desktop operational tools, not marketing pages.
2. Prefer clarity, scanability, consistency, and low distraction.
3. Do not create page-specific color systems, button systems, radii, shadows, decorative gradients, ornamental backgrounds, or business-irrelevant illustrations.
4. Use page structure appropriate to the app: title, query/filter area, action area, table/list/card content, pagination or footer actions.
5. Keep page margins at 24px or 32px unless a local pattern requires otherwise.
6. Avoid nested cards except for repeated list items or genuinely framed subtools.
7. Do not use marketing-style hero sections, decorative gradients, ornamental backgrounds, or unrelated illustrations in business screens.

## Ant Design Vue Usage

| Need         | Prefer                                                                                                                 |
| ------------ | ---------------------------------------------------------------------------------------------------------------------- |
| Layout       | `a-layout`, `a-menu`, `a-tabs`, `a-card`, `a-space`, `a-flex`, `a-row`, `a-col`                                        |
| Form input   | `a-form`, `a-form-item`, `a-input`, `a-input-number`, `a-select`, `a-switch`, `a-checkbox`, `a-radio`, `a-date-picker` |
| Data display | `a-table`, `a-tag`, `a-empty`, `a-statistic`, `a-typography`                                                           |
| Feedback     | `a-modal`, `Modal.confirm`, `message`, `a-spin`, `a-progress`, `a-alert`                                               |
| Icons        | `@ant-design/icons-vue`                                                                                                |

Use default component styles, official props, slots, layout components, and theme tokens first. Custom CSS is for local layout constraints or real readability needs.

When overriding Ant Design Vue internals:

1. Keep the override inside scoped styles.
2. Use `:deep()` under the current component root class.
3. Avoid global `.ant-*` overrides unless the task is a deliberate project-wide token or global fix.
4. Avoid `!important`; if unavoidable, document the reason.

## Tokens And Styling

1. Use Ant Design tokens or existing CSS variables for colors, backgrounds, borders, spacing, radius, shadow, and text.
2. Main spacing should follow 4px/8px multiples: 8, 16, 24, 32 are the usual anchors.
3. Use restrained type scales: 12, 14, 16, 18, 20, 24 for normal business pages.
4. Cards and modals usually use 8px or 12px radius; controls use Ant Design defaults.
5. Use light shadows sparingly; backend pages should not feel floaty.
6. Styles default to scoped and semantic kebab-case classes.

## Theme And Dark Mode

1. The single theme source of truth is `src/composables/useTheme.ts`: it toggles the `dark` class on `<html>` and injects all `--ant-*` variables on `:root`. `ConfigProvider` runs without `cssVar`, so AntD token variables do not exist at runtime unless `useTheme` defines them.
2. In CSS, prefer `--ant-*` tokens that already adapt to the theme. When a distinct dark value is unavoidable, key it on the `html.dark` ancestor selector inside scoped styles. Never use `@media (prefers-color-scheme: ...)` in components; it follows the OS instead of the app theme.
3. Never invent theme hooks such as `[data-theme='dark']` or a `.light` class; nothing in the codebase sets them, so such rules are dead code.
4. In JS/TS, derive theme-dependent values from the reactive `isDark` exported by `useTheme`. Never read `window.matchMedia('(prefers-color-scheme: ...)')` outside `useTheme.ts`; a matchMedia call inside a computed is non-reactive and will not update on theme or OS changes.
5. Reference only `--ant-*` names defined by `useTheme.updateCSSVariables()`. Every `--ant-*` definition must map to the matching `antTokens.<token>` value derived from the same Ant Design algorithm and seed used by `ConfigProvider`; never approximate Ant Design tokens with hand-written light/dark values. Use a literal name in each `setProperty` call so the variable stays greppable.
6. Reserve `--app-*` for project-specific shared values that have no Ant Design token equivalent. Derive those values from the app theme in `useTheme.ts`, with explicit light/dark behavior where needed.
7. When adding theme-aware styles, verify both themes with the app's own theme switch, not the OS setting.

## CSS Variable Audit

Before completing styling work that touches colors, borders, backgrounds, or adds `var()` references, run the undefined-CSS-variable audit in `references/css-variable-audit.md`. Fix every reported variable by correcting it to an existing token, mapping a missing `--ant-*` variable to its matching `antTokens.<token>`, or defining a genuinely project-specific `--app-*` variable.

## Component Patterns

### Buttons

1. Use one primary action per main page region.
2. Use `danger` for delete, stop, disable, clear, or irreversible actions.
3. High-risk actions require `Modal.confirm`.
4. Async submit/search/start/stop/export actions need `loading` or `confirm-loading`.
5. Icon-only buttons need accessible naming such as `aria-label` when context is not enough.

### Forms

1. Use `a-form`; complex configuration pages prefer `layout="vertical"`.
2. Use `rules` and `required`; do not rely on placeholder as validation.
3. Placeholder text should describe user action.
4. Long forms should be grouped by business meaning.
5. Submit failures must preserve user input and show a concrete reason.
6. Similar create/edit flows should reuse an edit component with `isEdit` or route parameters.
7. Read-only detail views must not reuse editable controls in an active editing state.

### Tables And Lists

1. Standard data lists prefer `a-table`; use custom lists for drag, complex cards, or virtual logs.
2. Specify widths for ID, status, time, and action columns.
3. Keep row actions stable; use a More menu when there are more than three actions.
4. Show loading and empty states.
5. Use `a-tag` only for finite enum statuses or scan-friendly categories.
6. Time format is `YYYY-MM-DD HH:mm:ss` unless a local pattern differs.
7. Parent-child search must define its matching semantics: a parent match may retain all children, while a child match should retain the parent and only the matching children unless the product explicitly needs broader results.
8. Do not write filtered subsets back through full-list drag-sort APIs. Disable reordering while searching, or explicitly map the result back to the complete source list.
9. Search may expand matching groups for discoverability, but must not overwrite the user's persisted collapse preference.

### Modals And Drawers

1. Use `Modal.confirm` for destructive confirmation.
2. Use `a-modal` for short forms and simple flows.
3. Prefer Drawer or a full page for long configuration, complex details, or logs.
4. Titles use concrete wording such as "新增 XX", "编辑 XX", "查看 XX", "删除确认".
5. Footer buttons follow "取消 / 确定" or "取消 / 保存".
6. Avoid browser-native `alert` and `confirm`.
7. Close protection is required when dismissing a form would lose unsaved changes.
8. In the frameless Electron window, treat the title bar and its minimize, maximize, and close buttons as reserved application chrome. Ordinary modals, masks, drawers, and popovers must not cover or block those controls.
9. Inspect the title bar height and stacking context before setting overlay `z-index`. Keep normal business overlays below the title bar or reserve its space; only an intentional startup or shutdown safety layer may block window controls.
10. At low window heights, constrain the dialog to the usable viewport and choose exactly one vertical scroll owner for the flow, normally the dialog body or content region. Ordinary child lists and grids must expand inside that scroller instead of adding another `overflow-y: auto`; nested scrolling is reserved for deliberately independent panes. Do not make the page body or the modal wrapper provide the overflow, and keep close and footer actions reachable.

### Scrollbars

1. Define scrollbar width, track, thumb, and hover colors in the shared global stylesheet or shared tokens; do not repeat browser-specific scrollbar rules in individual pages.
2. Scrollbars must support both light and dark themes. Tracks should be transparent or theme-matched, and a dark surface must never expose a hard-coded white track.
3. Local scrollbar overrides are allowed only when a component has genuinely different interaction needs, and should reuse shared variables where possible.
4. Do not hide scrollbars globally. Hidden scrollbars are acceptable only for deliberate containers that remain operable by wheel, touchpad, keyboard, and other supported input methods.

## Page States

Every page or major panel should account for:

1. First load.
2. Loading.
3. Failure with reason and retry when useful.
4. Empty state with context.
5. Data state.
6. Disabled state where relevant.
7. Success and failure feedback for async operations.

Loading indicators for an otherwise empty panel or dialog step must sit in a container with explicit usable size and centered alignment. Do not place an overlay spinner around zero-height conditional content, which leaves the indicator anchored at the container origin.

For WebSocket, scheduler, download, backend startup, and other process flows, distinguish connecting, connected, disconnected, reconnecting, timeout, processing, success, and failure when those states exist.

## Issue 128 UX Constraints

### Drag Interactions

1. Draggable rows must expose a visible drag handle such as `MenuOutlined` or `DragOutlined`.
2. The drag hot zone belongs to the handle area, not the whole row.
3. Buttons, inputs, switches, selects, and links inside rows must remain clickable.
4. Use `grab` on handles and `grabbing` while dragging.
5. Use one drag feedback style, not multiple placeholder or ghost effects at once.

### Tooltip And Toast

1. Use Tooltip only when an icon is unclear, a rule is complex, or an operation is risky.
2. Do not add Tooltip that repeats visible button text.
3. Do not show success Toast for trivial reversible toggles when the component state is already clear.
4. Always show error feedback for failed toggles, saves, and API exceptions.

### Tag And Status

1. Tags are for finite statuses or categories, not usernames, paths, IDs, timestamps, free text, or progress text.
2. One object should have one primary status at a time.
3. Use green for success, red for failure, orange/gold for warning, blue for processing.
4. Do not show success and failure with similar weight on the same object.

### Navigation And Dialog Flow

1. Breadcrumbs must reflect real reachable navigation, not invented hierarchy.
2. Detail and edit pages need a clear return path.
3. If selecting an item necessarily advances to the next step, advance directly instead of adding a redundant confirm button.

## Verification Gate

Before declaring UI work complete:

1. Check light mode and dark mode when visual styling changes.
2. Confirm text does not overlap, clip important actions, or overflow containers at common desktop widths.
3. Confirm loading, empty, error, disabled, success, and failure states affected by the task.
4. Run the relevant project verification from `mas-frontend-standards`.
5. If UI cannot be visually checked, state what was not checked and why.
6. Confirm interactive elements are visually discoverable and disabled elements are clearly non-interactive.
7. For overlays in Electron, test a low-height viewport and confirm title-bar controls remain visible and clickable, the outer page does not gain unintended overflow, and the dialog's internal content can still scroll.
8. When scrollbar styling changes, inspect both light and dark themes on an actually scrollable surface.
9. Confirm `prefers-color-scheme` appears only in `src/composables/useTheme.ts`; grep for it when touching theme-related styles.
10. Run the CSS variable audit from `references/css-variable-audit.md` and confirm zero undefined references.

## Red Lines

| Temptation                                  | Reality                                                                                                  |
| ------------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| "This page can have its own style."         | AUTO-MAS uses a shared desktop business UI language.                                                     |
| "A custom button/input/table is faster."    | Use Ant Design Vue and existing project components first.                                                |
| "A tag makes short text look neat."         | Tags are only for finite statuses or categories.                                                         |
| "Hover cursor is enough for drag."          | Draggable items need visible handles and protected inner controls.                                       |
| "Success/failure messages can be generic."  | Feedback should state the concrete result or reason.                                                     |
| "Dark mode can wait."                       | Color and token changes must remain readable in both themes.                                             |
| "prefers-color-scheme is the standard way." | The app theme overrides the OS theme; components must key on `html.dark` or tokens, never media queries. |
| "Any --ant-\* name will work."              | AntD does not emit CSS variables here; only names defined in `useTheme.updateCSSVariables()` resolve.    |

## Final Response

For UI tasks, report:

1. UI change scope.
2. Ant Design Vue and token usage.
3. State handling touched by the task.
4. Light/dark mode checks or why they were not run.
5. Verification commands and results.
