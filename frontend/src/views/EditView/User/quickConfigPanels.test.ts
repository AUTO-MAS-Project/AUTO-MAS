import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { parse } from '@vue/compiler-sfc'

describe('quick configuration panel visibility', () => {
  // 以下专项保留快速配置开关（页面内 handleQuickConfigChange + 面板按开关门控）。
  // BetterGI 不在列：已移除「是否启用快速配置」选项，直控下固定接管写入（见底部断言组）。
  for (const name of ['MAA', 'M9A', 'SRC', 'MaaEnd', 'Okww', 'OkNte']) {
    it(`${name} keeps its switch outside the conditional panel`, () => {
      const source = readFileSync(new URL(`./${name}UserEdit.vue`, import.meta.url), 'utf8')
      const template = parse(source).descriptor.template!.content
      const panel =
        {
          MAA: '<TaskPipelineSection',
          M9A: '<TaskQueueSection',
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

  it('keeps BetterGI source-driven panel independent of quick config', () => {
    // BetterGI 已移除「是否启用快速配置」选项：页面不再出现开关或字段。
    const source = readFileSync(new URL('./BetterGIUserEdit.vue', import.meta.url), 'utf8')
    expect(source).not.toContain('handleQuickConfigChange')
    expect(source).not.toContain('Info.IfQuickConfig')
  })

  for (const name of ['BetterGI', 'General', 'HSR', 'BAAH', 'ZzzOd']) {
    it(`${name} has no inactive or newly invented quick switch`, () => {
      const source = readFileSync(new URL(`./${name}UserEdit.vue`, import.meta.url), 'utf8')
      const template = parse(source).descriptor.template!.content
      expect(template).not.toMatch(/quick-config|enableQuickConfiguration|Info.IfQuickConfig/)
    })
  }
})
