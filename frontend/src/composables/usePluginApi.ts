import { onScopeDispose } from 'vue'
import { Service, type OperationStartIn, type PluginConfigUpdateIn, type OutBase } from '@/api'
import { i18n, translate as t } from '@/i18n'
import { requestApi } from '@/utils/apiResult'
import { beginAnalyticsOperation } from '@/utils/analytics'

type Action = 'enable' | 'disable' | 'reload' | 'uninstall' | 'install' | 'refresh' | 'config'

class OperationResultError extends Error {
  constructor(readonly outcome: 'failure' | 'cancelled' | 'unknown') {
    // 用明确的命令结果传递遥测分类，避免根据翻译后的错误文本判断状态。
    super(
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
      throw error
    } finally {
      observation.finish({ action, outcome })
    }
  }
  const runCommand = (action: Action, body: OperationStartIn) =>
    perform(action, async () => {
      // 命令入口直接返回身份，配置 update 不再承担命令跟踪契约。
      const accepted = await requestApi(
        () => Service.startOperationApiOperationsStartPost(body),
        t('core.plugins.actionFailed')
      )
      const operationId = accepted.data?.operationId
      if (!operationId) throw new OperationResultError('unknown')
      let operation = accepted.data
      let misses = 0
      while (operation?.state !== 'succeeded') {
        if (operation?.state === 'failed' || operation?.state === 'cancelled') {
          throw new OperationResultError(operation.state === 'cancelled' ? 'cancelled' : 'failure')
        }
        if (disposed) throw new OperationResultError('unknown')
        await pause()
        try {
          const response = await requestApi(
            () => Service.getOperationApiOperationsGetPost({ operationId }),
            t('core.plugins.outcomeUnknown')
          )
          if (!response.data) throw new OperationResultError('unknown')
          operation = response.data
          misses = 0
        } catch {
          if (++misses >= 3) throw new OperationResultError('unknown')
        }
      }
      return accepted
    })
  return {
    runCommand,
    getRegistry: (recordId: string | null = null) =>
      /* 读取插件注册配置及其 UI 提示，保留后端决定的显隐和禁用状态。 */ requestApi(
        () => Service.getPluginRegistryApiPluginRegistryGetPost({ recordId }, locale()),
        t('core.plugins.loadFailed')
      ),
    getCatalog: () =>
      /* 读取市场条目与安装字段的 UI 属性。 */ requestApi(
        () => Service.getPluginCatalogApiPluginCatalogGetPost({}, locale()),
        t('core.plugins.marketLoadFailed')
      ),
    refreshCatalog: () =>
      perform('refresh', () =>
        /* 刷新完成后记录结果。 */ requestApi(
          () => Service.refreshPluginCatalogApiPluginCatalogRefreshPost(locale(), {}),
          t('core.plugins.actionFailed')
        )
      ),
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
