import { isDevelopmentEnvironment as isDev } from '@/utils/environment'
import { translate as t } from '@/i18n'
import { message } from 'ant-design-vue'
import { useAppInitialization } from '@/composables/useAppInitialization'
import { navigateTo } from '@/router'
import { enterApp } from '@/utils/appEntry'
import { beginAnalyticsOperation } from '@/utils/analytics'
import { connectionState } from '@/services/websocket/connection'

const logger = window.electronAPI.getLogger('跳过初始化启动')

let startupPromise: Promise<void> | null = null

export function startSkippedInitializationStartup(): Promise<void> {
  if (startupPromise) {
    return startupPromise
  }

  const { beginBootstrap, finishBootstrap, resetInitializationStatus } = useAppInitialization()
  beginBootstrap()
  const operation = beginAnalyticsOperation('initialization_finished')

  startupPromise = (async () => {
    const api = window.electronAPI

    try {
      if (!isDev) {
        const backendStatus = await api.backendStatus?.().catch(() => null)

        if (!backendStatus?.isRunning) {
          logger.info('检测到后端未运行，开始后台启动')
          const result = await api.backendStart?.()
          if (!result?.success) {
            throw new Error(result?.error || '后端启动失败')
          }
        } else {
          logger.info(`检测到后端已运行，PID: ${backendStatus.pid ?? 'unknown'}`)
        }
      }

      const success = await enterApp('跳过初始化直接进入首页', true)
      if (!success) {
        operation.finish({
          flow_kind: 'skip',
          runtime_mode: 'unknown',
          failed_stage: 'unknown',
          outcome: 'failure',
        })
        return
      }
      operation.finish({
        flow_kind: 'skip',
        runtime_mode: 'unknown',
        failed_stage: 'none',
        outcome: connectionState().value === 'open' ? 'success' : 'unconfirmed',
      })
    } catch (error) {
      operation.finish({
        flow_kind: 'skip',
        runtime_mode: 'unknown',
        failed_stage: 'backend',
        outcome: 'failure',
      })
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`跳过初始化启动失败: ${errorMsg}`)
      sessionStorage.setItem('disableInitializationSkip', 'true')
      message.error(t('bootstrap.misc.backendFailedStartSwitching'))

      // 取消尚未完成的主页跳转，初始化页落地前保留启动遮罩。
      await navigateTo('/initialization', { replace: true })
      resetInitializationStatus()
    } finally {
      finishBootstrap()
      startupPromise = null
    }
  })()

  return startupPromise
}
