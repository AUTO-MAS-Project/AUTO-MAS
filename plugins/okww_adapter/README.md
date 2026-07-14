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

The script and user edit routes are now resolved from the `Okww` plugin descriptor.
`PluginUserEdit` renders the JSON-file configuration editor through the declared
`client.config_editor` contract and calls the plugin routes above. No host-side
OK-WW configuration endpoint or specialized API client is required.
