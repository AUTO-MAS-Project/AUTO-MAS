import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'

import { isAppInitialized } from '@/utils/config'

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
    component: () => import('../views/Initialization.vue'),
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
    path: '/scripts/:id/edit',
    name: 'ScriptEdit',
    component: () => import('../views/ScriptEdit.vue'),
    meta: { title: '编辑脚本' },
  },
  {
    path: '/scripts/:scriptId/users/add',
    name: 'UserAdd',
    component: () => import('../views/UserEdit.vue'),
    meta: { title: '添加用户' },
  },
  {
    path: '/scripts/:scriptId/users/:userId/edit',
    name: 'UserEdit',
    component: () => import('../views/UserEdit.vue'),
    meta: { title: '编辑用户' },
  },
  {
    path: '/plans',
    name: 'Plans',
    component: () => import('../views/Plans.vue'),
    meta: { title: '计划管理' },
  },
  {
    path: '/queue',
    name: 'Queue',
    component: () => import('../views/Queue.vue'),
    meta: { title: '调度队列' },
  },
  {
    path: '/scheduler',
    name: 'Scheduler',
    component: () => import('../views/Scheduler.vue'),
    meta: { title: '调度中心' },
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
    component: () => import('../views/Settings.vue'),
    meta: { title: '设置' },
  },
  {
    path: '/logs',
    name: 'Logs',
    component: () => import('../views/Logs.vue'),
    meta: { title: '系统日志' },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// 添加路由守卫，确保在生产环境中也能正确进入初始化页面
router.beforeEach(async (to, from, next) => {
  console.log('路由守卫：', { to: to.path, from: from.path })

  // 如果访问的不是初始化页面，且没有初始化标记，则重定向到初始化页面
  if (to.path !== '/initialization') {
    // 在开发环境下跳过初始化检查
    const isDev = import.meta.env.VITE_APP_ENV === 'dev'
    if (isDev) {
      console.log('开发环境，跳过初始化检查')
      next()
      return
    }

    const initialized = await isAppInitialized()
    console.log('检查初始化状态：', initialized)

    if (!initialized) {
      console.log('应用未初始化，重定向到初始化页面')
      next('/initialization')
      return
    }
  }

  next()
})

export default router
