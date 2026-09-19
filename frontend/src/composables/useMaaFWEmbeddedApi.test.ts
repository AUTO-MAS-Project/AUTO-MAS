import { beforeEach, describe, expect, it, vi } from 'vitest'

const service = vi.hoisted(() => ({
  getMaafwEmbeddedStatusApiScriptsMaafwEmbeddedStatusPost: vi.fn(),
  reimportMaafwEmbeddedApiScriptsMaafwEmbeddedReimportPost: vi.fn(),
  listMaafwEmbeddedSourcesApiScriptsMaafwEmbeddedSourcesPost: vi.fn(),
  cloneMaafwEmbeddedApiScriptsMaafwEmbeddedClonePost: vi.fn(),
}))

vi.mock('@/api', () => ({ MaaFwService: service }))

import {
  EMPTY_EMBEDDED_STATUS,
  formatEmbeddedBytes,
  useMaaFWEmbeddedApi,
} from './useMaaFWEmbeddedApi'

/**
 * 两条内嵌路由的业务失败都是 HTTP 200 + `code !== 200`，生成的客户端不会抛错；
 * 这里钉住「code 不对就抛后端文案」与「成功时状态补齐默认值」，界面侧才能只看
 * 一个 try/catch。
 */
describe('useMaaFWEmbeddedApi', () => {
  beforeEach(() => {
    Object.values(service).forEach(fn => fn.mockReset())
  })

  it('成功时把缺省字段补齐，并把后端文案带回来', async () => {
    service.reimportMaafwEmbeddedApiScriptsMaafwEmbeddedReimportPost.mockResolvedValue({
      code: 200,
      status: 'success',
      message: '已导入，副本只有来源的 38%；来源目录未改动',
      data: { copyHealthy: true, report: { savedPercent: 62.1 } },
    })

    const { reimportEmbedded } = useMaaFWEmbeddedApi()
    const result = await reimportEmbedded('sid', 'D:/src')

    expect(service.reimportMaafwEmbeddedApiScriptsMaafwEmbeddedReimportPost).toHaveBeenCalledWith({
      scriptId: 'sid',
      sourcePath: 'D:/src',
    })
    expect(result.message).toContain('已导入')
    expect(result.status).toEqual({
      ...EMPTY_EMBEDDED_STATUS,
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

  it('克隆走同一套 unwrap：成功回状态与文案，失败抛后端文案', async () => {
    service.cloneMaafwEmbeddedApiScriptsMaafwEmbeddedClonePost.mockResolvedValueOnce({
      code: 200,
      status: 'success',
      message: '已复用「床1」的项目',
      data: { copyHealthy: true, sourcePath: 'D:/m9a' },
    })
    const { cloneEmbedded } = useMaaFWEmbeddedApi()
    const ok = await cloneEmbedded('new', 'old')
    expect(service.cloneMaafwEmbeddedApiScriptsMaafwEmbeddedClonePost).toHaveBeenCalledWith({
      scriptId: 'new',
      sourceScriptId: 'old',
    })
    expect(ok.status.sourcePath).toBe('D:/m9a')
    expect(ok.message).toContain('已复用')

    service.cloneMaafwEmbeddedApiScriptsMaafwEmbeddedClonePost.mockResolvedValueOnce({
      code: 400,
      status: 'error',
      message: '源脚本正在运行，运行结束后再复用它的项目',
      data: null,
    })
    await expect(cloneEmbedded('new', 'old')).rejects.toThrow('源脚本正在运行')
  })

  it('候选列表：code 对就给 data，没 data 给空数组，code 不对抛文案', async () => {
    const { listEmbeddedSources } = useMaaFWEmbeddedApi()
    service.listMaafwEmbeddedSourcesApiScriptsMaafwEmbeddedSourcesPost.mockResolvedValueOnce({
      code: 200,
      status: 'success',
      message: '',
      data: [{ scriptId: 'a', name: '床1', type: 'M9A', projectName: 'M9A', version: 'v4.9.0' }],
    })
    expect(await listEmbeddedSources('new')).toHaveLength(1)
    expect(
      service.listMaafwEmbeddedSourcesApiScriptsMaafwEmbeddedSourcesPost
    ).toHaveBeenLastCalledWith({ scriptId: 'new' })
    service.listMaafwEmbeddedSourcesApiScriptsMaafwEmbeddedSourcesPost.mockResolvedValueOnce({
      code: 200,
      status: 'success',
      message: '',
      data: [],
    })
    // 新建对话框里还没有脚本：不传就不排除任何人
    expect(await listEmbeddedSources()).toEqual([])
    expect(
      service.listMaafwEmbeddedSourcesApiScriptsMaafwEmbeddedSourcesPost
    ).toHaveBeenLastCalledWith({})
    service.listMaafwEmbeddedSourcesApiScriptsMaafwEmbeddedSourcesPost.mockResolvedValueOnce({
      code: 200,
      status: 'success',
      message: '',
      data: undefined,
    })
    expect(await listEmbeddedSources('new')).toEqual([])
    service.listMaafwEmbeddedSourcesApiScriptsMaafwEmbeddedSourcesPost.mockResolvedValueOnce({
      code: 400,
      status: 'error',
      message: 'MFW 脚本无效',
      data: [],
    })
    await expect(listEmbeddedSources('new')).rejects.toThrow('MFW 脚本无效')
  })

  it('没有 data 也能给出完整的空状态', async () => {
    service.getMaafwEmbeddedStatusApiScriptsMaafwEmbeddedStatusPost.mockResolvedValue({
      code: 200,
      status: 'success',
      message: '',
      data: null,
    })

    const { getEmbeddedStatus } = useMaaFWEmbeddedApi()
    const result = await getEmbeddedStatus('sid')
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
