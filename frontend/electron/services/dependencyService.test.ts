import { describe, expect, it } from 'vitest'
import { estimateDownloadProgress } from './dependencyService'

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
