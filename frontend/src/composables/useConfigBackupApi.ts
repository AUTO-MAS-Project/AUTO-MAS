import { toValue, type MaybeRefOrGetter } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import { ApiError, Service } from '@/api'
import { beginAnalyticsOperation, getAnalyticsScriptType } from '@/utils/analytics'

interface ConfigBackupApiOptions {
  scriptId: MaybeRefOrGetter<string>
  userId: MaybeRefOrGetter<string>
  logger: Pick<ReturnType<typeof window.electronAPI.getLogger>, 'error'>
}

/** 只统一备份请求；归档时机、恢复锁和会话重载仍由编辑页负责。 */
export function useConfigBackupApi({ scriptId, userId, logger }: ConfigBackupApiOptions) {
  const { t } = useI18n()

  // 新建用户后 ID 会变化，不能在创建 composable 时捕获空 ID。
  const context = () => ({ scriptId: toValue(scriptId), userId: toValue(userId) })

  const restore = async (target: string, time: string, force?: boolean) => {
    const operation = beginAnalyticsOperation('config_restore_finished')
    const ids = context()
    const dimensions = {
      script_type: getAnalyticsScriptType(ids.scriptId),
      target_kind:
        target === 'mas'
          ? ('mas' as const)
          : target === 'native' || target === 'onedragon'
            ? ('native' as const)
            : ('unknown' as const),
      forced: force ? ('yes' as const) : ('no' as const),
    }
    try {
      const response = await Service.restoreConfigBackupApiApiScriptsBackupRestorePost({
        ...ids,
        target,
        time,
        ...(force === undefined ? {} : { force }),
      })
      operation.finish({
        ...dimensions,
        outcome:
          response.code === 200
            ? 'success'
            : response.code === 409
              ? 'confirmation_required'
              : 'failure',
      })
      return response
    } catch (error) {
      operation.finish({
        ...dimensions,
        outcome:
          error instanceof ApiError && error.status === 409 ? 'confirmation_required' : 'failure',
      })
      throw error
    }
  }

  const restoreApi = {
    list: async (target: string) => {
      const { scriptId, userId } = context()
      return Service.listConfigBackupsApiApiScriptsBackupListGet(scriptId, userId, target)
    },
    preview: async (target: string, time: string) => {
      const { scriptId, userId } = context()
      return Service.getConfigBackupPreviewApiApiScriptsBackupPreviewGet(
        scriptId,
        userId,
        time,
        target
      )
    },
    // 普通入口维持双参数契约；有损坏配置二次确认的页面显式接入带 force 的 restore。
    restore: (target: string, time: string) => restore(target, time),
    readFile: async (target: string, time: string, path: string) => {
      const { scriptId, userId } = context()
      return Service.getConfigBackupFileApiApiScriptsBackupFileGet(
        scriptId,
        userId,
        time,
        target,
        path
      )
    },
  }

  // 不缓存、不合并、不自动重试归档或恢复；每次调用对应原来的一个请求。
  const ensure = async (target: string) =>
    Service.ensureConfigBackupApiApiScriptsBackupEnsurePost({ ...context(), target })

  /** 归档失败提示后继续编辑；需要展示专项诊断的页面自行处理 ensure 的响应。 */
  const ensureBackup = async (target: string) => {
    if (!toValue(userId)) return
    try {
      const resp = await ensure(target)
      if (resp.code !== 200)
        throw new Error(resp.message || t('core.edit.configRestoreEnsureFailed'))
    } catch (e) {
      logger.error(e instanceof Error ? e.message : String(e))
      message.warning(t('core.edit.configRestoreEnsureFailed'))
    }
  }

  return { restoreApi, restore, ensure, ensureBackup }
}
