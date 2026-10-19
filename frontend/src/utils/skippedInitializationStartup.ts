import { translate as t } from '@/i18n'
import { message } from 'ant-design-vue'
import { useAppInitialization } from '@/composables/useAppInitialization'
import { navigateTo } from '@/router'
import { enterApp } from '@/utils/appEntry'

const logger = window.electronAPI.getLogger('跳过初始化启动')

let startupPromise: Promise<void> | null = null

export function startSkippedInitializationStartup(): Promise<void> {
  if (startupPromise) {
    return startupPromise
  }

  const { beginBootstrap, finishBootstrap, resetInitializationStatus } = useAppInitialization()
  beginBootstrap()

  startupPromise = (async () => {
    const api = window.electronAPI

    try {
      if (!import.meta.env.DEV) {
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
        throw new Error('进入应用失败')
      }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`跳过初始化启动失败: ${errorMsg}`)
      sessionStorage.setItem('disableInitializationSkip', 'true')
      message.error(t('misc.backendFailedStartSwitching'))

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
