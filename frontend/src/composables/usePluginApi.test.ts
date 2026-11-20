import { beforeEach, afterEach, describe, expect, it, vi } from 'vite-plus/test'
import { effectScope } from 'vue'

const boundary = vi.hoisted(() => ({
  start: vi.fn(),
  get: vi.fn(),
  installation: vi.fn(),
  prepare: vi.fn(),
  resume: vi.fn(),
  restart: vi.fn(),
  reconnect: vi.fn(),
  manages: vi.fn(),
  finish: vi.fn(),
}))
vi.mock('@/api', async importOriginal => ({
  ...(await importOriginal<typeof import('@/api')>()),
  Service: {
    updatePluginConfigApiPluginConfigUpdatePost: vi.fn(),
    refreshPluginCatalogApiPluginCatalogRefreshPost: vi.fn(),
    writeConfigTriggerApiConfigTriggersWritePost: boundary.start,
    getConfigTriggerResultApiConfigTriggersResultPost: boundary.get,
    getPluginInstallationApiPluginInstallationGetPost: boundary.installation,
    preparePluginInstallationRestartApiPluginInstallationRestartPost: boundary.prepare,
    resumeAfterPluginInstallationRestartApiPluginInstallationResumePost: boundary.resume,
  },
}))
vi.mock('@/i18n', () => ({
  translate: (key: string) => key,
  i18n: { global: { locale: { value: 'en-US' } } },
}))
vi.mock('@/utils/analytics', () => ({
  beginAnalyticsOperation: () => ({ finish: boundary.finish }),
}))
vi.mock('@/utils/environment', () => ({ managesBackendProcess: boundary.manages }))
vi.mock('@/composables/useAppLifecycle', () => ({
  beginIntentionalBackendRestart: vi.fn(),
  endIntentionalBackendRestart: vi.fn(),
}))
vi.mock('@/services/websocket/connection', () => ({ reconnectNow: boundary.reconnect }))

import { usePluginApi } from './usePluginApi'

const request = { configUid: 'market-entry', group: 'info', field: 'install', value: true }
const progress = (state: string) => ({
  code: 200,
  data: { installationId: 'installation', metaId: request.configUid, state },
})

describe('插件安装的热加载与重启交接', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.clearAllMocks()
    boundary.start.mockResolvedValue({
      code: 200,
      data: 'task',
    })
    boundary.get.mockResolvedValue({ code: 200, data: { state: 'succeeded' } })
    boundary.installation.mockResolvedValue(progress('succeeded'))
    boundary.prepare.mockResolvedValue({ code: 200, ready: true })
    boundary.resume.mockResolvedValue({ code: 200 })
    boundary.restart.mockResolvedValue({ success: true })
    boundary.reconnect.mockResolvedValue(true)
    boundary.manages.mockReturnValue(true)
    vi.stubGlobal('window', {
      setTimeout,
      electronAPI: { backendRestart: boundary.restart, getLogger: () => ({ warn: vi.fn() }) },
    })
  })
  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it('无需换版已加载依赖时，安装完成直接返回成功', async () => {
    const scope = effectScope()
    try {
      const api = scope.run(usePluginApi)!
      await api.runCommand('install', request)
      expect(boundary.restart).not.toHaveBeenCalled()
      expect(boundary.finish).toHaveBeenCalledWith({ action: 'install', outcome: 'success' })
    } finally {
      scope.stop()
    }
  })

  it('当前业务结束前不重启，加载确认后才报告安装成功', async () => {
    boundary.installation
      .mockResolvedValueOnce({ code: 200, data: null })
      .mockResolvedValueOnce(progress('waiting_restart'))
      .mockResolvedValue(progress('succeeded'))
    boundary.prepare
      .mockResolvedValueOnce({ code: 200, ready: false })
      .mockResolvedValue({ code: 200, ready: true })
    const scope = effectScope()
    try {
      const api = scope.run(usePluginApi)!
      const execution = api.runCommand('install', request)
      await vi.advanceTimersByTimeAsync(0)
      expect(boundary.restart).not.toHaveBeenCalled()
      expect(boundary.finish).not.toHaveBeenCalled()
      await vi.advanceTimersByTimeAsync(500)
      await execution
      expect(boundary.restart).toHaveBeenCalledTimes(1)
      expect(boundary.start).toHaveBeenCalledTimes(1)
      expect(boundary.reconnect).toHaveBeenCalled()
      expect(boundary.resume).toHaveBeenCalledWith({ installationId: 'installation' })
      expect(boundary.finish).toHaveBeenCalledWith({ action: 'install', outcome: 'success' })
    } finally {
      scope.stop()
    }
  })

  it.each(['failed', 'disconnected'])(
    '新环境启动失败后恢复原环境，状态为 %s 时安装仍报告失败',
    async state => {
      boundary.installation
        .mockResolvedValueOnce({ code: 200, data: null })
        .mockResolvedValueOnce(progress('waiting_restart'))
        .mockResolvedValue(progress('failed'))
      if (state === 'disconnected')
        boundary.installation.mockRejectedValue(new Error('disconnected'))
      boundary.restart
        .mockResolvedValueOnce({ success: false })
        .mockResolvedValue({ success: true })
      const scope = effectScope()
      try {
        const api = scope.run(usePluginApi)!
        await expect(api.runCommand('install', request)).rejects.toThrow()
        expect(boundary.restart).toHaveBeenCalledTimes(2)
        expect(boundary.resume).toHaveBeenCalled()
        expect(boundary.finish).toHaveBeenCalledWith({ action: 'install', outcome: 'failure' })
      } finally {
        scope.stop()
      }
    }
  )

  it('外部后端保留待重启结果，不误报安装成功', async () => {
    boundary.installation.mockResolvedValue(progress('waiting_restart'))
    boundary.manages.mockReturnValue(false)
    const scope = effectScope()
    try {
      const api = scope.run(usePluginApi)!
      await expect(api.runCommand('install', request)).rejects.toThrow()
      expect(boundary.restart).not.toHaveBeenCalled()
      expect(boundary.finish).toHaveBeenCalledWith({ action: 'install', outcome: 'unknown' })
    } finally {
      scope.stop()
    }
  })

  it('页面恢复继续原候选，避免重复提交安装', async () => {
    boundary.installation
      .mockResolvedValueOnce(progress('waiting_restart'))
      .mockResolvedValue(progress('succeeded'))
    const scope = effectScope()
    try {
      await scope.run(usePluginApi)!.runCommand('install', request)
      expect(boundary.start).not.toHaveBeenCalled()
      expect(boundary.restart).toHaveBeenCalledTimes(1)
    } finally {
      scope.stop()
    }
  })

  it('重启资格响应中断后仍尝试归还，不停止后端', async () => {
    boundary.installation.mockResolvedValue(progress('waiting_restart'))
    boundary.prepare.mockRejectedValue(new Error('disconnected'))
    const scope = effectScope()
    try {
      await expect(scope.run(usePluginApi)!.runCommand('install', request)).rejects.toThrow(
        'disconnected'
      )
      expect(boundary.resume).toHaveBeenCalledWith({ installationId: 'installation' })
      expect(boundary.restart).not.toHaveBeenCalled()
      expect(boundary.finish).toHaveBeenCalledWith({ action: 'install', outcome: 'unknown' })
    } finally {
      scope.stop()
    }
  })
})

import { BackgroundTaskState, Service } from '@/api'
const finish = boundary.finish
describe('plugin commands and settings', () => {
  const scopes: ReturnType<typeof effectScope>[] = []
  const body = { configUid: 'config', group: 'info', field: 'enable', value: true }
  const createApi = () => {
    // 在真实 Vue 作用域内创建业务封装，确保轮询释放使用正式生命周期。
    const scope = effectScope()
    scopes.push(scope)
    return scope.run(usePluginApi)!
  }

  beforeEach(() => {
    // 仅隔离生成客户端和遥测边界，保留业务封装、错误转换和结果等待。
    vi.clearAllMocks()
    vi.useFakeTimers()
    vi.stubGlobal('window', { setTimeout })
    finish.mockClear()
  })
  afterEach(() => {
    // 释放作用域、计时器和边界替身，避免跨场景遗留轮询。
    for (const scope of scopes.splice(0)) scope.stop()
    vi.useRealTimers()
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it.each([
    [BackgroundTaskState.SUCCEEDED, 'success'],
    [BackgroundTaskState.FAILED, 'failure'],
    [BackgroundTaskState.TIMED_OUT, 'failure'],
    [BackgroundTaskState.CANCELLED, 'cancelled'],
  ] as const)(
    'records %s only after the command reaches its terminal state',
    async (state, outcome) => {
      // 后台受理与完成分开；不同终态必须保留独立结果且只观测一次。
      const start = vi
        .spyOn(Service, 'writeConfigTriggerApiConfigTriggersWritePost')
        .mockResolvedValue({ code: 200, data: 'task' })
      const query = vi
        .spyOn(Service, 'getConfigTriggerResultApiConfigTriggersResultPost')
        .mockResolvedValue({ code: 200, data: { state } })
      const settled = createApi()
        .runCommand('enable', body)
        .then(
          () => 'success',
          () => 'error'
        )
      await Promise.resolve()
      expect(finish).not.toHaveBeenCalled()
      await vi.runAllTimersAsync()
      expect(await settled).toBe(state === 'succeeded' ? 'success' : 'error')
      expect(start).toHaveBeenCalledWith(body)
      expect(query).toHaveBeenCalledWith({ taskId: 'task' })
      expect(finish).toHaveBeenCalledExactlyOnceWith({ action: 'enable', outcome })
    }
  )

  it('reports unknown after repeated query failures without resubmitting the command', async () => {
    // 轮询网络故障不能变成操作成功，也不能重复提交产生副作用的命令。
    const start = vi
      .spyOn(Service, 'writeConfigTriggerApiConfigTriggersWritePost')
      .mockResolvedValue({ code: 200, data: 'task' })
    const query = vi
      .spyOn(Service, 'getConfigTriggerResultApiConfigTriggersResultPost')
      .mockRejectedValue(new Error('disconnected'))
    const settled = createApi()
      .runCommand('enable', body)
      .catch(error => error)
    await vi.runAllTimersAsync()
    expect(await settled).toMatchObject({ message: 'core.plugins.outcomeUnknown' })
    expect(start).toHaveBeenCalledTimes(1)
    expect(query).toHaveBeenCalledTimes(3)
    expect(finish).toHaveBeenCalledExactlyOnceWith({ action: 'enable', outcome: 'unknown' })
  })

  it('saves settings without expecting operation IDs or polling command state', async () => {
    // 普通配置保存只消费保存结果，不再依赖 update 返回操作列表。
    const save = vi
      .spyOn(Service, 'updatePluginConfigApiPluginConfigUpdatePost')
      .mockResolvedValue({ code: 200 })
    const query = vi.spyOn(Service, 'getConfigTriggerResultApiConfigTriggersResultPost')
    const patch = { recordId: 'record', data: { info: { value: true } } }
    expect(await createApi().updateConfig(patch)).toEqual({ code: 200 })
    expect(save).toHaveBeenCalledWith(patch, 'en-US')
    expect(query).not.toHaveBeenCalled()
    expect(finish).toHaveBeenCalledExactlyOnceWith({ action: 'config', outcome: 'success' })
  })

  it.each(['config', 'refresh'] as const)(
    'records explicit %s rejection as failure',
    async action => {
      // 后端已明确回复失败时不再记录 unknown，只有传输中断才保留未知结果。
      vi.spyOn(Service, 'updatePluginConfigApiPluginConfigUpdatePost').mockResolvedValue({
        code: 400,
        message: 'rejected',
      })
      vi.spyOn(Service, 'refreshPluginCatalogApiPluginCatalogRefreshPost').mockResolvedValue({
        code: 500,
        message: 'rejected',
      })
      const api = createApi()
      await expect(
        action === 'config'
          ? api.updateConfig({ recordId: 'record', data: {} })
          : api.refreshCatalog()
      ).rejects.toThrow('rejected')
      expect(finish).toHaveBeenCalledExactlyOnceWith({ action, outcome: 'failure' })
    }
  )

  it('shares catalog refreshes and observes only newly started manual batches', async () => {
    const refresh = vi
      .spyOn(Service, 'refreshPluginCatalogApiPluginCatalogRefreshPost')
      .mockResolvedValue({ code: 200 })

    await Promise.all([createApi().refreshCatalog('automatic'), createApi().refreshCatalog()])
    expect(refresh).toHaveBeenCalledTimes(1)
    expect(finish).not.toHaveBeenCalled()

    await Promise.all([createApi().refreshCatalog(), createApi().refreshCatalog()])
    expect(refresh).toHaveBeenCalledTimes(2)
    expect(finish).toHaveBeenCalledExactlyOnceWith({ action: 'refresh', outcome: 'success' })
  })
})
