# Electron Overlay Layout

Use this reference when changing modal placement, portal styles, or overflow in the frameless Electron window.

## Chrome And Spacing

- Confirm the current geometry in `frontend/src/components/TitleBar.vue`. The current title bar is 32px high; normal dialog spacing is 16px below it and 16px above the bottom edge. Do not solve a missing offset by raising an overlay's `z-index`.
- Reuse `frontend/src/styles/appOverlays.css`, loaded once by `frontend/src/main.ts`. It reserves chrome only when `.title-bar` exists. Windows without that title bar must retain their own layout.
- Keep both `.ant-modal-wrap` and `.ant-modal-mask` out of the title-bar region. Moving only `.ant-modal` leaves a full-window mask or wrapper intercepting window controls, including when it shares the title bar's stacking level.
- Account for the coordinate origin. Once the wrapper begins below the title bar and provides the ordinary gap, an additional dialog `top: 48px` counts the same space twice. A viewport-relative value such as `top: 5vh` is not a reliable chrome reservation: at 600px height it is only 30px.
- Nested dialogs may need a higher layer than their parent, but their wrapper and mask must still respect chrome. Inspect the actual `getContainer` target and stacking context; do not add the title-bar offset again just because a dialog is nested.

## Portal Styles And Scroll Ownership

- Vue `scoped` plus `:deep()` does not guarantee that an Ant Design modal shell will match. Check the generated selector, portal DOM, and computed style. For a module-specific portal override, use a dedicated class such as `:global(.update-modal .ant-modal-body)`. Keep application-wide geometry in the shared stylesheet rather than broad module-level `.ant-*` rules.
- Bound the content by the usable viewport, including title bar and both gaps; the current cap is `calc(100vh - 64px)`. Header and footer actions must not shrink. Flex children that should scroll or shrink need `min-height: 0`.
- Choose one vertical scroll owner for ordinary content, normally `.ant-modal-body`. Let ordinary form fields, lists, and grids expand inside it. Do not leave independent `55vh` / `60vh` child scrollers inside a shrinking body or put scrolling on both the content shell and body.
- Preserve deliberate independent panes such as log editors or split-column tables. In those cases, let the pane scroll, keep its containing body bounded, and avoid a second outer scrollbar.

## Coverage And Verification

Before marking a related dialog flow fixed:

1. Inventory `a-modal` / `Modal` components, `Modal.confirm/info/warning/error`, `Modal.useModal()` options, shared composables, and nested confirmation or picker dialogs. Checking only the first template modal misses shared previews and confirmations.
2. Use real components with long content in light and dark modes. Exercise normal and low heights; 720px, 480px, and 300px are useful regression probes for this layout. A local fixture with mocked services checks rendering but does not prove an installed Electron application's behavior.
3. Confirm modal content stays below the title bar plus the normal gap and above the bottom gap, the mask starts below the title bar, close/footer actions remain reachable, and the wrapper/page has no unintended overflow.
4. Inspect the window-control hit target and perform a harmless control interaction in the test fixture while the modal is open. Verify the observed result; visual presence or a successful locator click alone does not prove that the mask is not intercepting input.
5. Open a nested dialog or confirmation and repeat the chrome and scrolling checks. Also check a window without `.title-bar` to confirm the chrome-specific rules do not impose offsets there.
