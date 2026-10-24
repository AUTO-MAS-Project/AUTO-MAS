import { describe, expect, it, vi } from 'vitest'

// comboxLabel 只需要「按 key 取译文」；mock 掉 i18n 实例，测试就不依赖浏览器环境
vi.mock('@/i18n', () => ({
  translate: (key: string) => `t(${key})`,
}))

import { comboxLabel, isQueueTaskOption, isScriptTaskOption } from './comboxLabel'

describe('comboxLabel', () => {
  it('labelKey 项整条按词表翻译', () => {
    expect(comboxLabel({ label: '未选择', value: '-', labelKey: 'common.notSelected' })).toBe(
      't(common.notSelected)'
    )
  })

  it('队列与脚本项按 kind + name 拼装本地化文案', () => {
    expect(comboxLabel({ label: '队列 - 早班', value: 'q1', kind: 'queue', name: '早班' })).toBe(
      't(combox.queue)'
    )
    expect(
      comboxLabel({
        label: '脚本 - MAA - 主号',
        value: 's1',
        kind: 'script',
        scriptType: 'MAA',
        name: '主号',
      })
    ).toBe('t(combox.scriptType.MAA) - 主号')
  })

  it('旧后端没带新字段时逐字回退 label', () => {
    expect(comboxLabel({ label: '队列 - 早班', value: 'q1' })).toBe('队列 - 早班')
  })
})

describe('任务分类', () => {
  it('新结构按 kind 分类', () => {
    expect(isQueueTaskOption({ label: '队列 - x', value: 'q', kind: 'queue' })).toBe(true)
    expect(isQueueTaskOption({ label: 'MAA - x', value: 's', kind: 'script' })).toBe(false)
    expect(isQueueTaskOption({ label: '未选择', value: '-', kind: 'placeholder' })).toBe(false)
    expect(isScriptTaskOption({ label: 'MAA - x', value: 's', kind: 'script' })).toBe(true)
    expect(isScriptTaskOption({ label: '队列 - x', value: 'q', kind: 'queue' })).toBe(false)
    expect(isScriptTaskOption({ label: '未选择', value: '-', kind: 'placeholder' })).toBe(false)
  })

  it('旧结构（缺 kind）沿用中文前缀识别队列，不再被当成脚本任务', () => {
    const legacyQueue = { label: '队列 - 早班', value: 'q1' }
    const legacyScript = { label: '脚本 - MAA - 主号', value: 's1' }
    expect(isQueueTaskOption(legacyQueue)).toBe(true)
    expect(isScriptTaskOption(legacyQueue)).toBe(false)
    expect(isQueueTaskOption(legacyScript)).toBe(false)
    expect(isScriptTaskOption(legacyScript)).toBe(true)
  })

  it('空选项既不是队列也不是脚本', () => {
    expect(isQueueTaskOption(undefined)).toBe(false)
    expect(isScriptTaskOption(undefined)).toBe(false)
  })
})
