# OK Script Adapter

`automas_plugin_ok_script_adapter` adapts projects built on the `ok-script` framework
to AUTO-MAS. It is a generic adapter: project identity, task choices, configuration
directory and launch protocol candidates come from the selected project descriptor, not from an
OK-EF, OK-WW or OK-NTE default.

## Installation and Discovery

The root `pyproject.toml` declares this package in the `plugins` dependency group and
uv workspace. A development environment must synchronize that workspace before
starting AUTO-MAS:

```powershell
python scripts/sync_plugin_workspace.py --check
uv sync --group plugins
```

The package exposes the `auto_mas.plugins` entry point `ok_script_adapter`. In a
packaged deployment AUTO-MAS discovers the entry point through its isolated plugin
site-packages directory. Do not install the adapter into the system Python or add a
global proxy setting.

## Enable and Verify

Enable the `ok_script_adapter` instance in Plugin Management, then create an
`ok-script` project from Script Management. The project editor stores only the selected
root, game launch settings and runtime limits. On save, a valid descriptor fills the
resource name and project label.

The adapter accepts a project that exposes `pyappify.yml`, `app.json`, or a supported
`config.py` source/install layout. `ProjectParser` reads those files with AST/JSON
parsers and never imports the project module. Descriptor v2 records the real config
source/target/folder, ordered tasks, metadata sources, protocol candidates,
capabilities, diagnostics, and a change fingerprint.

`framework-cli`, `main-script`, and `legacy-exe` are candidates only. Automatic
execution remains disabled until a registered provider explicitly marks that project
runtime as verified. The same inspection can be checked from the console shell:

```powershell
python -m ok_script_adapter.shell inspect <project-root>
python -m ok_script_adapter.shell --help
```

User JSON is copied into `data/<script-id>/<user-id>/ConfigFile`. Missing JSON files
are added recursively without overwriting existing user files. During execution the
adapter publishes stdout, stderr, project logs and supported structured events to MAS.

## Execution Architecture

Project inspection and execution are separate contracts. `ProjectParser` produces the
versioned descriptor, and `ExecutionPlanner` compiles an immutable `ExecutionPlan` from
that descriptor, the registered provider, the selected task, and an explicit protocol
probe result. Planning does not start a process or read a runtime log.

In the MAS production path, `RunController` is the only owner of the ok-script process.
It uses the host `ProcessManager` and centralizes stdout/stderr forwarding, v1 JSONL
events, legacy text-log fallback, process exit, timeout, cancellation, cleanup, and
retry. `OkScriptAutoProxyTask` remains the adapter boundary for game policy, user state,
reports, notifications, and configuration injection/write-back/restore.

Retries are deliberately `whole-run`: every attempt executes the same complete
`TaskInvocation`. Event protocol v1 has no stable selector, run ID, dependency graph,
idempotency flag, or retryability contract, so task names and console text are never
used to guess a child task to rerun. Selective child-task retry requires a future
versioned upstream event contract and provider capability declaration.

`OkShellRunner.run()` remains available to `python -m ok_script_adapter.shell` as an
independent synchronous CLI shell. It is not a fallback production executor for MAS;
the MAS adapter only reuses its command-building capability.

## Game Launch and Cleanup

Game launch policy belongs to each registered provider. A `GameLaunchDescriptor`
separates the program MAS starts, the process that proves the game is ready, and the
processes used for end-of-task cleanup. This avoids treating all games as a single
executable path.

- `direct`: MAS launches the game executable and tracks that same game process.
- `launcher`: MAS launches a launcher but tracks the declared game-body process. For
  OK-NTE this is `NTEGame.exe` or `NTEGlobalGame.exe` followed by `HTGame.exe`.
- `script-managed`: MAS does not launch the game before the task; ok-script owns that
  startup, while MAS still retains its configured cleanup targets.
- `attach`: MAS requires an already-running declared game process and does not launch
  another instance.
- `uri`: MAS opens the provider URI and tracks the declared game process.

`Game.Enabled=false` or `Game.LaunchBeforeTask=false` only changes the pre-task launch
mode to `script-managed`. It does not disable end-of-task cleanup. On manual stop,
`Game.KillGameOnManualStop` remains the single switch that decides whether MAS closes
the game. The game-path resolve endpoint keeps its existing `data.path` and
`data.formPatch` response members and additionally returns role-aware
`data.resolution`. When more than one launch or ready target is found, it returns HTTP
409 with the diagnostic candidates instead of selecting a path arbitrarily.

The current lifecycle checks use static fixtures and fake process managers only. They
do not prove real launcher behavior, installed-game layouts, or game/device E2E. Each
provider remains responsible for declaring its `runtime_verified` state; OK-NTE remains
unverified until its real success and failure logs have been validated.

## Configuration Schema and Validation

Configuration responses expose FieldSchema v1 without breaking the current editor.
Each file keeps the legacy `fields` and `currentData` members and also returns a typed
`fieldSchema` plus an independent `snapshot`. The schema records value and item types,
typed choices, defaults, nullability, validation constraints, source confidence and
`omitWhenUnset`; the snapshot records current values, revision and source fingerprint.

Schema sources are resolved in this order: statically proven upstream task declarations,
registered provider additions, then low-confidence inference from existing JSON values.
Projects such as OK-GF2 can therefore return `schema_only` fields before their first JSON
file exists. An upstream default is displayed with `isSet=false` and is not written until
the user explicitly changes that field. Existing unknown enum values and unknown JSON keys
are preserved. Numeric choices, arrays and objects are not coerced to strings.

`POST /plugin/ok-script/configs/batch-update` accepts `mode=validate` or `mode=commit`.
The default remains `commit` for existing clients. Both modes validate every file and
return draft diffs; `validate` never writes. A field error returns HTTP 422 with per-file,
per-field errors and writes no file from that batch. Successful commits use the existing
per-file atomic replacement after recursively preserving untouched keys.

## Independent Configuration Workspace

After the plugin is enabled, the main menu provides **ok-script 配置**. This is a
plugin-owned Custom Element page packaged with the adapter wheel. It lists already saved
`OkScript` scripts and their users, then uses the existing config list and batch-update
contracts to load, validate, save, or discard a user's JSON configuration changes.

The page deliberately does not create, delete, or edit the host script/user records. It is
an independent workspace used to validate the plugin frontend contract while the host editor
does not yet expose a generic Custom Element editor slot. The existing script and user edit
routes remain the source of truth for basic information, game settings, lifecycle actions,
and navigation.

The Custom Element only uses `window.pluginAPI`, CSS variables exposed by AUTO-MAS, and CSS
selectors rooted at `auto-mas-ok-script-workspace`; it does not import host Vue internals or
override global styles. Static/plugin tests cover its package resources and lifecycle
contract. Real desktop light/dark, resizing, and plugin reload checks still require a later
manual runtime session and are not implied by those tests.

Time-like field names are deliberately not guessed. A project or provider must declare
whether a value is a time of day, datetime, duration, or Unix timestamp before a dedicated
control and serialization rule can be added. The current host editor also still saves
dirty values when leaving or switching users; explicit Save/Discard interaction requires
the separately reviewed host editor-slot work and is not implemented by this backend stage.

## Compatibility and Upgrade

New records use `PluginScriptConfig` with `Meta.PluginTypeKey=OkScript`. Saved Manifest
v1 JSON remains readable and is converted in memory to descriptor v2; newly saved
inspection data always uses v2. Historical
`OkefConfig` and `OkefUserConfig` remain readable only for migration and old links;
they are not the new-project protocol. OK-WW remains its own plugin and is not changed
by this adapter.

When an upstream project updates, reselect or save its root once so the adapter can
refresh project metadata, then open each affected MAS user configuration to copy only
new default JSON files. Do not overwrite the isolated user directory from upstream.

## Troubleshooting

- Plugin unavailable: run `python scripts/sync_plugin_workspace.py --check`, then
  synchronize the plugin dependency group and restart AUTO-MAS.
- Project inspection fails: select the project root containing `pyappify.yml` or the
  installed application metadata, not the game executable or a `configs` subdirectory.
- No terminal result: inspect the MAS task log first. Legacy executables are not
  considered successful from their launcher exit code alone; the adapter waits for a
  terminal event or project log result.
- A daily report text window appears: this is handled only by the provider that
  explicitly supports that report. Generic projects and OK-WW do not enumerate or
  close unrelated text-editor windows.
