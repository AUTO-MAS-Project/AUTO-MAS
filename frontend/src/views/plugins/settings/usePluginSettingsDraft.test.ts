import { describe, expect, it } from 'vite-plus/test'
import { settingsChanges, usePluginSettingsDraft } from './usePluginSettingsDraft'

describe('插件设置编辑稿', () => {
  it('只把与上次读取不同的字段算作未保存，按分组与字段区分', () => {
    expect(
      settingsChanges(
        { general: { a: 1, b: [1, 2] }, extra: { c: 'x' } },
        { general: { a: 1, b: [1, 2] }, extra: { c: 'y' } }
      )
    ).toEqual([{ group: 'extra', field: 'c' }])
    expect(settingsChanges({ general: { a: 2 } }, { general: {} })).toEqual([
      { group: 'general', field: 'a' },
    ])
  })

  it('放弃恢复上次读取的值；重读时保留未保存的改动，换插件时整体替换', () => {
    const draft = usePluginSettingsDraft()
    draft.reset({ general: { a: 1, b: 'x' } }, { keepDraft: false })
    draft.update('general', 'a', 2)
    expect(draft.dirtyCount.value).toBe(1)

    draft.reset({ general: { a: 1, b: 'y' } }, { keepDraft: true })
    expect(draft.values).toEqual({ general: { a: 2, b: 'y' } })
    expect(draft.dirtyCount.value).toBe(1)

    draft.discard()
    expect(draft.values).toEqual({ general: { a: 1, b: 'y' } })
    expect(draft.dirtyCount.value).toBe(0)

    draft.update('general', 'a', 3)
    draft.reset({ other: { z: true } }, { keepDraft: false })
    expect(draft.values).toEqual({ other: { z: true } })
    expect(draft.dirtyCount.value).toBe(0)
  })

  it('保存成功后基线即为提交的值，重读没成功也不算未保存；保存期间的新改动仍算未保存', () => {
    const draft = usePluginSettingsDraft()
    draft.reset({ general: { a: 1, b: 'x' } }, { keepDraft: false })
    draft.update('general', 'a', 2)
    const submitted = draft.snapshot()
    draft.update('general', 'b', 'late')

    draft.commit(submitted)

    expect(draft.changes.value).toEqual([{ group: 'general', field: 'b' }])
    draft.discard()
    expect(draft.values).toEqual({ general: { a: 2, b: 'x' } })
    expect(draft.dirtyCount.value).toBe(0)
  })
})
