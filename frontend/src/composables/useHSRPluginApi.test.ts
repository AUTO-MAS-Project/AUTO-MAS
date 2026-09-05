import { describe, expect, it } from 'vitest'

import { getHSRDroppedOverrides } from './useHSRPluginApi'

describe('getHSRDroppedOverrides', () => {
  it('原样读出后端 dropped_overrides 里的失效覆盖键', () => {
    const form = {
      dropped_overrides: [
        {
          key: 'currencyWars.removed',
          reason: 'unknown' as const,
          value: true,
          message: 'currencyWars.removed：当前原生配置没有该字段',
        },
        {
          key: 'currencyWars.mode',
          reason: 'type' as const,
          value: 'overclock',
          message: 'currencyWars.mode：保存的值类型与原生配置不一致',
        },
      ],
    }
    expect(getHSRDroppedOverrides(form)).toEqual(form.dropped_overrides)
  })

  it('没有字段、空表单、缺 key 的条目都得到空数组或被跳过', () => {
    expect(getHSRDroppedOverrides(undefined)).toEqual([])
    expect(getHSRDroppedOverrides(null)).toEqual([])
    expect(getHSRDroppedOverrides({})).toEqual([])
    expect(getHSRDroppedOverrides({ dropped_overrides: undefined })).toEqual([])
    const loose = { dropped_overrides: [{ reason: 'unknown', value: 1 }, null] } as unknown as {
      dropped_overrides: never[]
    }
    expect(getHSRDroppedOverrides(loose)).toEqual([])
  })

  it('未知 reason 归为 unknown，缺 message 补空串', () => {
    const loose = { dropped_overrides: [{ key: 'k', reason: 'weird' }] } as unknown as {
      dropped_overrides: never[]
    }
    expect(getHSRDroppedOverrides(loose)).toEqual([
      { key: 'k', reason: 'unknown', value: undefined, message: '' },
    ])
  })
})
