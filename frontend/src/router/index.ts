import { createRouter, createWebHashHistory } from 'vue-router'
import { isAppInitialized } from '@/utils/config'
import { getLogger } from '@/utils/logger'

const logger = getLogger('路由管理')

// 异步按需加载调度中心，避免弹窗窗口提前执行相关逻辑
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
    meta: { title: '编辑MAA脚本' },
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
    meta: { title: '添加MAA用户' },
  },
  {
    path: '/scripts/:scriptId/users/:userId/edit/maa',
    name: 'MAAUserEdit',
    component: () => import('../views/EditView/User/MAAUserEdit.vue'),
    meta: { title: '编辑MAA用户' },
  },
  {
    path: '/scripts/:scriptId/users/add/general',
    name: 'GeneralUserAdd',
    component: () => import('../views/EditView/User/GeneralUserEdit.vue'),
    meta: { title: '添加通用用户' },
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
    meta: { title: '调度中心' },
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
    meta: { title: 'OCR测试' },
  },
  {
    path: '/history',
    name: 'History',
    component: () => import('../views/history/index.vue'),
    meta: { title: '历史记录' },
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
    meta: { title: '日志查看' },
  },
  {
    path: '/mirror-test',
    name: 'MirrorTest',
    component: () => import('../views/MirrorTest.vue'),
    meta: { title: '镜像配置测试' },
  },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

router.beforeEach(async (to, from, next) => {
  logger.info('路由守卫：', { to: to.path, from: from.path })

  // 声明跳过的路由：直接放行
  if ((to.meta as any)?.skipGuard) {
    next()
    return
  }

  if (to.path === '/initialization') {
    needInitLanding = false
    next()
    return
  }

  const isDev = import.meta.env.VITE_APP_ENV === 'dev'
  if (isDev) return next()

  const initialized = await isAppInitialized()
  logger.info('检查初始化状态：', initialized)
  if (!initialized) {
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
