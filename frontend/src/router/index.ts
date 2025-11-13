import type { RouteRecordRaw } from 'vue-router'
import { createRouter, createWebHistory } from 'vue-router'
import { isAppInitialized } from '@/utils/config'
// 同步导入调度中心，保证其模块级导出（如 handler 注册点）在应用初始化时可用
const SchedulerView = () => import('../views/scheduler/index.vue') // 改为异步按需加载，避免在 Popup/对话框窗口模式下提前执行调度中心相关逻辑

let needInitLanding = true

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    redirect: () => {
      return '/initialization'
    },
  },
  {
    path: '/initialization',
    name: 'Initialization',
    component: () => import('../views/Initialization/index.vue'),
    meta: { title: '初始化' },
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
    component: SchedulerView, // 现在是异步函数，按需加载
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
    component: () => import('../views/History.vue'),
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
  {
    path: '/popup',
    name: 'Popup',
    component: () => import('../views/Popup.vue'),
    meta: { title: '对话框', skipInit: true, skipGuard: true },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// 添加路由守卫，确保在生产环境中也能正确进入初始化页面
router.beforeEach(async (to, from, next) => {
  console.log('路由守卫：', { to: to.path, from: from.path })

  // Popup 路由：跳过所有守卫检查，直接放行
  if (to.path === '/popup') {
    next('/popup')
    return
  }

  // 如果目标就是初始化页，放行并清除一次性标记，避免反复跳转
  if (to.path === '/initialization' && to.path !== '/popup') {
    needInitLanding = false
    next()
    return
  }

  // （可选）开发环境跳过检查，可按需恢复
  const isDev = import.meta.env.VITE_APP_ENV === 'dev'
  if (isDev) return next()

  // 先按原逻辑：未初始化 => 强制进入初始化
  const initialized = await isAppInitialized()
  console.log('检查初始化状态：', initialized)
  if (!initialized) {
    needInitLanding = false // 以免重复重定向
    next('/initialization')
    return
  }

  // 已初始化：如果是“本次启动的第一次进入”，也先去初始化页一次
  if (needInitLanding) {
    needInitLanding = false
    next({ path: '/initialization', query: { redirect: to.fullPath } })
    return
  }

  // 其他情况正常放行
  next()
})

// 路由跳转函数
export function navigateTo(
  path: string,
  options?: {
    replace?: boolean
    query?: Record<string, any>
  }
) {
  const { replace = false, query } = options || {}

  if (replace) {
    return router.replace({ path, query })
  } else {
    return router.push({ path, query })
  }
}

// 通过路由名称跳转的函数
export function navigateToByName(
  name: string,
  options?: {
    replace?: boolean
    query?: Record<string, any>
    params?: Record<string, any>
  }
) {
  const { replace = false, query, params } = options || {}

  if (replace) {
    return router.replace({ name, query, params })
  } else {
    return router.push({ name, query, params })
  }
}

// 返回上一页的函数
export function goBack() {
  return router.back()
}

// 前进到下一页的函数
export function goForward() {
  return router.forward()
}

export default router
