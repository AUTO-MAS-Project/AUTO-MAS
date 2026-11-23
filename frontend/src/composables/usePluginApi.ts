import { onScopeDispose } from 'vue'
import {
  Service,
  PluginInstallation,
  type TriggerTaskResult,
  type TriggerWriteIn,
  type PluginConfigUpdateIn,
  type OutBase,
} from '@/api'
import { i18n, translate as t } from '@/i18n'
import { ApiResponseError, requestApi } from '@/utils/apiResult'
import { beginAnalyticsOperation } from '@/utils/analytics'
import { managesBackendProcess } from '@/utils/environment'
import {
  beginIntentionalBackendRestart,
  endIntentionalBackendRestart,
} from '@/composables/useAppLifecycle'
import { reconnectNow } from '@/services/websocket/connection'

type Action = 'enable' | 'disable' | 'reload' | 'uninstall' | 'install' | 'refresh' | 'config'
export type InstallationStage = 'waiting' | 'restarting' | 'recovering'

let catalogRefreshRequest: Promise<OutBase> | undefined

class OperationResultError extends Error {
  constructor(
    readonly outcome: 'failure' | 'cancelled' | 'unknown',
    reason?: string
  ) {
    // 用明确的命令结果传递遥测分类，避免根据翻译后的错误文本判断状态。
    super(
      reason ??
        t(
          outcome === 'cancelled'
            ? 'core.plugins.actionCancelled'
            : outcome === 'failure'
              ? 'core.plugins.actionFailed'
              : 'core.plugins.outcomeUnknown'
        )
    )
  }
}

export function usePluginApi() {
  // 统一插件配置读取、保存和独立命令提交；每个用户操作只记录一次真实完成结果。
  let disposed = false
  onScopeDispose(() => {
    // 页面释放后停止轮询，后台插件命令仍由后端持有。
    disposed = true
  })
  const locale = () => /* 读取插件请求使用的当前界面语言。 */ i18n.global.locale.value
  const pause = () =>
    /* 按固定间隔查询后台命令，避免连续请求。 */ new Promise<void>(resolve => {
      window.setTimeout(resolve, 500)
    })
  const perform = async <T extends OutBase>(action: Action, invoke: () => PromiseLike<T>) => {
    // 围绕保存或完整命令流程记录结果；受理成功不提前计为命令完成。
    const observation = beginAnalyticsOperation('plugin_action_finished')
    let outcome: 'success' | 'failure' | 'cancelled' | 'unknown' = 'unknown'
    try {
      const result = await invoke()
      outcome = 'success'
      return result
    } catch (error) {
      if (error instanceof OperationResultError) outcome = error.outcome
      else if (error instanceof ApiResponseError) outcome = 'failure'
      throw error
    } finally {
      observation.finish({ action, outcome })
    }
  }
  const refreshCatalog = (trigger: 'manual' | 'automatic' = 'manual') => {
    // 跨页面共用正在进行的刷新，只观察实际发起的手动批次。
    if (catalogRefreshRequest) return catalogRefreshRequest
    const request = () =>
      requestApi(
        () => Service.refreshPluginCatalogApiPluginCatalogRefreshPost(locale(), {}),
        t('core.plugins.actionFailed')
      )
    catalogRefreshRequest = (
      trigger === 'automatic' ? request() : perform('refresh', request)
    ).finally(() => {
      catalogRefreshRequest = undefined
    })
    return catalogRefreshRequest
  }
  const finishInstallation = async (
    metaId: string,
    onProgress?: (stage: InstallationStage) => void,
    prepared?: PluginInstallation
  ) => {
    // 下载与候选准备结束后，继续确认跨进程安装；准备受理不计为安装成功。
    const get = () =>
      requestApi(
        () => Service.getPluginInstallationApiPluginInstallationGetPost({ metaId }),
        t('core.plugins.actionFailed')
      )
    const installation = prepared ?? (await get()).data
    if (!installation || installation.state === PluginInstallation.state.SUCCEEDED) return
    if (installation.state === PluginInstallation.state.FAILED)
      throw new OperationResultError('failure')
    if (!managesBackendProcess() || !window.electronAPI?.backendRestart) {
      throw new OperationResultError('unknown', installation.message ?? undefined)
    }
    const body = { installationId: installation.installationId }
    let reserved = false
    let requested = false
    let restarting = false
    try {
      if (disposed) throw new OperationResultError('unknown')
      onProgress?.('waiting')
      while (!reserved) {
        if (disposed) throw new OperationResultError('unknown')
        requested = true
        const response = await requestApi(
          () => Service.preparePluginInstallationRestartApiPluginInstallationRestartPost(body),
          t('core.plugins.actionFailed')
        )
        reserved = response.ready === true
        if (!reserved) await pause()
      }
      if (disposed) throw new OperationResultError('unknown')
      onProgress?.('restarting')
      beginIntentionalBackendRestart('插件依赖更新')
      restarting = true
      const result = await window.electronAPI.backendRestart('update')
      if (!result.success) {
        // 失败进程可能已退出；读不到 HTTP 状态也须执行这次交接唯一允许的恢复重启。
        const progress = await get().catch(() => null)
        if (
          progress === null ||
          progress.data?.state === PluginInstallation.state.FAILED ||
          progress.data?.state === PluginInstallation.state.APPLYING
        ) {
          // 启动未确认成功时，新进程按既有交接记录恢复旧环境；最多恢复一次。
          if (!disposed) onProgress?.('recovering')
          const restored = await window.electronAPI.backendRestart('recovery')
          if (restored.success) await reconnectNow('插件环境恢复')
        }
        throw new OperationResultError('failure')
      }
      await reconnectNow('插件环境更新完成')
      const progress = (await get()).data
      if (progress?.state === PluginInstallation.state.FAILED)
        throw new OperationResultError('failure')
      if (progress?.state !== PluginInstallation.state.SUCCEEDED)
        throw new OperationResultError('unknown')
    } finally {
      if (restarting) endIntentionalBackendRestart('插件安装重启流程结束')
      if (requested) {
        try {
          await Service.resumeAfterPluginInstallationRestartApiPluginInstallationResumePost(body)
        } catch {
          window.electronAPI.getLogger('插件安装').warn('重启资格未能归还，请检查后端连接')
        }
      }
    }
  }
  const runCommand = (
    action: Action,
    body: TriggerWriteIn,
    onProgress?: (stage: InstallationStage) => void
  ) =>
    perform(action, async () => {
      if (action === 'install') {
        // 页面重建或重启交接响应丢失后，可继续原候选，不重复提交安装命令。
        const pending = await requestApi(
          () =>
            Service.getPluginInstallationApiPluginInstallationGetPost({ metaId: body.configUid }),
          t('core.plugins.actionFailed')
        )
        if (pending.data?.state === PluginInstallation.state.WAITING_RESTART) {
          await finishInstallation(body.configUid, onProgress, pending.data)
          return { code: 200, status: 'success' }
        }
      }
      // 命令入口直接返回身份，配置 update 不再承担命令跟踪契约。
      const accepted = await requestApi(
        () => Service.writeConfigTriggerApiConfigTriggersWritePost(body),
        t('core.plugins.actionFailed')
      )
      const taskId = accepted.data
      if (!taskId) throw new OperationResultError('unknown')
      let misses = 0
      while (true) {
        if (disposed) throw new OperationResultError('unknown')
        let state: TriggerTaskResult['state']
        try {
          const response = await requestApi(
            () => Service.getConfigTriggerResultApiConfigTriggersResultPost({ taskId }),
            t('core.plugins.outcomeUnknown')
          )
          if (!response.data) throw new OperationResultError('unknown')
          state = response.data.state
          misses = 0
        } catch {
          if (++misses >= 3) throw new OperationResultError('unknown')
          await pause()
          continue
        }
        if (state === 'succeeded') break
        if (state === 'failed' || state === 'timed_out') throw new OperationResultError('failure')
        if (state === 'cancelled') throw new OperationResultError('cancelled')
        await pause()
      }
      if (action === 'install') await finishInstallation(body.configUid, onProgress)
      return accepted
    })
  return {
    runCommand,
    getRegistry: (recordId: string | null = null) =>
      /* 读取插件注册配置及其 UI 提示，保留后端决定的显隐和禁用状态。 */ requestApi(
        () => Service.getPluginRegistryApiPluginRegistryGetPost({ recordId }, locale()),
        t('core.plugins.loadFailed')
      ),
    getCatalog: (language = locale()) =>
      /* 读取市场条目与安装字段的 UI 属性。 */ requestApi(
        () => Service.getPluginCatalogApiPluginCatalogGetPost({}, language),
        t('core.plugins.marketLoadFailed')
      ),
    refreshCatalog,
    getConfig: (recordId: string) =>
      /* 读取插件自有配置及其独立配置 UID。 */ requestApi(
        () => Service.getPluginConfigApiPluginConfigGetPost({ recordId }, locale()),
        t('core.plugins.settingsLoadFailed')
      ),
    updateConfig: (body: PluginConfigUpdateIn) =>
      perform('config', () =>
        /* 保存普通配置字段；按钮动作通过 runCommand 独立提交。 */ requestApi(
          () => Service.updatePluginConfigApiPluginConfigUpdatePost(body, locale()),
          t('core.plugins.actionFailed')
        )
      ),
  }
}
