import { describe, expect, it } from 'vite-plus/test'
import { portableGraphics } from './portable'
import { SampleSummary } from './summary'

describe('只有核显或无法查询显卡的设备', () => {
  it('保留核显共享内存和驱动实际给出的负载', () => {
    const summary = new SampleSummary(0)
    summary.add({
      previous: 0,
      at: 1000,
      data: {
        cpu: 45,
        gpu_count: 1,
        graphics_layout: 'integrated-only',
        gpu0_kind: 'integrated',
        gpu0_series: 'Intel Iris Xe',
        gpu0_shared: 1.4,
        gpu0_busy: 20,
      },
    })
    expect(summary.fields()).toMatchObject({
      graphics_layout: 'integrated-only',
      gpu0_shared: '1-4GiB',
      gpu0_busy_peak: '20-50%',
      gpu0_kind: 'integrated',
    })
    expect(summary.fields()).not.toHaveProperty('gpu0_dedicated')
  })
  it('区分软件渲染、空列表和枚举失败', () => {
    expect(portableGraphics({ gpuDevice: [{ vendorId: 0x1414 }] })).toEqual({
      gpu_count: 0,
      graphics_layout: 'software-only',
    })
    expect(portableGraphics({ gpuDevice: [] })).toEqual({
      gpu_count: 0,
      graphics_layout: 'no-adapter',
    })
    expect(portableGraphics(undefined)).toEqual({})
  })
})
