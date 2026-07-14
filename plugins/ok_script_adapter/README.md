# OK Script Adapter

`automas_plugin_ok_script_adapter` adapts projects built on the `ok-script` framework
to AUTO-MAS. It is a generic adapter: project identity, task choices, configuration
directory and launch protocol come from the selected project Manifest, not from an
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
root, game launch settings and runtime limits. On save, a valid Manifest fills the
resource name and project label.

The adapter accepts a project that exposes `pyappify.yml` or supported installed-app
metadata. It selects `framework-cli`, `main-script` or `legacy-exe` at runtime. The
same inspection can be checked from the console shell:

```powershell
python -m ok_script_adapter.shell inspect <project-root>
python -m ok_script_adapter.shell --help
```

User JSON is copied into `data/<script-id>/<user-id>/ConfigFile`. Missing JSON files
are added recursively without overwriting existing user files. During execution the
adapter publishes stdout, stderr, project logs and supported structured events to MAS.

## Compatibility and Upgrade

New records use `PluginScriptConfig` with `Meta.PluginTypeKey=OkScript`. Historical
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
