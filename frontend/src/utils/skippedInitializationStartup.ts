import { message } from 'ant-design-vue'
import { useAppInitialization } from '@/composables/useAppInitialization'
import { useAppStartup } from '@/composables/useAppStartup'
import { enterApp } from '@/utils/appEntry'

const logger = window.electronAPI.getLogger('跳过初始化启动')

let startupPromise: Promise<void> | null = null

export function startSkippedInitializationStartup(): Promise<void> {
  if (startupPromise) {
    return startupPromise
  }

  const { beginBootstrap, finishBootstrap, resetInitializationStatus } = useAppInitialization()
  const { setStatus } = useAppStartup()
  beginBootstrap()
  setStatus('backend-starting', {
    stage: 'runtime',
    message: '正在校验运行环境...',
  })

  startupPromise = (async () => {
    const api = window.electronAPI
    let currentStage: 'runtime' | 'backend' | 'connection' = 'runtime'

    try {
      if (!import.meta.env.DEV) {
        // 即使应用版本号未变化，也必须验证随包 wheel、bootstrap state 与
        // 已安装 entry point。主进程在单一互斥区内完成精确停服、修复与重启。
        const result = await api.repairRuntimeAndStart?.()
        if (!result?.success) {
          throw new Error(result?.error || result?.summary || '运行环境检查或后端启动失败')
        }
      }

      currentStage = 'backend'
      setStatus('backend-starting', {
        stage: currentStage,
        message: '后端已启动，正在加载配置与插件...',
      })

      // Browser-only Vite preview has no Electron-managed backend process. Allow
      // it to render the real application shell so UI work can be verified
      // against the design source without weakening packaged startup checks.
      currentStage = 'connection'
      const success = await enterApp('跳过初始化直接进入首页', import.meta.env.DEV)
      if (!success) {
        throw new Error('进入应用失败')
      }

      const visualRoute = new URLSearchParams(window.location.search).get('visual-route')
      if (import.meta.env.DEV && visualRoute?.startsWith('/')) {
        window.location.hash = `#${visualRoute}`
      }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`跳过初始化启动失败: ${errorMsg}`)
      setStatus('failed', {
        stage: currentStage,
        detail: errorMsg,
      })
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
