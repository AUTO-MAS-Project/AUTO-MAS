import {
  PluginProvidedScriptType,
  type PluginFrontendTargetInfo,
  type PluginRegistryDocument,
} from '@/api'

type PluginScriptType = PluginProvidedScriptType & {
  firstAccountMode: PluginProvidedScriptType.firstAccountMode
  displayName: string
  description: string
}

export function indexPluginScriptTypes(documents: Record<string, PluginRegistryDocument> = {}) {
  const byScriptKey = new Map<string, PluginScriptType>()
  const byScriptConfigType = new Map<string, PluginScriptType>()
  const byUserConfigType = new Map<string, PluginScriptType>()
  const byPlanConfigType = new Map<string, PluginScriptType>()
  const frontendByScriptKey = new Map<string, PluginFrontendTargetInfo>()
  const frontendByPlanConfigType = new Map<string, PluginFrontendTargetInfo>()

  for (const { providedScript, frontend, info } of Object.values(documents)) {
    for (const target of frontend?.targets ?? []) {
      const previous = frontendByScriptKey.get(target.scriptKey)
      frontendByScriptKey.set(target.scriptKey, {
        ...target,
        surfaces: { ...previous?.surfaces, ...target.surfaces },
        aliases: [...(previous?.aliases ?? []), ...target.aliases],
      })
      if (target.planConfigType && (target.surfaces.plan || target.planCreation)) {
        const prior = frontendByPlanConfigType.get(target.planConfigType)
        frontendByPlanConfigType.set(target.planConfigType, {
          ...target,
          surfaces: { ...prior?.surfaces, ...target.surfaces },
          planCreation: target.planCreation ?? prior?.planCreation ?? null,
        })
      }
    }
    if (!providedScript) continue
    const script = {
      ...providedScript,
      firstAccountMode:
        providedScript.firstAccountMode ?? PluginProvidedScriptType.firstAccountMode.DIRECT,
      displayName: info?.display_name || info?.plugin_name || providedScript.scriptKey,
      description: info?.description ?? '',
    }
    byScriptKey.set(script.scriptKey, script)
    byScriptConfigType.set(script.scriptConfigType, script)
    byUserConfigType.set(script.userConfigType, script)
    if (script.planConfigType) byPlanConfigType.set(script.planConfigType, script)
  }
  return {
    byScriptKey,
    byScriptConfigType,
    byUserConfigType,
    byPlanConfigType,
    frontendByScriptKey,
    frontendByPlanConfigType,
  }
}

export type PluginScriptTypes = ReturnType<typeof indexPluginScriptTypes>
