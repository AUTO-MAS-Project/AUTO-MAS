# OK-WW Adapter

AUTO-MAS pluginized OK-WW script adapter.

## Scope

- Registers the `Okww` script type from a plugin instead of the host builtin registry.
- Keeps the ok-script behavior from `dev`: `ok-ww.exe -t {TaskIndex} -e`.
- Provides schema-driven script/user forms for `PluginScriptEdit` and `PluginUserEdit`.
- Stores simple-mode settings in `data/{script}/Default/ConfigFile` and detailed-mode
  settings per user.
- Opens the native OK-WW settings window through the schema action session, then saves
  its configuration back to plugin-managed storage.
- Manages the high-frequency DailyTask fields in AUTO-MAS while preserving other OK-WW
  settings for its native UI.
- Resolves the actual game client from the official launcher or WeGame before launch.

## Compatibility Notes

The host still keeps legacy `OkwwConfig` / `OkwwUserConfig` classes so existing config
files can load. New plugin records are stored through `PluginScriptConfig`.

The script and user edit routes are now resolved from the `Okww` plugin descriptor.
No host-side OK-WW configuration endpoint, generated API client, or specialized Vue
editor is required.
