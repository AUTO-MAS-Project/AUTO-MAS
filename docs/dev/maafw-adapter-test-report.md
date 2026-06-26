# MaaFW adapter test report

Date: 2026-06-21

Scope: MaaFW generic adapter implementation, regenerated OpenAPI frontend client, MaaFW user/script edit UI, project update configuration, option parsing/rendering, and same-path runtime conflict handling.

## Test matrix

| Area | Coverage |
| --- | --- |
| Interface loader | JSON/JSONC parsing, imports, i18n-style fields, project metadata, option/case/input fields, task/group/preset snapshots |
| Task options | select/switch/checkbox/input defaults, nested options, preserved unknown storage values, common global/resource/controller/task options |
| Pipeline overrides | typed input substitution, checkbox merge order, resource/controller filtering, common option override order |
| Project updater | full package replacement, incremental package delete handling, empty `version` update skip, GitHub/MirrorChyan source selection review |
| Runtime | ADB-only guard, emulator-required guard, LD/MuMu extra config review, same-path skip lock review |
| Frontend | MaaFW script page ADB-only layout and update settings, user page record-only account/password fields, two-column option editor, safe Markdown/HTML description view |
| OpenAPI | Backend schema changes regenerated into `frontend/src/api` |

## Commands run

Backend syntax check:

```powershell
python -m py_compile app\models\config.py app\models\schema.py app\api\scripts.py app\task\MaaFW\AutoProxy.py app\task\MaaFW\manager.py app\task\MaaFW\project_updater.py app\task\MaaFW\interface_models.py app\task\MaaFW\interface_loader.py app\task\MaaFW\pipeline_override.py app\task\MaaFW\task_config.py app\task\MaaFW\run_plan.py
```

Result: passed.

Focused MaaFW tests:

```powershell
python -m pytest tests\test_maafw_interface_loader.py
```

Result: `21 passed`.

Targeted frontend lint:

```powershell
yarn eslint src/views/EditView/Script/MaaFWScriptEdit.vue src/views/EditView/User/MaaFWUserEdit.vue src/views/EditView/User/MaaFWTaskOptionEditor.vue src/views/EditView/User/MaaFWDescriptionView.vue src/views/setting/TabOthers.vue src/types/settings.ts src/types/script.ts src/composables/useMaaFWApi.ts src/composables/useScriptApi.ts eslint.config.mjs
```

Result: passed.

Renderer build:

```powershell
yarn vite build
```

Result: passed.

Electron main build:

```powershell
yarn build:main
```

Result: passed.

Patch whitespace check:

```powershell
git diff --check
```

Result: passed, with line-ending warnings only.

OpenAPI generated diff check:

```powershell
git diff --ignore-space-at-eol --name-only -- frontend/src/api
```

Result: used to separate real generated API changes from LF/CRLF working-tree noise before staging.

## Known non-gating command

Full frontend lint was also reviewed:

```powershell
yarn lint
```

Result: fails on pre-existing repository-wide style/rule noise outside this MaaFW landing. The targeted lint command above covers all touched frontend business files and passes.

## Manual review notes

- Settings UI now uses Chinese copy for the newly added global GitHub token/API key field.
- `frontend/src/api` was regenerated after backend schema changes; no manual generated-file edits were made during the final review pass.
- The docs site and official repository source were both checked because the VitePress-rendered page alone is harder to inspect programmatically.
- Visual browser checks were not run in this pass; layout risk is mitigated by targeted lint/build plus review of the affected Ant Design Vue layouts, but live UI interaction on desktop remains a follow-up validation item.

## Remaining validation gaps

- No live device/emulator execution.
- No live MirrorChyan/GitHub download-and-install update.
- No PC/PlayCover execution, by design.
- No full repo lint pass because of unrelated existing failures.
