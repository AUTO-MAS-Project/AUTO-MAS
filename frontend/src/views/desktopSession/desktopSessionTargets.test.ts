import { describe, expect, it } from 'vite-plus/test'
import { mergeLegacyDesktopSessionTargets } from './desktopSessionTargets'

const id = (n: number) => `00000000-0000-4000-8000-${n.toString().padStart(12, '0')}`

describe('旧的桌面分身选择并入一并启动清单', () => {
  it('只剔除确定已删除的 id，插件不可用的托管保留，顺序沿用旧选择', () => {
    const queue = id(1)
    const unavailable = id(2)
    const deleted = id(3)
    const script = id(4)
    const known = new Set([queue, unavailable, script])

    expect(
      mergeLegacyDesktopSessionTargets(
        [script],
        [queue.toUpperCase(), deleted, unavailable, script, 'not-a-uuid', 42],
        known
      )
    ).toEqual([script, queue, unavailable])
  })

  it('旧键缺失或不是数组时原样返回一并启动清单', () => {
    expect(mergeLegacyDesktopSessionTargets([id(1)], undefined, new Set())).toEqual([id(1)])
    expect(mergeLegacyDesktopSessionTargets([id(1)], 'x', new Set([id(2)]))).toEqual([id(1)])
  })

  it('合并后最多 100 条', () => {
    const current = Array.from({ length: 99 }, (_, index) => id(index))
    const legacy = [id(200), id(201)]
    const merged = mergeLegacyDesktopSessionTargets(current, legacy, new Set(legacy))
    expect(merged).toHaveLength(100)
    expect(merged.at(-1)).toBe(id(200))
  })
})
