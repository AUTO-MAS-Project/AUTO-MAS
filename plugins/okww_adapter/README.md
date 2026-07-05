# OK-WW Adapter

AUTO-MAS pluginized OK-WW script adapter.

## Scope

- Registers the `Okww` script type from a plugin instead of the host builtin registry.
- Keeps the ok-script behavior from `dev`: `ok-ww.exe -t {TaskIndex} -e`.
- Provides schema-driven script/user forms for `PluginScriptEdit` and `PluginUserEdit`.
- Moves OK-WW config-file service endpoints to plugin routes:
  - `/plugin/okww/configs/list`
  - `/plugin/okww/configs/update`
  - `/plugin/okww/configs/batch-update`

## Compatibility Notes

The host still keeps legacy `OkwwConfig` / `OkwwUserConfig` classes so existing config
files can load. New plugin records are stored through `PluginScriptConfig`.

The old embedded Vue `OkwwConfigEditor` is not wired into the plugin UI yet; the backend
routes are present so a plugin page or schema action can be added next.
