import { createRouter, createWebHashHistory, type LocationQueryRaw } from 'vue-router'
import { useAppInitialization } from '@/composables/useAppInitialization'
import { getInitializationDecision } from '@/utils/initializationDecision'
import { startSkippedInitializationStartup } from '@/utils/skippedInitializationStartup'

const logger = window.electronAPI.getLogger('路由管理')
let needInitLanding = true

const devRoutes = import.meta.env.DEV
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
    ]
  : []

const routes = [
  { path: '/', redirect: () => '/initialization' },
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
    path: '/plugins',
    name: 'Plugins',
    component: () => import('../views/Plugins.vue'),
    meta: { title: '插件中心' },
  },
  {
    path: '/plugins/market',
    name: 'PluginMarket',
    component: () => import('../views/PluginMarket.vue'),
    meta: { title: '插件市场' },
  },
  {
    path: '/plugins/:pluginId/settings',
    name: 'PluginSettings',
    component: () => import('../views/PluginSettingsPage.vue'),
    meta: { title: '插件设置' },
  },
  {
    path: '/plugins/:pluginId/:pageId',
    name: 'PluginPage',
    component: () => import('../views/PluginSettingsPage.vue'),
    meta: { title: '插件页面' },
  },
  {
    path: '/scripts',
    name: 'Scripts',
    component: () => import('../views/Scripts.vue'),
    meta: { title: '脚本管理' },
  },
  {
    path: '/plans',
    name: 'Plans',
    component: () => import('../views/plan/index.vue'),
    meta: { title: '计划管理' },
  },
  {
    path: '/games',
    name: 'Games',
    component: () => import('../views/Games.vue'),
    meta: { title: '游戏管理' },
  },
  { path: '/emulators', redirect: '/games' },
  {
    path: '/queue',
    name: 'Queue',
    component: () => import('../views/queue/index.vue'),
    meta: { title: '调度队列' },
  },
  {
    path: '/scheduler',
    name: 'Scheduler',
    component: () => import('../views/scheduler/index.vue'),
    meta: { title: '调度中心' },
  },
  {
    path: '/history',
    name: 'History',
    component: () => import('../views/history/index.vue'),
    meta: { title: '历史记录' },
  },
  {
    path: '/gamesign',
    name: 'GameSign',
    component: () => import('../views/gamesign/index.vue'),
    meta: { title: '游戏社区' },
  },
  {
    path: '/tools',
    name: 'Tools',
    component: () => import('../views/tools/index.vue'),
    meta: { title: '工具' },
  },
  {
    path: '/settings',
    name: 'Settings',
    component: () => import('../views/setting/index.vue'),
    meta: { title: '设置' },
  },
  {
    path: '/logs',
    name: 'Logs',
    component: () => import('../views/Logs.vue'),
    meta: { title: '日志查看', skipGuard: true },
  },
  {
    path: '/vdd-prompt',
    name: 'VirtualDisplayPrompt',
    component: () => import('../views/VirtualDisplayPrompt.vue'),
    meta: { title: '虚拟显示器', skipGuard: true },
  },
  ...devRoutes,
]

const router = createRouter({ history: createWebHashHistory(), routes })

router.beforeEach(async (to, from, next) => {
  logger.info(`路由守卫：${JSON.stringify({ to: to.path, from: from.path })}`)
  const { isInitialized, isBootstrapping } = useAppInitialization()

  if (to.meta.skipGuard === true) {
    next()
    return
  }

  if (to.path === '/initialization') {
    if (!isInitialized.value && !isBootstrapping.value) {
      const decision = await getInitializationDecision()
      if (decision.mode === 'skip-home') {
        needInitLanding = false
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

  if (import.meta.env.DEV) {
    if (!isInitialized.value && !isBootstrapping.value) {
      const { beginBootstrap, finishBootstrap, markAsInitialized } = useAppInitialization()
      beginBootstrap()
      void (async () => {
        try {
          const { connectWithRetry } = await import('@/composables/useAppLifecycle')
          await connectWithRetry()
        } catch (error) {
          logger.error(`开发模式直达内页启动失败: ${error instanceof Error ? error.message : String(error)}`)
        } finally {
          markAsInitialized()
          finishBootstrap()
        }
      })()
    }
    next()
    return
  }

  if (isBootstrapping.value) {
    needInitLanding = false
    if (to.path === '/home') {
      next()
    } else {
      next('/home')
    }
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
  options?: { replace?: boolean; query?: LocationQueryRaw },
) {
  const { replace = false, query } = options || {}
  return replace ? router.replace({ path, query }) : router.push({ path, query })
}

export default router
