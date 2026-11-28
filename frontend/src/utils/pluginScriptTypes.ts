import {
  PluginProvidedScriptType,
  PluginState,
  type FrontendSurfaceMount,
  type PanelBinding,
  type PluginRegistryDocument,
} from '@/api'

type PluginScriptType = PluginProvidedScriptType & {
  firstAccountMode: PluginProvidedScriptType.firstAccountMode
  displayName: string
  description: string
}

export function compatibleWheel(mount?: FrontendSurfaceMount) {
  const web = mount?.artifacts.web
  if (mount && web?.panelApi === 1) return { ...mount, entry: web.entry }
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

  const settingsPanels = new Map<string, FrontendSurfaceMount>()
  const notificationPanels = new Map<string, FrontendSurfaceMount>()
  for (const { uid, providedScript, frontend, info } of Object.values(documents)) {
    if (frontend && info?.plugin_name && info.state === PluginState.ENABLED) {
      for (const { surface, page, scriptType, planType, channel } of frontend.bindings) {
        const artifacts = frontend.pages[page]
        if (!artifacts || surface === 'extra') continue
        const mount = {
          pluginName: info.plugin_name,
          pageId: page,
          revision: frontend.revision,
          activationId: frontend.activationId,
          artifacts,
        }
        if (surface === 'settings') settingsPanels.set(uid, mount)
        if (surface === 'notification' && channel === info.plugin_name)
          notificationPanels.set(channel, mount)
        if (scriptType && scriptType === providedScript?.scriptKey) {
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
    settingsPanels,
    notificationPanels,
    frontendByScriptKey,
    frontendByPlanConfigType,
  }
}

export type PluginScriptTypes = ReturnType<typeof indexPluginScriptTypes>
