import { describe, expect, it } from 'vite-plus/test'
import { allowedFields, SampleSummary } from './summary'

describe('启动硬件摘要', () => {
  it('只汇总本阶段内完整的采样区间，区分真实低负载和未知', () => {
    const stage = new SampleSummary(500)
    stage.add({
      previous: 0,
      at: 1000,
      data: { cpu: 100, install_free: 0.5, cache_location: 'different-disk' },
    })
    expect(stage.fields()).not.toHaveProperty('cpu_avg')
    stage.add({ previous: 1000, at: 2000, data: { cpu: 10, install_free: 64 } })
    stage.add({ previous: 2000, at: 4000, data: { cpu: 100, install_free: 32 } })
    expect(stage.fields()).toMatchObject({
      cpu_avg: '50-75%',
      cpu_peak: '90-100%',
      cpu_high: '1-5s',
      install_free: '<1GiB',
      cache_location: 'different-disk',
    })
  })
  it('发送边界拒绝目录、设备名称和未登记值', () => {
    expect(
      allowedFields({
        install_free: '<1GiB',
        install_fs: 'private-volume',
        cpu_series: 'private-cpu',
        serial: 'private',
      })
    ).toEqual({ install_free: '<1GiB' })
  })
})
