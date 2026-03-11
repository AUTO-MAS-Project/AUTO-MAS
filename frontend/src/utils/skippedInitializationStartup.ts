import { message } from 'ant-design-vue'
import { useAppInitialization } from '@/composables/useAppInitialization'
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
    const api = window.electronAPI as any

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
      resetInitializationStatus()
      sessionStorage.setItem('disableInitializationSkip', 'true')
      message.error('后端启动失败，已切换到初始化页面')

      if (window.location.hash !== '#/initialization') {
        window.location.hash = '#/initialization'
      }
    } finally {
      finishBootstrap()
      startupPromise = null
    }
  })()

  return startupPromise
}
