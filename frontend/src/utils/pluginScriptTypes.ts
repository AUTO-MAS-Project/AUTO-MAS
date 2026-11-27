import type { PluginProvidedScriptType, PluginRegistryDocument } from '@/api'

type PluginScriptType = PluginProvidedScriptType & { displayName: string; description: string }

export function indexPluginScriptTypes(documents: Record<string, PluginRegistryDocument> = {}) {
  const byScriptKey = new Map<string, PluginScriptType>()
  const byScriptConfigType = new Map<string, PluginScriptType>()
  const byUserConfigType = new Map<string, PluginScriptType>()
  const byPlanConfigType = new Map<string, PluginScriptType>()

  for (const { providedScript, info } of Object.values(documents)) {
    if (!providedScript) continue
    const script = {
      ...providedScript,
      displayName: info?.display_name || info?.plugin_name || providedScript.scriptKey,
      description: info?.description ?? '',
    }
    byScriptKey.set(script.scriptKey, script)
    byScriptConfigType.set(script.scriptConfigType, script)
    byUserConfigType.set(script.userConfigType, script)
    if (script.planConfigType) byPlanConfigType.set(script.planConfigType, script)
  }
  return { byScriptKey, byScriptConfigType, byUserConfigType, byPlanConfigType }
}

export type PluginScriptTypes = ReturnType<typeof indexPluginScriptTypes>
