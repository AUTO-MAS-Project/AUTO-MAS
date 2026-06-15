---
name: mas-frontend-ui
description: Use when working on AUTO-MAS frontend UI, Ant Design Vue components, page layout, forms, tables, modals, drawers, feedback, empty/loading/error states, drag interactions, dark mode, or visual polish.
---

# MAS Frontend UI

## Objective
Keep AUTO-MAS UI changes consistent with an Electron desktop business operations platform: dense enough for repeated work, quiet enough for long sessions, and aligned with Ant Design Vue 4.x.

## Required Source Documents
Before UI work, read these files in the main repository:

1. `frontend/docs/frontend-ui-standard.md`
2. `frontend/docs/frontend-standard.md`

This skill summarizes the execution rules. The source documents and nearby existing pages are the authority for detail.

## UI Intake
Before editing UI:

1. Inspect the target page and adjacent pages to learn the module's real layout, spacing, component usage, and wording.
2. Confirm the project uses Ant Design Vue and `@ant-design/icons-vue`, not Element Plus, Naive UI, Arco, or Ant Design React.
3. Confirm theme variables come from `src/style.css` and `src/composables/useTheme.ts`.
4. Prefer existing components, layout classes, theme tokens, and wording before adding new ones.
5. Check both light and dark mode for readability when UI colors, borders, backgrounds, or status colors change.

## Visual Direction

1. Treat pages as desktop operational tools, not marketing pages.
2. Prefer clarity, scanability, consistency, and low distraction.
3. Do not create page-specific color systems, button systems, radii, shadows, decorative gradients, ornamental backgrounds, or business-irrelevant illustrations.
4. Use page structure appropriate to the app: title, query/filter area, action area, table/list/card content, pagination or footer actions.
5. Keep page margins at 24px or 32px unless a local pattern requires otherwise.
6. Avoid nested cards except for repeated list items or genuinely framed subtools.

## Ant Design Vue Usage

| Need | Prefer |
| --- | --- |
| Layout | `a-layout`, `a-menu`, `a-tabs`, `a-card`, `a-space`, `a-flex`, `a-row`, `a-col` |
| Form input | `a-form`, `a-form-item`, `a-input`, `a-input-number`, `a-select`, `a-switch`, `a-checkbox`, `a-radio`, `a-date-picker` |
| Data display | `a-table`, `a-tag`, `a-empty`, `a-statistic`, `a-typography` |
| Feedback | `a-modal`, `Modal.confirm`, `message`, `a-spin`, `a-progress`, `a-alert` |
| Icons | `@ant-design/icons-vue` |

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

### Tables And Lists
1. Standard data lists prefer `a-table`; use custom lists for drag, complex cards, or virtual logs.
2. Specify widths for ID, status, time, and action columns.
3. Keep row actions stable; use a More menu when there are more than three actions.
4. Show loading and empty states.
5. Use `a-tag` only for finite enum statuses or scan-friendly categories.
6. Time format is `YYYY-MM-DD HH:mm:ss` unless a local pattern differs.

### Modals And Drawers
1. Use `Modal.confirm` for destructive confirmation.
2. Use `a-modal` for short forms and simple flows.
3. Prefer Drawer or a full page for long configuration, complex details, or logs.
4. Titles use concrete wording such as "新增 XX", "编辑 XX", "查看 XX", "删除确认".
5. Footer buttons follow "取消 / 确定" or "取消 / 保存".
6. Avoid browser-native `alert` and `confirm`.

## Page States
Every page or major panel should account for:

1. First load.
2. Loading.
3. Failure with reason and retry when useful.
4. Empty state with context.
5. Data state.
6. Disabled state where relevant.
7. Success and failure feedback for async operations.

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

## Red Lines

| Temptation | Reality |
| --- | --- |
| "This page can have its own style." | AUTO-MAS uses a shared desktop business UI language. |
| "A custom button/input/table is faster." | Use Ant Design Vue and existing project components first. |
| "A tag makes short text look neat." | Tags are only for finite statuses or categories. |
| "Hover cursor is enough for drag." | Draggable items need visible handles and protected inner controls. |
| "Success/failure messages can be generic." | Feedback should state the concrete result or reason. |
| "Dark mode can wait." | Color and token changes must remain readable in both themes. |

## Final Response
For UI tasks, report:

1. UI change scope.
2. Ant Design Vue and token usage.
3. State handling touched by the task.
4. Light/dark mode checks or why they were not run.
5. Verification commands and results.
