# MaaFW handoff - 2026-06-23

This note records the current MaaFW work state on branch `inter`
tracking `origin/feat/inter`. It is intended for continuing the work on
another machine.

## Current user directives

- Commit and push the current code changes together with this handoff note.
- Do not modify the emulator management page in this branch.
- Do not modify the generic script page in this branch.
- Generic emulator capabilities and generic emulator polling are out of scope.
- MaaFW-specific emulator capability detection and MaaFW runtime control strategy are in scope.
- MaaFW `Controller` must be script-level config, not user-level config.
- MaaFW `Resource` must also be script-level config, not user-level config.
- MaaFW user page must not show `Controller`; after the latest direction, it should not show `Resource` either.
- No legacy-user compatibility/migration work is needed.
- Draggable MaaFW task rows should follow the user's preference: whole-row drag, no left drag handle.
- If the MaaFW script page has to load `interface.json`, dependent controls must be disabled while loading and the loading state must be obvious.

## Current code state

The worktree contains MaaFW changes across backend and frontend. `_stats.py`
is an unrelated untracked local file and should stay out of commits.

Changed files to carry forward:

- `app/api/scripts.py`
- `app/models/schema.py`
- `app/task/MaaFW/AutoProxy.py`
- `app/task/MaaFW/control_capabilities.py`
- `app/task/MaaFW/interface_preview.py`
- `app/utils/emulator/ldplayer.py`
- `app/utils/emulator/mumu.py`
- `frontend/src/composables/useMaaFWApi.ts`
- `frontend/src/types/script.ts`
- `frontend/src/views/EditView/Script/MaaFWScriptEdit.vue`
- `frontend/src/views/EditView/User/MaaFWDescriptionView.vue`
- `frontend/src/views/EditView/User/MaaFWTaskOptionEditor.vue`
- `frontend/src/views/EditView/User/MaaFWUserEdit.vue`

Implemented or partially implemented:

- MaaFW local image rendering no longer uses renderer `file://` URLs directly.
  Backend asset proxy route was added in `app/api/scripts.py`, and MaaFW
  frontend description/option/user components now build asset URLs through
  `useMaaFWApi.ts`.
- MaaFW interface preview now exposes MaaFW-specific `controlCapabilities`
  for emulator extras support. This is MaaFW-specific and should not be moved
  into generic emulator management.
- MaaFW runtime now attempts to choose package-derived emulator extras for
  MaaFW ADB control. Keep this scoped to MaaFW.
- MaaFW task failure/crash path now tries to close the emulator if it was
  opened by the MaaFW task.
- LDPlayer/MuMu close paths were adjusted to attempt close even when status is
  uncertain.
- User page UI fixes already present:
  - image rendering via asset proxy
  - description divider
  - no default-check/all-select actions
  - preset wording changed toward one-click preset switching
  - account/password wording says local record only
  - multi-level add-task menu with pinned next levels
  - whole-row drag, no visible left drag handle

Important mismatch with latest direction:

- Current code still has MaaFW user-level `Info.Controller` in the user page,
  frontend type, backend schema/config, and runtime selection.
- Current code still has MaaFW user-level `Info.Resource`.
- Next work must move both `Controller` and `Resource` to script-level
  `MaaFWConfig.Info`, then remove them from the MaaFW user page and user
  persistence.

## Next implementation steps

1. Add script-level `Info.Controller` and `Info.Resource`.
   - Add `ConfigItem`s to `MaaFWConfig` before `super().__init__()`.
   - Add fields to `MaaFWConfig_Info` in `app/models/schema.py`.
   - Add fields to `MaaFWScriptConfig.Info` in `frontend/src/types/script.ts`.

2. Remove user-level `Controller` and `Resource`.
   - Remove `Info_Controller` and `Info_Resource` from `MaaFWUserConfig`.
   - Remove fields from `MaaFWUserConfig_Info`.
   - Remove fields from `MaaFWUserConfig` frontend type.
   - Remove MaaFW user page form controls and save paths for these fields.
   - No migration is required; `ConfigBase.load()` normalizes to current
     `ConfigItem`s and drops unknown fields on save.

3. Update MaaFW runtime selection.
   - `_select_controller_name()` should read `self.script_config.get("Info", "Controller")`.
   - `_select_resource_name()` should read `self.script_config.get("Info", "Resource")`.
   - If script-level values are blank, keep the current automatic defaults:
     prefer ADB controller when a script-level emulator is selected, then choose
     the first resource compatible with the effective controller.

4. Update MaaFW script page.
   - Add script-level `Controller` and `Resource` selects.
   - Controller options come from `previewData.controllers`.
   - Resource options are filtered by the effective Controller.
   - Disable Controller/Resource and other interface-dependent controls while
     `interfaceLoading` is true or `previewData` is missing.
   - Loading should use a clear `a-spin`/alert style, not just a small button spinner.

5. Update MaaFW user page.
   - Load script config and cache script-level Controller/Resource locally.
   - Use script-level Controller/Resource for task filtering, preset filtering,
     and `MaaFWTaskOptionEditor` props.
   - Disable preset/add-task/task editor while interface is loading.
   - Keep the existing multi-level add-task menu behavior and whole-row drag.

6. Improve LDPlayer command diagnostics.
   - The pasted log shows `ProcessResult(stdout='', stderr='', returncode=3221225477)`.
   - `3221225477` is `0xC0000005`, a Windows access violation from
     `dnconsole.exe`, not a `MaxWaitTime` timeout.
   - Format LDPlayer `launch`, `quit`, and `list2` failures with action,
     returncode, hex code, stdout, and stderr.
   - Only report timeout when `asyncio.TimeoutError` is actually raised.
   - Avoid large traceback noise during MaaFW emulator cleanup; log the concise
     close failure reason.

## Validation already run before this handoff

These were run before the latest script-level Resource correction:

- `.venv\Scripts\python.exe -m py_compile app/api/scripts.py app/models/schema.py app/task/MaaFW/control_capabilities.py app/task/MaaFW/interface_preview.py app/task/MaaFW/AutoProxy.py app/task/MaaFW/runner.py app/utils/emulator/ldplayer.py app/utils/emulator/mumu.py`
- `yarn prettier --write src/views/EditView/User/MaaFWUserEdit.vue src/views/EditView/User/MaaFWDescriptionView.vue src/views/EditView/User/MaaFWTaskOptionEditor.vue src/composables/useMaaFWApi.ts`
- `yarn eslint src/composables/useMaaFWApi.ts src/views/EditView/User/MaaFWUserEdit.vue src/views/EditView/User/MaaFWDescriptionView.vue src/views/EditView/User/MaaFWTaskOptionEditor.vue`
- `yarn vue-tsc --noEmit`
- `git diff --check` passed with only CRLF warnings

Run validation again after finishing the script-level Controller/Resource move.

The next machine is not expected to have a sufficient MaaFW real-project test
environment. Do not assume `maabbh`/`maabbb` or `maayys` real packages and
matching emulator instances are available there. On that machine, rely on
static checks, type checks, and interface parsing if sample packages exist;
real MaaFW run validation, LDPlayer/MuMu extras behavior, and image rendering
against the user's actual MaaFW packages may need to be verified back on the
original environment or on the user's machine.

Suggested commands:

```powershell
.venv\Scripts\python.exe -m py_compile app/models/config.py app/models/schema.py app/api/scripts.py app/task/MaaFW/AutoProxy.py app/task/MaaFW/control_capabilities.py app/task/MaaFW/interface_preview.py app/utils/emulator/ldplayer.py app/utils/emulator/mumu.py
cd frontend
yarn prettier --write src/types/script.ts src/composables/useMaaFWApi.ts src/views/EditView/Script/MaaFWScriptEdit.vue src/views/EditView/User/MaaFWUserEdit.vue src/views/EditView/User/MaaFWDescriptionView.vue src/views/EditView/User/MaaFWTaskOptionEditor.vue
yarn eslint src/types/script.ts src/composables/useMaaFWApi.ts src/views/EditView/Script/MaaFWScriptEdit.vue src/views/EditView/User/MaaFWUserEdit.vue src/views/EditView/User/MaaFWDescriptionView.vue src/views/EditView/User/MaaFWTaskOptionEditor.vue
yarn vue-tsc --noEmit
cd ..
git diff --check
```

## Notes from failure log

The MaaFW run failure with LDPlayer showed repeated blank command failures,
then cleanup failure:

```text
ProcessResult(stdout='', stderr='', returncode=3221225477)
```

This means `dnconsole.exe` exited with `0xC0000005`. The previous message
`命令执行失败:` was empty because the LDPlayer adapter only included stdout in
the error text. The maximum wait time did not silently fail; the external
command returned before the timeout.
