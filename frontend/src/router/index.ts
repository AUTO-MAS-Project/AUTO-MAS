import { isDevelopmentEnvironment as isDev } from '@/utils/environment'
import { createRouter, createWebHashHistory, type LocationQueryRaw } from 'vue-router'
import { useAppInitialization } from '@/composables/useAppInitialization'
import { getInitializationDecision } from '@/utils/initializationDecision'
import { startSkippedInitializationStartup } from '@/utils/skippedInitializationStartup'
import { SCRIPT_ROUTES } from '@/scriptDescriptors'
import { registerRouterAnalytics } from './analytics'
const logger = window.electronAPI.getLogger('路由管理')

// 异步按需加载调度中心，避免弹窗窗口提前执行相关逻辑
const SchedulerView = () => import('../views/scheduler/index.vue')

let needInitLanding = true

// 调试页仅在开发环境注册。import.meta.env.DEV 是编译期常量，
// 生产构建时整个数组会被判定为死代码，这几个页面不会进入产物。
const devRoutes =
  import.meta.env.DEV && isDev
    ? [
        {
          path: '/TestRouter',
          name: 'TestRouter',
          component: () => import('../views/TestRouter.vue'),
          meta: { title: '测试路由' },
        },
        {
          path: '/OCRdev',
          name: 'OCRdev',
          component: () => import('../views/OCRdev.vue'),
          meta: { title: 'OCR测试' },
        },
        {
          path: '/OverlayMaskDev',
          name: 'OverlayMaskDev',
          component: () => import('../views/OverlayMaskDev.vue'),
          meta: { title: '遮罩彩蛋测试' },
        },
      ]
    : []

const routes = [
  {
    path: '/',
    redirect: () => '/initialization',
  },
  {
    path: '/initialization',
    name: 'Initialization',
    component: () => import('../views/Initialization/index.vue'),
    meta: { title: 'AUTO-MAS 初始化' },
  },
  {
    path: '/home',
    name: 'Home',
    component: () => import('../views/Home.vue'),
    meta: { title: '主页' },
  },
  {
    path: '/scripts',
    name: 'Scripts',
    component: () => import('../views/Scripts.vue'),
    meta: { title: '脚本管理' },
  },
  ...SCRIPT_ROUTES,
  {
    path: '/plans',
    name: 'Plans',
    component: () => import('../views/plan/index.vue'),
    meta: { title: '计划管理' },
  },
  {
    path: '/emulators',
    name: 'Emulators',
    component: () => import('../views/Emulator.vue'),
    meta: { title: '模拟器管理' },
  },
  {
    path: '/queue',
    name: 'Queue',
    component: () => import('../views/queue/index.vue'),
    meta: { title: '调度队列' },
  },
  {
    path: '/scheduler',
    name: 'Scheduler',
    component: SchedulerView,
    meta: {
      title: '调度中心',
      keepAlive: true, // 启用 keep-alive，保持组件存活
    },
  },
  ...devRoutes,
  {
    path: '/history',
    name: 'History',
    component: () => import('../views/history/index.vue'),
    meta: { title: '历史记录' },
  },
  {
    path: '/taskboard',
    name: 'Taskboard',
    component: () => import('@/views/taskboard/index.vue'),
    meta: { title: '任务台' },
  },
  {
    path: '/gamesign',
    name: 'GameSign',
    component: () => import('../views/gamesign/index.vue'),
    meta: { title: '游戏社区' },
  },
  {
    path: '/gamesign/sign',
    name: 'CommunityToolSign',
    redirect: '/gamesign',
    meta: { title: '游戏社区' },
  },
  {
    path: '/gamesign/activity',
    name: 'CommunityToolActivity',
    redirect: {
      path: '/gamesign',
      query: { tab: 'activity' },
    },
    meta: { title: '游戏社区' },
  },
  {
    path: '/theme-store',
    name: 'ThemeStore',
    component: () => import('../views/themeStore/index.vue'),
    meta: { title: '主题商店' },
  },
  {
    path: '/settings',
    name: 'Settings',
    component: () => import('../views/setting/index.vue'),
    meta: { title: '设置' },
  },
  {
    path: '/settings/mystery',
    name: 'Mystery',
    component: () => import('../views/mystery/index.vue'),
    meta: { title: '神秘入口' },
    children: [
      {
        path: 'tokens',
        name: 'MysteryTokens',
        component: () => import('../views/mystery/tokens/index.vue'),
        meta: { title: 'Token 获取', mysteryTitleKey: 'core.mystery.tokens.title' },
      },
    ],
  },
  {
    path: '/logs',
    name: 'Logs',
    component: () => import('../views/Logs.vue'),
    meta: { title: '日志查看', skipGuard: true },
  },
  {
    // 主进程另开的小窗口：真实显示器回来了但有任务在跑，问用户要不要拆虚拟屏
    path: '/vdd-prompt',
    name: 'VirtualDisplayPrompt',
    component: () => import('../views/VirtualDisplayPrompt.vue'),
    meta: { title: '虚拟显示器', skipGuard: true },
  },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

router.beforeEach(async (to, from, next) => {
  logger.info(`路由守卫：${JSON.stringify({ to: to.path, from: from.path })}`)

  const { isInitialized, isBootstrapping } = useAppInitialization()

  // 声明跳过的路由：直接放行
  if (to.meta.skipGuard === true) {
    next()
    return
  }

  if (to.path === '/initialization') {
    if (!isInitialized.value && !isBootstrapping.value) {
      const decision = await getInitializationDecision()
      if (decision.mode === 'skip-home') {
        needInitLanding = false
        logger.info(`命中跳过初始化条件，直接进入主页: ${JSON.stringify(decision)}`)
        void startSkippedInitializationStartup()
        next('/home')
        return
      }
    }

    sessionStorage.removeItem('disableInitializationSkip')
    needInitLanding = false
    next()
    return
  }

  if (isDev) {
    // 开发模式免初始化门禁，但直达内页（如刷新后落在 /scripts）时仍需
    // 建立主 WebSocket 连接并标记初始化，否则 isAppReady 恒为 false 导致整窗空白。
    // 旧版由 useWebSocket 单体的全局自动连接掩盖了这一缺口。
    if (!isInitialized.value && !isBootstrapping.value) {
      const { beginBootstrap, finishBootstrap, markAsInitialized } = useAppInitialization()
      beginBootstrap()
      void (async () => {
        try {
          const { connectWithRetry } = await import('@/composables/useAppLifecycle')
          await connectWithRetry()
        } catch (error) {
          const errorMsg = error instanceof Error ? error.message : String(error)
          logger.error(`开发模式直达内页启动失败: ${errorMsg}`)
        } finally {
          // 开发模式仍须准备界面词表；失败时由本地资源恢复界面承接。
          const { useBackendI18nStore } = await import('@/stores/backendI18n')
          if (await useBackendI18nStore().ensure()) markAsInitialized()
          finishBootstrap()
        }
      })()
    }
    return next()
  }

  logger.info(
    `检查初始化状态：${JSON.stringify({ isInitialized: isInitialized.value, isBootstrapping: isBootstrapping.value })}`
  )
  if (isBootstrapping.value) {
    needInitLanding = false
    if (to.path !== '/home') {
      next('/home')
      return
    }
    next()
    return
  }

  if (!isInitialized.value) {
    needInitLanding = false
    next('/initialization')
    return
  }

  if (needInitLanding) {
    needInitLanding = false
    next({ path: '/initialization', query: { redirect: to.fullPath } })
    return
  }

  next()
})

export function navigateTo(
  path: string,
  options?: { replace?: boolean; query?: LocationQueryRaw }
) {
  const { replace = false, query } = options || {}
  if (replace) return router.replace({ path, query })
  return router.push({ path, query })
}

registerRouterAnalytics(router)

export default router
