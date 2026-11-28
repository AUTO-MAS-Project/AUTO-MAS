import {
  useRouter,
  type HistoryState,
  type RouteLocationNormalized,
  type Router,
  type RouteRecordRaw,
} from 'vue-router'
import { getPluginRegistry } from '@/composables/usePluginScriptTypes'
import { compatibleWheel, indexPluginScriptTypes } from '@/utils/pluginScriptTypes'
import { isMaaFWFamily } from '@/plugins/maafwFamily'
import {
  PLUGIN_EDITOR_SCRIPT_TYPES,
  type BuiltinScriptType,
  type PluginEditorScriptType,
} from '@/types/script'
import { SCRIPT_METADATA } from '@/utils/scriptMetadata'

type OrdinaryScriptType = Exclude<BuiltinScriptType, PluginEditorScriptType>
type LazyPage = Extract<RouteRecordRaw, { component: unknown }>['component']

const EDITOR_PAGES: Record<string, { script: LazyPage; user: LazyPage }> = {
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

export async function resolveScriptPanelRoute(
  to: RouteLocationNormalized,
  router: Router,
  type: string
) {
  const page = to.meta.scriptPage
  if (!page || page === 'setup') return
  const kind = page === 'script' ? 'script' : 'user'
  const custom = routeNameOf(type, page)
  const generic = page === 'userAdd' ? 'GenericUserAdd' : genericPanelRoute[kind]
  if (!router.hasRoute(custom)) return
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
    scriptType?: string
    scriptPage?: ScriptEditorKind | 'setup'
  }
}

const genericEditor = () => import('@/views/plugins/ConfigEditor.vue')

export const pluginEditorRedirects: RouteRecordRaw[] = [
  ...PLUGIN_EDITOR_SCRIPT_TYPES.flatMap<RouteRecordRaw>(scriptType => [
    {
      path: PAGE_ROUTES.script.path(SCRIPT_METADATA[scriptType].routeSuffix),
      redirect: to => ({
        name: genericPanelRoute.script,
        params: { scriptId: to.params.id, scriptType },
      }),
    },
    {
      path: PAGE_ROUTES.userAdd.path(SCRIPT_METADATA[scriptType].routeSuffix),
      redirect: to => ({
        name: 'GenericUserAdd',
        params: { scriptId: to.params.scriptId, scriptType },
      }),
    },
    {
      path: PAGE_ROUTES.userEdit.path(SCRIPT_METADATA[scriptType].routeSuffix),
      redirect: to => ({
        name: genericPanelRoute.user,
        params: { scriptId: to.params.scriptId, userId: to.params.userId, scriptType },
      }),
    },
  ]),
  ...PLUGIN_EDITOR_SCRIPT_TYPES.filter(isMaaFWFamily).map<RouteRecordRaw>(scriptType => ({
    path: '/scripts/:id/setup/' + SCRIPT_METADATA[scriptType].routeSuffix,
    redirect: to => ({
      name: genericPanelRoute.setup,
      params: { scriptId: to.params.id, scriptType },
    }),
  })),
  {
    path: '/scripts/:scriptId/users/:userId/cultivate/maa',
    redirect: to => ({
      name: genericPanelRoute.user,
      params: { scriptId: to.params.scriptId, userId: to.params.userId, scriptType: 'MAA' },
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
    meta: { title: 'core.comp.editScript', scriptPage: 'setup' },
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
    const custom = kind === 'setup' ? undefined : routeNameOf(type, kind)
    const generic =
      kind === 'setup'
        ? genericPanelRoute.setup
        : kind === 'script'
          ? genericPanelRoute.script
          : kind === 'userEdit' || kind === 'user'
            ? genericPanelRoute.user
            : PLUGIN_EDITOR_SCRIPT_TYPES.some(scriptType => scriptType === type)
              ? 'GenericUserAdd'
              : null
    if (custom && router.hasRoute(custom)) {
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
