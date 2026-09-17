import { describe, expect, it } from 'vitest'
import {
  createPipProgressParser,
  estimateDownloadProgress,
} from './dependencyService'

/**
 * 下载阶段的进度估计：pip 逐行报 Collecting，总包数此刻未知。
 *
 * 锁住三条语义：起点是 40%、单调不减、封顶 70%（70-80 留给「开始安装」那一跳）。
 */

describe('estimateDownloadProgress', () => {
  it('刚开始下载时停在 40%', () => {
    expect(estimateDownloadProgress(0)).toBe(40)
  })

  it('随已见包数单调增长', () => {
    const values = [0, 1, 5, 20, 60, 200].map(estimateDownloadProgress)
    for (let i = 1; i < values.length; i += 1) {
      expect(values[i]).toBeGreaterThan(values[i - 1])
    }
  })

  it('永不超过 70%，且到得了 70% 附近', () => {
    expect(estimateDownloadProgress(80)).toBeLessThanOrEqual(70)
    expect(estimateDownloadProgress(1000)).toBeLessThanOrEqual(70)
    expect(estimateDownloadProgress(1000)).toBeGreaterThanOrEqual(69)
  })

  it('见到二十来个包时已经过半，用户能看出在动', () => {
    expect(estimateDownloadProgress(20)).toBeGreaterThan(50)
  })
})

/**
 * 跨 chunk 累计：Node 的管道不按行送达，一行 `Collecting xxx` 会被拆进相邻两个 chunk。
 * 按单个 chunk 匹配时两半都匹配不上，包数漏计、进度就此停住。
 */

describe('createPipProgressParser', () => {
  it('一行被拆成两个 chunk 时仍算一个包', () => {
    const seen: number[] = []
    const parser = createPipProgressParser(p => seen.push(p))

    parser.push('Collect')
    // 半行不解析，等下一个 chunk
    expect(parser.packages()).toBe(0)
    expect(seen).toEqual([])

    parser.push('ing aaa-bbb==1.0\n')
    expect(parser.packages()).toBe(1)
    expect(seen).toEqual([estimateDownloadProgress(1)])
  })

  it('连续多行被随意切开也一个不落', () => {
    const parser = createPipProgressParser()
    const stream =
      'Collecting aaa==1.0\nCollecting bbb==2.0\nCollecting ccc==3.0\n'

    // 7 字节一刀，切点必然落在行中间
    for (let i = 0; i < stream.length; i += 7) {
      parser.push(stream.slice(i, i + 7))
    }

    expect(parser.packages()).toBe(3)
  })

  it('CRLF 行尾也按一行处理', () => {
    const parser = createPipProgressParser()

    parser.push('Collecting aaa==1.0\r\n')

    expect(parser.packages()).toBe(1)
  })

  it('最后一行没有换行符时由 flush 收尾', () => {
    const parser = createPipProgressParser()

    parser.push('Collecting aaa==1.0\nCollecting bbb==2.0')
    expect(parser.packages()).toBe(1)

    parser.flush()
    expect(parser.packages()).toBe(2)
  })

  it('安装与完成节点照旧推进', () => {
    const seen: number[] = []
    const parser = createPipProgressParser(p => seen.push(p))

    parser.push('Collecting aaa==1.0\nCollecting bbb==2.0\n')
    parser.push('Installing collected packages: aaa, bbb\n')
    parser.push('Successfully installed aaa-1.0 bbb-2.0\n')

    expect(parser.packages()).toBe(2)
    expect(seen[seen.length - 1]).toBe(95)
  })
})
