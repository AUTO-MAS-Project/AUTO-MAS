import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { parse } from '@vue/compiler-sfc'

describe('quick configuration panel visibility', () => {
  // BetterGI 不在列：其快速配置开关已隐藏，改由配置来源派生（直控 = 关，脚本 / 用户 = 开），
  // 于是选择器不再渲染该开关；面板形态仍按来源决定（见本文件最后一条用例）。
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

  it('derives BetterGI quick configuration from the config source', () => {
    // 开关已从 BetterGI 页隐藏：值随配置来源派生（直控 = 关，脚本 / 用户 = 开），切来源时
    // 与 Mode 一起保存；原「关闭前先落盘一条龙组设置」的处理移到切到直控时（面板将隐藏）。
    const source = readFileSync(new URL('./BetterGIUserEdit.vue', import.meta.url), 'utf8')
    const template = parse(source).descriptor.template!.content
    expect(template).not.toMatch(/quick-config|enableQuickConfiguration|Info\.IfQuickConfig/)
    expect(source).not.toContain('handleQuickConfigChange')

    const handler = source.slice(
      source.indexOf('const handleConfigModeChange ='),
      source.indexOf('// ----- 原生 GUI 设置会话')
    )
    expect(handler).toContain("const nextQuickConfig = value !== '直控'")
    expect(handler).toMatch(
      /Info: \{ Mode: formData\.Info\.Mode, IfQuickConfig: nextQuickConfig \}/
    )
    expect(handler).toMatch(
      /if \(!saved\) \{[\s\S]*?formData\.Info\.IfQuickConfig = previousQuickConfig/
    )
    // 切到直控（派生为关）前先把未落盘的一条龙组设置刷掉，避免面板隐藏后丢改动
    expect(handler.indexOf('await saveDragonGroupSettings(true, dragonGroupSaveSel)')).toBeLessThan(
      handler.indexOf('formData.Info.IfQuickConfig = nextQuickConfig')
    )
    expect(handler).toMatch(/!\(await saveDragonGroupSettings\([\s\S]*?\)\)\s*\)\s*return/)
    // 加载时同样按来源归一（存量「直控 + 开」不再残留在表单里）
    expect(source).toContain("formData.Info.IfQuickConfig = formData.Info.Mode !== '直控'")
  })

  // Whimbox 已接入快速配置（2026-09 维护者决策，为后续特殊功能预留），
  // 不再列进「无开关」名单；其绑定形态见下一条用例
  for (const name of ['General', 'HSR', 'BAAH', 'ZzzOd']) {
    it(`${name} has no inactive or newly invented quick switch`, () => {
      const source = readFileSync(new URL(`./${name}UserEdit.vue`, import.meta.url), 'utf8')
      const template = parse(source).descriptor.template!.content
      expect(template).not.toMatch(/quick-config|enableQuickConfiguration|Info.IfQuickConfig/)
    })
  }

  it('Whimbox binds the quick switch to the user field via the base selector', () => {
    // 三态来源 + 快速配置：Section 把基座开关绑定到 Info.IfQuickConfig 并上抛变更，
    // 页面处理器按字段路径保存（当前消费点：原生态任务前物化面板覆盖集、结束还原）
    const source = readFileSync(
      new URL('../../WhimboxUserEdit/BasicInfoSection.vue', import.meta.url),
      'utf8'
    )
    const template = parse(source).descriptor.template!.content
    expect(template).toContain(':quick-config="formData.Info.IfQuickConfig"')
    expect(template).toContain('@quick-config-change=')

    const page = readFileSync(new URL('./WhimboxUserEdit.vue', import.meta.url), 'utf8')
    expect(page).toContain('handleQuickConfigChange')
    expect(page).toContain("handleFieldSave('Info.IfQuickConfig', value)")
  })
})
