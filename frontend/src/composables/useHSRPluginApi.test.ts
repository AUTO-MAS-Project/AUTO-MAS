import { describe, expect, it } from 'vitest'

import { parseHSRDroppedOverrides } from './useHSRPluginApi'

describe('parseHSRDroppedOverrides', () => {
  it('还原后端编进 warnings 的失效覆盖键', () => {
    const warnings = [
      JSON.stringify({
        kind: 'dropped_override',
        key: 'currencyWars.removed',
        reason: 'unknown',
        value: true,
        message: 'currencyWars.removed：当前原生配置没有该字段',
      }),
      JSON.stringify({
        kind: 'dropped_override',
        key: 'currencyWars.mode',
        reason: 'type',
        value: 'overclock',
        message: 'currencyWars.mode：保存的值类型与原生配置不一致',
      }),
    ]
    expect(parseHSRDroppedOverrides(warnings)).toEqual([
      {
        key: 'currencyWars.removed',
        reason: 'unknown',
        value: true,
        message: 'currencyWars.removed：当前原生配置没有该字段',
      },
      {
        key: 'currencyWars.mode',
        reason: 'type',
        value: 'overclock',
        message: 'currencyWars.mode：保存的值类型与原生配置不一致',
      },
    ])
  })

  it('普通文本、其他 kind 与缺 key 的条目都跳过', () => {
    const warnings = [
      '读取 config.yaml 时缺少注释',
      JSON.stringify({ kind: 'something_else', key: 'x' }),
      JSON.stringify({ kind: 'dropped_override', reason: 'unknown' }),
      JSON.stringify([1, 2]),
      'not json {',
    ]
    expect(parseHSRDroppedOverrides(warnings)).toEqual([])
    expect(parseHSRDroppedOverrides(undefined)).toEqual([])
    expect(parseHSRDroppedOverrides(null)).toEqual([])
  })

  it('未知 reason 归为 unknown', () => {
    const warnings = [JSON.stringify({ kind: 'dropped_override', key: 'k', reason: 'weird' })]
    expect(parseHSRDroppedOverrides(warnings)[0]).toMatchObject({ key: 'k', reason: 'unknown' })
  })
})
