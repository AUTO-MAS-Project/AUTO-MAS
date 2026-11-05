import '@/utils/browserDevElectronAPI'
import { createApp, nextTick, watch } from 'vue'
import { createPinia } from 'pinia'
import { VueQueryPlugin } from '@tanstack/vue-query'
import App from './App.vue'
import NoData from '@/components/NoData.vue'
import router from './router/index.ts'
import { OpenAPI } from '@/api'
import { configureLocalMonaco } from '@/utils/monaco'
import { getConfig } from '@/utils/config'
import { configureSentry, recordRendererStartup } from '@/utils/sentry'
import { captureAnalyticsContext, recordRendererReady } from '@/utils/analytics'
import { getDefaultHttpEndpoint } from '@/utils/backendEndpoint'
import { i18n } from '@/i18n'
import { useLocale } from '@/composables/useLocale'
import { useTheme } from '@/composables/useTheme'
import { useAppInitialization } from '@/composables/useAppInitialization'
import { queryClient } from '@/services/queryClient'
import { finishStartupStage, measureStartup } from '@/utils/startupTiming'

import Antd, { message } from 'ant-design-vue'
import 'ant-design-vue/dist/reset.css'
import '@/styles/scrollbar.css'
import '@/styles/formSection.css'
import '@/styles/pageTitle.css'
import '@/styles/appearanceCursor.css'
import '@/styles/appearanceSurfaces.css'
import '@/styles/themeTransition.css'
import '@/styles/appOverlays.css'
import '@/styles/taskboardTokens.css'

const TITLE_BAR_HEIGHT = 32
const MESSAGE_TOP_GAP = 8
const rendererStartedAt = performance.now()
// 从导航起点计时，包含静态 import 执行前的网络、转换和模块求值。
finishStartupStage('文档与静态依赖加载', 0)

// 静态 message 默认从窗口顶部 8px 开始，会覆盖无边框窗口的标题栏。
message.config({ top: `${TITLE_BAR_HEIGHT + MESSAGE_TOP_GAP}px` })

// 导入日志系统
const logger = window.electronAPI.getLogger('前端主入口')

// Monaco 预加载推迟到浏览器空闲时段，避免与首屏渲染争抢主线程
const preloadMonaco = () => {
  void configureLocalMonaco().catch(error => {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.warn(`Monaco 预加载失败，将在下次使用时重试: ${errorMsg}`)
  })
}

if (typeof window.requestIdleCallback === 'function') {
  window.requestIdleCallback(preloadMonaco, { timeout: 5000 })
} else {
  window.setTimeout(preloadMonaco, 2000)
}

if (
  (window as Window & { __AUTO_MAS_BROWSER_DEV_MODE__?: boolean }).__AUTO_MAS_BROWSER_DEV_MODE__
) {
  OpenAPI.BASE = getDefaultHttpEndpoint()
}

import { bootstrapRealtimeResidents } from '@/bootstrap/realtimeResidents'
import { initializeAppLifecycle } from '@/composables/useAppLifecycle'

// 从 Electron 获取 API 端点并设置 OpenAPI.BASE
let apiEndpointReady: Promise<void> = Promise.resolve()
if (window.electronAPI?.getApiEndpoint) {
  apiEndpointReady = window.electronAPI
    .getApiEndpoint('local')
    .then(endpoint => {
      OpenAPI.BASE = endpoint
      logger.info('前端应用开始初始化')
      logger.info(`API基础URL: ${OpenAPI.BASE}`)
    })
    .catch(error => {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`获取 API 端点失败，使用默认值: ${errorMsg}`)
      OpenAPI.BASE = getDefaultHttpEndpoint()
      logger.info(`API基础URL (默认): ${OpenAPI.BASE}`)
    })
} else {
  // 非 Electron 环境，使用默认值
  OpenAPI.BASE = getDefaultHttpEndpoint()
  logger.info('前端应用开始初始化')
  logger.info(`API基础URL (默认): ${OpenAPI.BASE}`)
}

// 创建应用实例
const pluginsStartedAt = performance.now()
const app = createApp(App)

// 注册插件
app.use(createPinia())
app.use(VueQueryPlugin, { queryClient })
app.use(Antd)
app.component('NoData', NoData)
app.use(i18n)

// Pinia 先就绪，常驻订阅仍早于路由首次进入时建立的主 WebSocket 连接。
bootstrapRealtimeResidents()
initializeAppLifecycle()
finishStartupStage('应用插件与常驻订阅', pluginsStartedAt)

// 全局错误处理
app.config.errorHandler = (err, instance, info) => {
  const errorMsg = err instanceof Error ? err.message : String(err)
  logger.error(`Vue应用错误: ${errorMsg}, 组件信息: ${info}`)
}

const bootstrap = async () => {
  await measureStartup('等待 API 端点', () => apiEndpointReady)
  const analyticsContext = captureAnalyticsContext()
  const frontendConfig = await measureStartup('读取本地配置', getConfig)

  // 外观必须在首次挂载前恢复，避免独立窗口和主窗口先显示默认主题后再跳变。
  await measureStartup('恢复主题', () => useTheme().initTheme(frontendConfig))

  // 语言必须在挂载前定好，否则首帧会闪一次默认语言；复用上面已读的配置，避免重复 IPC
  await measureStartup('恢复语言', () => useLocale().initLocale(frontendConfig))
  const sentryStartedAt = performance.now()
  configureSentry(app, router, frontendConfig.Function?.IfEnableTelemetry !== false)
  finishStartupStage('错误收集初始化', sentryStartedAt)

  // 首次路由进入前，端点与本地语言必须已确定，避免按默认语言提前请求业务词表。
  const routeStartedAt = performance.now()
  app.use(router)

  const { isInitialized } = useAppInitialization()
  const stopReadyWatch = watch(
    isInitialized,
    ready => {
      if (!ready) return
      finishStartupStage('业务初始化就绪', rendererStartedAt)
      stopReadyWatch()
    },
    { immediate: false }
  )
  // 旁路观察，不把首路由/绘制等待加进现有挂载流程。
  void router.isReady().then(async () => {
    finishStartupStage('首路由加载', routeStartedAt)
    await nextTick()
    requestAnimationFrame(() => {
      requestAnimationFrame(() => finishStartupStage('首路由绘制后', routeStartedAt))
    })
  })

  // 挂载应用
  const mountStartedAt = performance.now()
  app.mount('#app')
  finishStartupStage('根组件挂载', mountStartedAt)
  window.electronAPI?.notifyRendererReady?.()
  recordRendererReady(analyticsContext, performance.now() - rendererStartedAt)
  recordRendererStartup(performance.now() - rendererStartedAt)

  logger.info('前端应用初始化完成')
}

void bootstrap()
