import { beforeEach, describe, expect, it, vi } from 'vitest'

const service = vi.hoisted(() => ({
  getMaafwEmbeddedStatusApiScriptsMaafwEmbeddedStatusPost: vi.fn(),
  enableMaafwEmbeddedApiScriptsMaafwEmbeddedEnablePost: vi.fn(),
  reimportMaafwEmbeddedApiScriptsMaafwEmbeddedReimportPost: vi.fn(),
  disableMaafwEmbeddedApiScriptsMaafwEmbeddedDisablePost: vi.fn(),
}))

vi.mock('@/api', () => ({ MaaFwService: service }))

import {
  EMPTY_EMBEDDED_STATUS,
  formatEmbeddedBytes,
  useMaaFWEmbeddedApi,
} from './useMaaFWEmbeddedApi'

/**
 * 四条内嵌路由的业务失败都是 HTTP 200 + `code !== 200`，生成的客户端不会抛错；
 * 这里钉住「code 不对就抛后端文案」与「成功时状态补齐默认值」，界面侧才能只看
 * 一个 try/catch。
 */
describe('useMaaFWEmbeddedApi', () => {
  beforeEach(() => {
    Object.values(service).forEach(fn => fn.mockReset())
  })

  it('成功时把缺省字段补齐，并把后端文案带回来', async () => {
    service.enableMaafwEmbeddedApiScriptsMaafwEmbeddedEnablePost.mockResolvedValue({
      code: 200,
      status: 'success',
      message: '已内嵌，省下 62.10%；原目录未改动',
      data: { enabled: true, copyHealthy: true, report: { savedPercent: 62.1 } },
    })

    const { enableEmbedded } = useMaaFWEmbeddedApi()
    const result = await enableEmbedded('sid')

    expect(service.enableMaafwEmbeddedApiScriptsMaafwEmbeddedEnablePost).toHaveBeenCalledWith({
      scriptId: 'sid',
    })
    expect(result.message).toContain('省下')
    expect(result.status).toEqual({
      ...EMPTY_EMBEDDED_STATUS,
      enabled: true,
      copyHealthy: true,
      report: { savedPercent: 62.1 },
    })
  })

  it('code 不是 200 时抛出后端给的文案', async () => {
    service.reimportMaafwEmbeddedApiScriptsMaafwEmbeddedReimportPost.mockResolvedValue({
      code: 400,
      status: 'error',
      message: '重新导入失败: 来源目录不存在',
      data: null,
    })

    const { reimportEmbedded } = useMaaFWEmbeddedApi()
    await expect(reimportEmbedded('sid', 'D:\\nope')).rejects.toThrow('来源目录不存在')
    expect(service.reimportMaafwEmbeddedApiScriptsMaafwEmbeddedReimportPost).toHaveBeenCalledWith({
      scriptId: 'sid',
      sourcePath: 'D:\\nope',
    })
  })

  it('没有 data 也能给出完整的空状态', async () => {
    service.disableMaafwEmbeddedApiScriptsMaafwEmbeddedDisablePost.mockResolvedValue({
      code: 200,
      status: 'success',
      message: '',
      data: null,
    })

    const { disableEmbedded } = useMaaFWEmbeddedApi()
    const result = await disableEmbedded('sid')
    expect(result.status).toEqual(EMPTY_EMBEDDED_STATUS)
  })
})

describe('formatEmbeddedBytes', () => {
  it('小于 1 GB 用 MB，否则用 GB；非法输入当 0', () => {
    expect(formatEmbeddedBytes(0)).toBe('0 MB')
    expect(formatEmbeddedBytes(undefined)).toBe('0 MB')
    expect(formatEmbeddedBytes(75.5 * 1024 * 1024)).toBe('75.5 MB')
    expect(formatEmbeddedBytes(1.5 * 1024 ** 3)).toBe('1.50 GB')
  })
})
