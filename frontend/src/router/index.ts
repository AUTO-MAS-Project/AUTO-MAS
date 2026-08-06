import { createRouter, createWebHashHistory } from 'vue-router'
import type { RouteLocationGeneric } from 'vue-router'
import { useAppInitialization } from '@/composables/useAppInitialization'
import { getInitializationDecision } from '@/utils/initializationDecision'
import { startSkippedInitializationStartup } from '@/utils/skippedInitializationStartup'
import { createPageRoutes, FALLBACK_PAGE_DECLARATIONS } from './pageDeclarations'

const logger = window.electronAPI.getLogger('\u8def\u7531\u7ba1\u7406')

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
    meta: { title: 'AUTO-MAS \u521d\u59cb\u5316' },
  },
  ...createPageRoutes(FALLBACK_PAGE_DECLARATIONS),
  {
    path: '/scripts/:id/edit/src',
    name: 'SRCScriptEdit',
    component: () => import('../views/EditView/Script/SRCScriptEdit.vue'),
    meta: { title: '\u7f16\u8f91 SRC \u811a\u672c' },
  },
  {
    path: '/scripts/:id/edit/maaend',
    name: 'MaaEndScriptEdit',
    component: () => import('../views/EditView/Script/MaaEndScriptEdit.vue'),
    meta: { title: '\u7f16\u8f91 MaaEnd \u811a\u672c' },
  },
  {
    path: '/scripts/:id/edit/m9a',
    redirect: (to: RouteLocationGeneric) => `/scripts/${to.params.id}/edit/maafw`,
    name: 'M9AScriptEdit',
    meta: { title: '编辑M9A脚本' },
  },
  {
    path: '/scripts/:id/edit/maafw',
    name: 'MaaFWScriptEdit',
    component: () => import('../views/EditView/Script/MaaFWScriptEdit.vue'),
    meta: { title: '编辑MaaFramework项目' },
  },
  {
    path: '/scripts/:id/setup/m9a',
    redirect: (to: RouteLocationGeneric) => `/scripts/${to.params.id}/setup/maafw`,
    name: 'M9ASetupWizard',
    meta: { title: 'M9A项目引导' },
  },
  {
    path: '/scripts/:id/setup/maafw',
    name: 'MaaFWSetupWizard',
    component: () => import('../views/EditView/Script/MaaFWSetupWizard.vue'),
    meta: { title: 'MaaFramework项目引导' },
  },
  {
    path: '/scripts/:id/edit/hsr',
    name: 'HSRScriptEdit',
    component: () => import('../views/EditView/Script/HSRScriptEdit.vue'),
    meta: { title: '编辑HSR脚本' },
  },
  {
    path: '/scripts/:id/edit/general',
    name: 'GeneralScriptEdit',
    component: () => import('../views/EditView/Script/GeneralScriptEdit.vue'),
    meta: { title: '编辑通用脚本' },
  },
  {
    path: '/scripts/:id/edit/okww',
    name: 'OkwwScriptEdit',
    component: () => import('../views/EditView/Script/OkwwScriptEdit.vue'),
    meta: { title: '编辑 Okww 项目' },
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
    path: '/scripts/:id/edit/schema',
    name: 'GenericScriptEdit',
    component: () => import('../views/EditView/Script/GenericScriptEdit.vue'),
    meta: { title: '\u7f16\u8f91 Schema \u811a\u672c' },
  },
  {
    path: '/scripts/:id/edit/plugin',
    name: 'PluginScriptEdit',
    component: () => import('../views/EditView/Script/PluginScriptEdit.vue'),
    meta: { title: '\u7f16\u8f91\u63d2\u4ef6\u811a\u672c' },
  },
  {
    path: '/scripts/:scriptId/users/add/src',
    name: 'SRCUserAdd',
    component: () => import('../views/EditView/User/SRCUserEdit.vue'),
    meta: { title: '\u6dfb\u52a0 SRC \u7528\u6237' },
  },
  {
    path: '/scripts/:scriptId/users/add/maaend',
    name: 'MaaEndUserAdd',
    component: () => import('../views/EditView/User/MaaEndUserEdit.vue'),
    meta: { title: '\u6dfb\u52a0 MaaEnd \u7528\u6237' },
  },
  {
    path: '/scripts/:scriptId/users/add/m9a',
    redirect: (to: RouteLocationGeneric) => `/scripts/${to.params.scriptId}/users/add/maafw`,
    name: 'M9AUserAdd',
    meta: { title: '添加M9A用户' },
  },
  {
    path: '/scripts/:scriptId/users/add/maafw',
    name: 'MaaFWUserAdd',
    component: () => import('../views/EditView/User/MaaFWUserEdit.vue'),
    meta: { title: '添加MaaFramework用户' },
  },
  {
    path: '/scripts/:scriptId/users/add/hsr',
    name: 'HSRUserAdd',
    component: () => import('../views/EditView/User/HSRUserEdit.vue'),
    meta: { title: '添加HSR用户' },
  },
  {
    path: '/scripts/:scriptId/users/:userId/edit/src',
    name: 'SRCUserEdit',
    component: () => import('../views/EditView/User/SRCUserEdit.vue'),
    meta: { title: '\u7f16\u8f91 SRC \u7528\u6237' },
  },
  {
    path: '/scripts/:scriptId/users/:userId/edit/maaend',
    name: 'MaaEndUserEdit',
    component: () => import('../views/EditView/User/MaaEndUserEdit.vue'),
    meta: { title: '\u7f16\u8f91 MaaEnd \u7528\u6237' },
  },
  {
    path: '/scripts/:scriptId/users/:userId/edit/m9a',
    redirect: (to: RouteLocationGeneric) =>
      `/scripts/${to.params.scriptId}/users/${to.params.userId}/edit/maafw`,
    name: 'M9AUserEdit',
    meta: { title: '编辑M9A用户' },
  },
  {
    path: '/scripts/:scriptId/users/:userId/edit/maafw',
    name: 'MaaFWUserEdit',
    component: () => import('../views/EditView/User/MaaFWUserEdit.vue'),
    meta: { title: '编辑MaaFramework用户' },
  },
  {
    path: '/scripts/:scriptId/users/:userId/edit/hsr',
    name: 'HSRUserEdit',
    component: () => import('../views/EditView/User/HSRUserEdit.vue'),
    meta: { title: '编辑HSR用户' },
  },
  {
    path: '/scripts/:scriptId/users/add/general',
    name: 'GeneralUserAdd',
    component: () => import('../views/EditView/User/GeneralUserEdit.vue'),
    meta: { title: '添加通用用户' },
  },
  {
    path: '/scripts/:scriptId/users/add/schema',
    name: 'GenericUserAdd',
    component: () => import('../views/EditView/User/GenericUserEdit.vue'),
    meta: { title: '\u6dfb\u52a0 Schema \u7528\u6237' },
  },
  {
    path: '/scripts/:scriptId/users/add/plugin',
    name: 'PluginUserAdd',
    component: () => import('../views/EditView/User/PluginUserEdit.vue'),
    meta: { title: '\u6dfb\u52a0\u63d2\u4ef6\u811a\u672c\u7528\u6237' },
  },
  {
    path: '/scripts/:scriptId/users/add/okww',
    name: 'OkwwUserAdd',
    component: () => import('../views/EditView/User/OkwwUserEdit.vue'),
    meta: { title: '添加鸣潮用户' },
  },
  {
    path: '/scripts/:scriptId/users/:userId/edit/okww',
    name: 'OkwwUserEdit',
    component: () => import('../views/EditView/User/OkwwUserEdit.vue'),
    meta: { title: '编辑鸣潮用户' },
  },
  {
    path: '/plans',
    name: 'Plans',
    component: () => import('../views/plan/index.vue'),
    meta: { title: '计划管理' },
  },
  {
    path: '/scripts/:scriptId/users/:userId/edit/schema',
    name: 'GenericUserEdit',
    component: () => import('../views/EditView/User/GenericUserEdit.vue'),
    meta: { title: '\u7f16\u8f91 Schema \u7528\u6237' },
  },
  {
    path: '/scripts/:scriptId/users/:userId/edit/plugin',
    name: 'PluginUserEdit',
    component: () => import('../views/EditView/User/PluginUserEdit.vue'),
    meta: { title: '\u7f16\u8f91\u63d2\u4ef6\u811a\u672c\u7528\u6237' },
  },
  {
    path: '/logs',
    name: 'Logs',
    component: () => import('../views/Logs.vue'),
    meta: { title: '\u65e5\u5fd7\u67e5\u770b', skipGuard: true },
  },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

router.beforeEach(async (to, from, next) => {
  logger.info(`\u8def\u7531\u5b88\u536b: ${JSON.stringify({ to: to.path, from: from.path })}`)

  const { isInitialized, isBootstrapping, isAppReady } = useAppInitialization()

  if (to.meta.skipGuard) {
    next()
    return
  }

  if (to.path === '/initialization') {
    if (!isInitialized.value && !isBootstrapping.value) {
      const decision = await getInitializationDecision()
      if (decision.mode === 'skip-home') {
        needInitLanding = false
        logger.info(
          `\u547d\u4e2d\u8df3\u8fc7\u521d\u59cb\u5316\u6761\u4ef6\uff0c\u76f4\u63a5\u8fdb\u5165\u4e3b\u9875: ${JSON.stringify(decision)}`
        )
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
    if (!isAppReady.value && to.path !== '/initialization') {
      next({ path: '/initialization', query: { redirect: to.fullPath } })
      return
    }
    next()
    return
  }

  logger.info(
    `\u521d\u59cb\u5316\u72b6\u6001\u68c0\u67e5: ${JSON.stringify({
      isInitialized: isInitialized.value,
      isBootstrapping: isBootstrapping.value,
    })}`
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
