import { useRouter, type HistoryState, type RouteRecordRaw } from 'vue-router'
import { maafwRouteName } from './maafwRoutes'
import type { BuiltinScriptType } from '@/types/script'
import { SCRIPT_PLUGIN_EDITORS, type MaaFWFamilyType } from '@/plugins/scriptAdapters'
import { SCRIPT_METADATA } from '@/utils/scriptMetadata'

type OrdinaryScriptType = Exclude<BuiltinScriptType, MaaFWFamilyType>
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

export const genericEditorRoutes: RouteRecordRaw[] = [
  {
    path: '/scripts/:scriptId/edit/plugin/:scriptType',
    name: 'GenericScriptEdit',
    component: genericEditor,
    props: { mode: 'script' },
    meta: { title: 'core.comp.editScript', scriptPage: 'script' },
  },
  {
    path: PAGE_ROUTES.userEdit.path('plugin/:scriptType'),
    name: 'GenericUserEdit',
    component: genericEditor,
    props: { mode: 'user' },
    meta: { title: 'core.comp.editUser', scriptPage: 'userEdit' },
  },
]

/** 优先进入已注册的专用页面，运行时专项从详情接口读取表单。 */
export function useScriptEditorNavigation() {
  const router = useRouter()
  return <K extends keyof ScriptEditorParams>(
    type: string,
    kind: K,
    params: ScriptEditorParams[K],
    state?: HistoryState
  ) => {
    const custom = kind === 'setup' ? maafwRouteName(type, 'setup') : routeNameOf(type, kind)
    const generic =
      kind === 'script'
        ? 'GenericScriptEdit'
        : kind === 'userEdit' || kind === 'user'
          ? 'GenericUserEdit'
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
