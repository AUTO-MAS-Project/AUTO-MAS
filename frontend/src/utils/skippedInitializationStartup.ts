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
    const api = window.electronAPI

    try {
      if (!import.meta.env.DEV) {
        // 即使应用版本号未变化，也必须验证随包 wheel、bootstrap state 与
        // 已安装 entry point。主进程在单一互斥区内完成精确停服、修复与重启。
        const result = await api.repairRuntimeAndStart?.()
        if (!result?.success) {
          throw new Error(result?.error || result?.summary || '运行环境检查或后端启动失败')
        }
      }

      const success = await enterApp('跳过初始化直接进入首页', false)
      if (!success) {
        throw new Error('进入应用失败')
      }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`跳过初始化启动失败: ${errorMsg}`)
      resetInitializationStatus()
      sessionStorage.setItem('disableInitializationSkip', 'true')
      message.error('运行环境检查失败，已切换到初始化页面')

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
