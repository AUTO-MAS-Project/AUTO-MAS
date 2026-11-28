import {
  useRouter,
  type HistoryState,
  type RouteLocationNormalized,
  type Router,
  type RouteRecordRaw,
} from 'vue-router'
import { getPluginRegistry } from '@/composables/usePluginScriptTypes'
import { compatibleWheel, indexPluginScriptTypes } from '@/utils/pluginScriptTypes'
import { maafwRouteName } from './maafwRoutes'
import { isMaaFWFamily } from '@/plugins/maafwFamily'
import type { BuiltinScriptType } from '@/types/script'
import { SCRIPT_PLUGIN_EDITORS, type MaaFWFamilyType } from '@/plugins/scriptAdapters'
import { SCRIPT_METADATA } from '@/utils/scriptMetadata'

type OrdinaryScriptType = Exclude<BuiltinScriptType, MaaFWFamilyType | 'SRC'>
type LazyPage = Extract<RouteRecordRaw, { component: unknown }>['component']

const EDITOR_PAGES: Record<string, { script: LazyPage; user: LazyPage }> = {
  ...SCRIPT_PLUGIN_EDITORS,
  MaaEnd: {
    script: () => import('@/views/EditView/Script/MaaEndScriptEdit.vue'),
    user: () => import('@/views/EditView/User/MaaEndUserEdit.vue'),
  },
  HSR: {
    script: () => import('@/views/EditView/Script/HSRScriptEdit.vue'),
    user: () => import('@/views/EditView/User/HSRUserEdit.vue'),
  },
  General: {
    script: () => import('@/views/EditView/Script/GeneralScriptEdit.vue'),
    user: () => import('@/views/EditView/User/GeneralUserEdit.vue'),
  },
  BAAH: {
    script: () => import('@/views/EditView/Script/BAAHScriptEdit.vue'),
    user: () => import('@/views/EditView/User/BAAHUserEdit.vue'),
  },
  Okww: {
    script: () => import('@/views/EditView/Script/OkwwScriptEdit.vue'),
    user: () => import('@/views/EditView/User/OkwwUserEdit.vue'),
  },
  OkNte: {
    script: () => import('@/views/EditView/Script/OkNteScriptEdit.vue'),
    user: () => import('@/views/EditView/User/OkNteUserEdit.vue'),
  },
  ZzzOd: {
    script: () => import('@/views/EditView/Script/ZzzOdScriptEdit.vue'),
    user: () => import('@/views/EditView/User/ZzzOdUserEdit.vue'),
  },
}

const PAGE_ROUTES = {
  script: { name: 'ScriptEdit', path: (suffix: string) => `/scripts/:id/edit/${suffix}` },
  userAdd: { name: 'UserAdd', path: (suffix: string) => `/scripts/:scriptId/users/add/${suffix}` },
  userEdit: {
    name: 'UserEdit',
    path: (suffix: string) => `/scripts/:scriptId/users/:userId/edit/${suffix}`,
  },
}

export type ScriptEditorKind = keyof typeof PAGE_ROUTES
const routeNameOf = (type: string, kind: ScriptEditorKind | 'user') =>
  `${type}${PAGE_ROUTES[kind === 'user' ? 'userEdit' : kind].name}`
const genericPanelRoute = {
  script: 'GenericScriptEdit',
  setup: 'GenericScriptSetup',
  user: 'GenericUserEdit',
} as const

function staticPanelRoute(type: string, surface: keyof typeof genericPanelRoute) {
  if (surface === 'setup') return isMaaFWFamily(type) ? maafwRouteName(type, 'setup') : undefined
  return routeNameOf(type, surface)
}

export async function resolveScriptPanelRoute(
  to: RouteLocationNormalized,
  router: Router,
  type: string
) {
  const page = to.meta.maafwPage ?? to.meta.scriptPage
  if (!page) return
  const kind =
    to.name === genericPanelRoute.setup
      ? 'setup'
      : page === 'userEdit' || page === 'userAdd'
        ? 'user'
        : page
  const custom = page === 'userAdd' ? routeNameOf(type, page) : staticPanelRoute(type, kind)
  const generic = page === 'userAdd' ? 'GenericUserAdd' : genericPanelRoute[kind]
  if (!custom || custom === generic || !router.hasRoute(custom)) return
  const { frontendByScriptKey, blockSurfacesByScriptKey } = indexPluginScriptTypes(
    (await getPluginRegistry()).data
  )
  const surface = frontendByScriptKey.get(type)?.[kind]
  const name =
    blockSurfacesByScriptKey.get(type)?.has(kind) || compatibleWheel(surface) ? generic : custom
  if (name === to.name) {
    if (page === 'userAdd' && name === custom) return
    return true
  }
  const scriptId = to.params.scriptId ?? to.params.id
  const params = page === 'userEdit' ? { scriptId, userId: to.params.userId } : { scriptId }
  return {
    name,
    params:
      name === generic
        ? { ...params, scriptType: type }
        : kind === 'user'
          ? params
          : { id: scriptId },
    query: to.query,
    hash: to.hash,
  }
}

type ScriptEditorParams = {
  setup: { id: string }
  script: { id: string }
  userAdd: { scriptId: string }
  user: { scriptId: string; userId: string }
  userEdit: { scriptId: string; userId: string }
}

declare module 'vue-router' {
  interface RouteMeta {
    /** 普通专项页面种类；MFW 保留自身的引导和 canonical 路由契约。 */
    scriptPage?: ScriptEditorKind
  }
}

const genericEditor = () => import('@/views/plugins/ConfigEditor.vue')

export const srcEditorRedirects: RouteRecordRaw[] = [
  {
    path: PAGE_ROUTES.script.path(SCRIPT_METADATA.SRC.routeSuffix),
    redirect: to => ({
      name: genericPanelRoute.script,
      params: { scriptId: to.params.id, scriptType: 'SRC' },
    }),
  },
  {
    path: PAGE_ROUTES.userAdd.path(SCRIPT_METADATA.SRC.routeSuffix),
    redirect: to => ({
      name: 'GenericUserAdd',
      params: { scriptId: to.params.scriptId, scriptType: 'SRC' },
    }),
  },
  {
    path: PAGE_ROUTES.userEdit.path(SCRIPT_METADATA.SRC.routeSuffix),
    redirect: to => ({
      name: genericPanelRoute.user,
      params: { scriptId: to.params.scriptId, userId: to.params.userId, scriptType: 'SRC' },
    }),
  },
]

export const genericEditorRoutes: RouteRecordRaw[] = [
  {
    path: PAGE_ROUTES.userAdd.path('plugin/:scriptType'),
    name: 'GenericUserAdd',
    component: () => import('@/views/plugins/PluginUserAdd.vue'),
    props: true,
    meta: { title: 'core.comp.addUser', scriptPage: 'userAdd' },
  },
  {
    path: '/scripts/:scriptId/setup/plugin/:scriptType',
    name: genericPanelRoute.setup,
    component: genericEditor,
    props: { mode: 'script', setup: true },
    meta: { title: 'core.comp.editScript', scriptPage: 'script' },
  },
  {
    path: '/scripts/:scriptId/edit/plugin/:scriptType',
    name: genericPanelRoute.script,
    component: genericEditor,
    props: { mode: 'script' },
    meta: { title: 'core.comp.editScript', scriptPage: 'script' },
  },
  {
    path: PAGE_ROUTES.userEdit.path('plugin/:scriptType'),
    name: genericPanelRoute.user,
    component: genericEditor,
    props: { mode: 'user' },
    meta: { title: 'core.comp.editUser', scriptPage: 'userEdit' },
  },
]

/** 静态入口和直达地址统一由路由守卫解析当前插件面板。 */
export function useScriptEditorNavigation() {
  const router = useRouter()
  return <K extends keyof ScriptEditorParams>(
    type: string,
    kind: K,
    params: ScriptEditorParams[K],
    state?: HistoryState
  ) => {
    if (kind === 'setup' && !isMaaFWFamily(type) && 'id' in params) {
      void router.push({
        name: 'GenericScriptSetup',
        params: { scriptId: params.id, scriptType: type },
      })
      return true
    }
    const custom = kind === 'setup' ? maafwRouteName(type, 'setup') : routeNameOf(type, kind)
    const generic =
      kind === 'script'
        ? genericPanelRoute.script
        : kind === 'userEdit' || kind === 'user'
          ? genericPanelRoute.user
          : kind === 'userAdd' && type === 'SRC'
            ? 'GenericUserAdd'
            : null
    if (custom !== generic && router.hasRoute(custom)) {
      void router.push({ name: custom, params, state })
      return true
    }
    if (!generic) return false
    const ids = 'id' in params ? { scriptId: params.id } : params
    void router.push({ name: generic, params: { ...ids, scriptType: type } })
    return true
  }
}

/** 只装配页面入口；专项运行、保存和引导仍由所属模块持有。 */
export const buildScriptEditorRoutes = (): RouteRecordRaw[] =>
  (Object.keys(EDITOR_PAGES) as OrdinaryScriptType[]).flatMap(type => {
    const metadata = SCRIPT_METADATA[type]
    const pages = EDITOR_PAGES[type]
    return (Object.keys(PAGE_ROUTES) as ScriptEditorKind[]).map(kind => ({
      path: PAGE_ROUTES[kind].path(metadata.routeSuffix),
      name: routeNameOf(type, kind),
      component: kind === 'script' ? pages.script : pages.user,
      meta: { title: metadata.routeTitles[kind], scriptType: type, scriptPage: kind },
    }))
  })
