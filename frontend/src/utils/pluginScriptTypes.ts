import {
  PluginProvidedScriptType,
  type FrontendSurfaceMount,
  type PanelBinding,
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
  const frontendByScriptKey = new Map<
    string,
    Partial<Record<PanelBinding['surface'], FrontendSurfaceMount>>
  >()
  const frontendByPlanConfigType = new Map<string, FrontendSurfaceMount>()

  for (const { providedScript, frontend, info } of Object.values(documents)) {
    if (frontend && info?.plugin_name) {
      for (const { surface, page, scriptType, planType } of frontend.bindings) {
        const artifacts = frontend.pages[page]
        if (!artifacts || surface === 'extra') continue
        const mount = {
          pluginName: info.plugin_name,
          pageId: page,
          revision: frontend.revision,
          activationId: frontend.activationId,
          artifacts,
        }
        if (scriptType) {
          const surfaces = frontendByScriptKey.get(scriptType) ?? {}
          surfaces[surface] = mount
          frontendByScriptKey.set(scriptType, surfaces)
        }
        if (surface === 'plan' && planType) frontendByPlanConfigType.set(planType, mount)
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
