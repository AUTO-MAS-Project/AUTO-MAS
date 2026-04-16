import { createRouter, createWebHashHistory } from 'vue-router'

import { useAppInitialization } from '@/composables/useAppInitialization'
import { getInitializationDecision } from '@/utils/initializationDecision'
import { startSkippedInitializationStartup } from '@/utils/skippedInitializationStartup'

const logger = window.electronAPI.getLogger('路由管理')

const SchedulerView = () => import('../views/scheduler/index.vue')

let needInitLanding = true

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
  {
    path: '/scripts/:id/edit/maa',
    name: 'MAAScriptEdit',
    component: () => import('../views/EditView/Script/MAAScriptEdit.vue'),
    meta: { title: '编辑 MAA 脚本' },
  },
  {
    path: '/scripts/:id/edit/src',
    name: 'SRCScriptEdit',
    component: () => import('../views/EditView/Script/SRCScriptEdit.vue'),
    meta: { title: '编辑 SRC 脚本' },
  },
  {
    path: '/scripts/:id/edit/maaend',
    name: 'MaaEndScriptEdit',
    component: () => import('../views/EditView/Script/MaaEndScriptEdit.vue'),
    meta: { title: '编辑 MaaEnd 脚本' },
  },
  {
    path: '/scripts/:id/edit/general',
    name: 'GeneralScriptEdit',
    component: () => import('../views/EditView/Script/GeneralScriptEdit.vue'),
    meta: { title: '编辑通用脚本' },
  },
  {
    path: '/scripts/:scriptId/users/add/maa',
    name: 'MAAUserAdd',
    component: () => import('../views/EditView/User/MAAUserEdit.vue'),
    meta: { title: '新增 MAA 用户' },
  },
  {
    path: '/scripts/:scriptId/users/:userId/edit/maa',
    name: 'MAAUserEdit',
    component: () => import('../views/EditView/User/MAAUserEdit.vue'),
    meta: { title: '编辑 MAA 用户' },
  },
  {
    path: '/scripts/:scriptId/users/add/src',
    name: 'SRCUserAdd',
    component: () => import('../views/EditView/User/SRCUserEdit.vue'),
    meta: { title: '新增 SRC 用户' },
  },
  {
    path: '/scripts/:scriptId/users/add/maaend',
    name: 'MaaEndUserAdd',
    component: () => import('../views/EditView/User/MaaEndUserEdit.vue'),
    meta: { title: '新增 MaaEnd 用户' },
  },
  {
    path: '/scripts/:scriptId/users/:userId/edit/src',
    name: 'SRCUserEdit',
    component: () => import('../views/EditView/User/SRCUserEdit.vue'),
    meta: { title: '编辑 SRC 用户' },
  },
  {
    path: '/scripts/:scriptId/users/:userId/edit/maaend',
    name: 'MaaEndUserEdit',
    component: () => import('../views/EditView/User/MaaEndUserEdit.vue'),
    meta: { title: '编辑 MaaEnd 用户' },
  },
  {
    path: '/scripts/:scriptId/users/add/general',
    name: 'GeneralUserAdd',
    component: () => import('../views/EditView/User/GeneralUserEdit.vue'),
    meta: { title: '新增通用用户' },
  },
  {
    path: '/scripts/:scriptId/users/:userId/edit/general',
    name: 'GeneralUserEdit',
    component: () => import('../views/EditView/User/GeneralUserEdit.vue'),
    meta: { title: '编辑通用用户' },
  },
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
      keepAlive: true,
    },
  },
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
    meta: { title: 'OCR 测试' },
  },
  {
    path: '/WSdev',
    name: 'WSdev',
    component: () => import('../views/WSdev.vue'),
    meta: { title: 'WSdev' },
  },
  {
    path: '/OverlayMaskDev',
    name: 'OverlayMaskDev',
    component: () => import('../views/OverlayMaskDev.vue'),
    meta: { title: '遮罩彩蛋测试' },
  },
  {
    path: '/history',
    name: 'History',
    component: () => import('../views/history/index.vue'),
    meta: { title: '历史记录' },
  },
  {
    path: '/tools',
    name: 'Tools',
    component: () => import('../views/tools/index.vue'),
    meta: { title: '工具' },
  },
  {
    path: '/plugins',
    name: 'Plugins',
    component: () => import('../views/PluginDev.vue'),
    meta: { title: '插件管理' },
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
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

router.beforeEach(async (to, from, next) => {
  logger.info(`路由守卫：${JSON.stringify({ to: to.path, from: from.path })}`)

  const { isInitialized, isBootstrapping } = useAppInitialization()

  if ((to.meta as any)?.skipGuard) {
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

  const isDev = import.meta.env.DEV
  if (isDev) {
    next()
    return
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
  options?: { replace?: boolean; query?: Record<string, any> }
) {
  const { replace = false, query } = options || {}
  if (replace) return router.replace({ path, query })
  return router.push({ path, query })
}

export function navigateToByName(
  name: string,
  options?: { replace?: boolean; query?: Record<string, any>; params?: Record<string, any> }
) {
  const { replace = false, query, params } = options || {}
  if (replace) return router.replace({ name, query, params })
  return router.push({ name, query, params })
}

export function goBack() {
  return router.back()
}

export function goForward() {
  return router.forward()
}

export default router
