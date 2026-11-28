import { describe, expect, it } from 'vite-plus/test'
import { PluginState } from '@/api'
import { indexPluginScriptTypes } from './pluginScriptTypes'
import { getAvailablePlanTypes, PLAN_CONFIG_TYPES } from './planTypeRegistry'

describe('新建计划表菜单', () => {
  it('只显示已启用专项的计划表，保留内置类型', () => {
    const plugins = indexPluginScriptTypes({
      maa: {
        uid: 'maa',
        ui: {},
        info: { plugin_name: 'maa_adapter', state: PluginState.ENABLED },
        providedScript: {
          scriptKey: 'MAA',
          scriptConfigType: 'MaaConfig',
          userConfigType: 'MaaUserConfig',
          planConfigType: PLAN_CONFIG_TYPES.MAA,
          supportsGameBinding: true,
          supportsDesktopSession: true,
          hasAccountField: true,
          hasPasswordField: true,
        },
      },
    })
    const types = (enabled: string[], registry = plugins) =>
      getAvailablePlanTypes(enabled, registry).map(plan => plan.configType)
    expect(types(['MAA'])).toContain(PLAN_CONFIG_TYPES.MAA)
    expect(types(['MAA'], indexPluginScriptTypes())).not.toContain(PLAN_CONFIG_TYPES.MAA)
    expect(types(['MAA'])).not.toContain(PLAN_CONFIG_TYPES.MSS)
    expect(types(['MSS'])).toContain(PLAN_CONFIG_TYPES.MSS)
    expect(types(['MSS'])).not.toContain(PLAN_CONFIG_TYPES.MAA)
    expect(types([])).toContain(PLAN_CONFIG_TYPES.UNIVERSAL)
  })
})
