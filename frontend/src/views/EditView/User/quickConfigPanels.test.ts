import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { parse } from '@vue/compiler-sfc'

describe('quick configuration panel visibility', () => {
  // BetterGI 不在列：本 PR 决定「快速配置不作为配置来源开关」，该页面恢复原貌——
  // 任务配置卡片常显、开关回到 GeneralConfigModeSelector 内（按来源而非开关决定面板形态）。
  // M9A 也不在列：它已是 MaaFW 的特调类型，页面就是 MaaFWUserEdit.vue，见下一条
  for (const name of ['MAA', 'SRC', 'MaaEnd', 'Okww', 'OkNte']) {
    it(`${name} keeps its switch outside the conditional panel`, () => {
      const source = readFileSync(new URL(`./${name}UserEdit.vue`, import.meta.url), 'utf8')
      const template = parse(source).descriptor.template!.content
      const panel =
        {
          MAA: '<TaskPipelineSection',
          SRC: '<StageConfigSection',
        }[name] || '<a-card v-if="formData.Info.IfQuickConfig"'
      const start = template.indexOf(panel)
      expect(start).toBeGreaterThan(-1)
      expect(template.slice(start, template.indexOf('>', start))).toContain(
        'v-if="formData.Info.IfQuickConfig"'
      )
      expect(template.indexOf('@change="handleQuickConfigChange"')).toBeLessThan(start)
      expect(template).not.toContain('@quick-config-change=')
      expect(template.match(/@change="handleQuickConfigChange"/g)).toHaveLength(1)
      expect(source).toMatch(
        /if \(!\(await (handleFieldSave|saveField)\('Info.IfQuickConfig', value\)\)\)/
      )
      expect(source).toContain('formData.Info.IfQuickConfig = previous')
    })
  }

  it('MaaFW has neither a quick configuration switch nor a config source selector', () => {
    // MaaFW 是通用引擎，没有可退回的原生配置；两个控件对它没有所指，页面不再提供入口。
    const page = readFileSync(new URL('./MaaFWUserEdit.vue', import.meta.url), 'utf8')
    const section = readFileSync(
      new URL('./MaaFWUserEdit/BasicInfoSection.vue', import.meta.url),
      'utf8'
    )
    expect(page).not.toContain('handleQuickConfigChange')
    expect(page).not.toContain('v-if="formData.Info.IfQuickConfig"')
    expect(page).not.toContain('handleConfigModeChange')
    expect(section).not.toContain('GeneralConfigModeSelector')
    expect(section).not.toContain('v-if="formData.Info.IfQuickConfig"')
  })

  it('keeps the source selector quick configuration opt-in only', () => {
    // 选择器里的快速配置项只在调用方声明了 v-model 时渲染，未接入的专项不会出现死开关。
    const source = readFileSync(new URL('./GeneralConfigModeSelector.vue', import.meta.url), 'utf8')
    expect(source).toContain('v-if="quickConfig !== undefined"')
  })

  it('flushes BetterGI task settings before hiding the panel', () => {
    const source = readFileSync(new URL('./BetterGIUserEdit.vue', import.meta.url), 'utf8')
    const handler = source.slice(
      source.indexOf('const handleQuickConfigChange ='),
      source.indexOf('const toggleGroup =')
    )
    expect(handler.indexOf('await saveDragonGroupSettings(true, dragonGroupSaveSel)')).toBeLessThan(
      handler.indexOf('formData.Info.IfQuickConfig = value')
    )
    expect(handler).toMatch(/!\(await saveDragonGroupSettings\([\s\S]*?\)\)\s*\)\s*return/)
    expect(source).toContain('masConfigEnabled.value\n')
    expect(source).toContain('const globalUserId = masConfigEnabled.value ?')
  })

  for (const name of ['General', 'HSR', 'BAAH', 'ZzzOd']) {
    it(`${name} has no inactive or newly invented quick switch`, () => {
      const source = readFileSync(new URL(`./${name}UserEdit.vue`, import.meta.url), 'utf8')
      const template = parse(source).descriptor.template!.content
      expect(template).not.toMatch(/quick-config|enableQuickConfiguration|Info.IfQuickConfig/)
    })
  }
})
