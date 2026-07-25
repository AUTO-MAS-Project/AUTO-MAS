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
