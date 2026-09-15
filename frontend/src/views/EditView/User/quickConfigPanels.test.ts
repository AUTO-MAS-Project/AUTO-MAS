import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { parse } from '@vue/compiler-sfc'

describe('quick configuration panel visibility', () => {
  for (const name of ['MAA', 'M9A', 'SRC', 'MaaFW', 'MaaEnd', 'Okww', 'OkNte', 'BetterGI']) {
    it(`${name} keeps its switch outside the conditional panel`, () => {
      const source = readFileSync(new URL(`./${name}UserEdit.vue`, import.meta.url), 'utf8')
      const template = parse(source).descriptor.template!.content
      const panel =
        {
          MAA: '<TaskPipelineSection',
          M9A: '<TaskQueueSection',
          SRC: '<StageConfigSection',
          MaaFW: '<TaskQueueSection',
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

  it('keeps the source selector free of quick configuration props and events', () => {
    const source = readFileSync(new URL('./GeneralConfigModeSelector.vue', import.meta.url), 'utf8')
    expect(source).not.toMatch(/quickConfig|quick-config|enableQuickConfiguration/)
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
