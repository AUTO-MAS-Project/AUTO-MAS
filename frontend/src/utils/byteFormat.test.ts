import { describe, expect, it } from 'vitest'
import { formatBytes, formatSpeed } from './byteFormat'

describe('formatBytes', () => {
  it('二进制换算，小数最多两位并去掉尾零', () => {
    expect(formatBytes(0)).toBe('0 B')
    expect(formatBytes(512)).toBe('512 B')
    expect(formatBytes(1536)).toBe('1.5 KB')
    expect(formatBytes(10485760)).toBe('10 MB')
    expect(formatBytes(52428800)).toBe('50 MB')
    expect(formatBytes(1073741824)).toBe('1 GB')
    expect(formatBytes(33554432 + 1234567)).toBe('33.18 MB')
  })

  it('非法输入按 0 处理，超过 GB 的量不会越界到没有单位', () => {
    expect(formatBytes(-1)).toBe('0 B')
    expect(formatBytes(Number.NaN)).toBe('0 B')
    expect(formatBytes(2 ** 41)).toBe('2048 GB')
  })
})

describe('formatSpeed', () => {
  it('与更新下载弹窗同一口径：小数最多一位', () => {
    expect(formatSpeed(0)).toBe('0 B/s')
    expect(formatSpeed(524288)).toBe('512 KB/s')
    expect(formatSpeed(1153434)).toBe('1.1 MB/s')
    expect(formatSpeed(3355443)).toBe('3.2 MB/s')
    expect(formatSpeed(2097152)).toBe('2 MB/s')
  })

  it('非法输入按 0 处理', () => {
    expect(formatSpeed(-5)).toBe('0 B/s')
    expect(formatSpeed(Number.POSITIVE_INFINITY)).toBe('0 B/s')
  })
})
