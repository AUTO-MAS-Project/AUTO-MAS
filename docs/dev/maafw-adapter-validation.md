# MaaFW adapter validation notes

Date: 2026-06-21

This document records the external checks used to land the MaaFW generic adapter work. It complements `maafw-adapter-alignment.md` and keeps the evidence separate from the original requirement alignment.

## Official MaaFramework checks

Checked sources:

- MaaFW docs site: <https://maafw.com/docs/1.1-QuickStarted>
- MaaFW Project Interface V2: <https://maafw.com/docs/3.3-ProjectInterfaceV2#interface-json>
- MaaFramework repository: <https://github.com/MaaXYZ/MaaFramework>
- Source files found through the MaaFramework tree:
  - `docs/zh_cn/1.1-快速开始.md`
  - `docs/zh_cn/3.3-ProjectInterfaceV2协议.md`
  - `tools/interface.schema.json`
  - `sample/interface.json`

Confirmed protocol points:

- `ProjectInterface` is represented by `interface.json`; official docs recommend defining it even for projects integrated through a general language.
- `interface_version` is the JSON structure major version and is currently fixed to `2`.
- `github` is the project GitHub repository for version update checks and issue feedback. Official wording expects generic UIs to provide project-release update support instead of separate UI/MaaFW framework update controls.
- `version` is the resource project version used for update checks and client display. Empty `version` therefore cannot safely drive update checks.
- `controller`, `resource`, `task`, `option`, `global_option`, `preset`, `description`, and `icon` are first-class Project Interface fields.
- `description` can be text, a file path, or URL-like content, and supports Markdown style rendering in clients.
- `option` supports at least `select`, `checkbox`, and `input`; the same document also describes `switch` handling through cases/defaults.
- Option filtering must happen before applying pipeline overrides: inactive options for the selected `controller` or `resource` must not produce overrides.
- Pipeline override merge order is `global_option -> resource.option -> controller.option -> task.option`, with later layers overriding earlier layers.
- `input.inputs[].pipeline_type` controls placeholder conversion for `pipeline_override`; documented values include `string`, `int`, and `bool`. The implementation also accepts common numeric aliases used by current script schemas.

Implementation alignment:

- Backend preview now exposes project metadata, ADB-filtered controllers/resources, global/resource/controller/task option names, option inputs/cases/icons/descriptions, and resolved local description files.
- Runtime task normalization and pipeline override generation now include common options and filter them by selected controller/resource.
- Input substitution preserves typed values for bool/int/float-like input fields and keeps string replacement for text placeholders.
- The script page disables automatic update when `interface.version` is empty and shows that the project did not declare a version.

## Upstream MaaFW project checks

Checked projects:

- M9A: <https://github.com/MAA1999/M9A>
- Maa_bbb: <https://github.com/miaojiuqing/Maa_bbb>

M9A observations:

- Latest GitHub release checked during validation: `v4.0.0`, non-prerelease.
- `assets/interface.json` contains `github`, `mirrorchyan_rid: "M9A"`, `mirrorchyan_multiplatform: true`, and both ADB and PC-style controllers.
- `assets/resource/tasks/SwitchAccount.json` in the latest upstream release exposes the `切换账号` task option `目标账号(可选)` as an `input` option with input field `账号`.
- The same task writes the user-provided account through `pipeline_override`; no password option was found.
- Older local M9A release packages may not have this task option, so AUTO-MAS account/password fields remain record-only and do not auto-link to MaaFW task options.

Maa_bbb observations:

- Latest GitHub release checked during validation: `v1.12.8`, non-prerelease.
- `assets/interface.json` contains project description/icon metadata, `mirrorchyan_rid: "Maa_bbb"`, and `mirrorchyan_multiplatform: true`.
- The project declares desktop and Android/ADB style surfaces. The current AUTO-MAS adapter only presents ADB-compatible controller/resource choices.

## MirrorChyan checks

Checked source:

- <https://github.com/MirrorChyan/docs>

Confirmed update contract:

- Latest resource endpoint shape: `GET https://mirrorchyan.com/api/resources/{res_id}/latest`.
- `current_version` is recommended for update checks.
- `cdk` is optional; docs caution against exposing CDK in plaintext logs.
- Responses include `code`, `msg`, and data such as `version_name`, `url`, and `release_note`.
- Incremental update metadata can include deleted path lists; the implementation recognizes `deleted_dir` along with existing deletion aliases.

Implementation alignment:

- MaaFW project update source is explicit: `MirrorChyan` or `GitHub`.
- Script-level CDK/token fields are optional overrides; empty values fall back to MAS global update configuration.
- GitHub updates use `interface.github` and the selected channel: `stable` selects a non-prerelease release, `beta` selects a prerelease release. Internal channels are intentionally not exposed.
- MirrorChyan updates use `interface.mirrorchyan_rid`; multiplatform behavior is derived from `interface.mirrorchyan_multiplatform`.
- The update path sanitizes logged URLs through the existing security helper.

## Self-review checklist

- ADB-only runtime: user-facing script/user pages no longer expose manual ADB address, Win32, Gamepad, or PlayCover runtime controls for MaaFW.
- Account/password behavior: fields are visible and saved, but only for AUTO-MAS records; they do not select tasks or write MaaFW options.
- Same-path conflict: a normalized project path lock marks repeated same-path starts as `跳过` and releases the lock on finalization or crash.
- Resource filtering: user page resource selection uses the effective default controller when the stored controller is empty.
- OpenAPI: backend schema changes were propagated by regenerating the frontend client instead of manually editing generated API files.

## Residual risks

- No live Android emulator or real MaaFW task run was executed in this validation pass.
- No live project update install was executed against GitHub or MirrorChyan; update behavior is covered by unit-level package application tests and source API review.
- PC, Win32, Gamepad, and PlayCover execution are intentionally out of scope for this landing.
- Full repository lint still has existing unrelated failures; targeted frontend lint and builds are used as the landing gate.
