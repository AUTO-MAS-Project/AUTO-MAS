import type { RouteRecordRaw } from 'vue-router'
import type { MaaFWFlavorType } from '@/composables/maafwFlavorTypes'
import type { ScriptType } from '@/types/script'
import { SCRIPT_METADATA } from '@/utils/scriptMetadata'

type OrdinaryScriptType = Exclude<ScriptType, MaaFWFlavorType>
type LazyPage = Extract<RouteRecordRaw, { component: unknown }>['component']

const EDITOR_PAGES = {
  MAA: {
    script: () => import('@/views/EditView/Script/MAAScriptEdit.vue'),
    user: () => import('@/views/EditView/User/MAAUserEdit.vue'),
  },
  SRC: {
    script: () => import('@/views/EditView/Script/SRCScriptEdit.vue'),
    user: () => import('@/views/EditView/User/SRCUserEdit.vue'),
  },
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
  BetterGI: {
    script: () => import('@/views/EditView/Script/BetterGIScriptEdit.vue'),
    user: () => import('@/views/EditView/User/BetterGIUserEdit.vue'),
  },
  ZzzOd: {
    script: () => import('@/views/EditView/Script/ZzzOdScriptEdit.vue'),
    user: () => import('@/views/EditView/User/ZzzOdUserEdit.vue'),
  },
  Whimbox: {
    script: () => import('@/views/EditView/Script/WhimboxScriptEdit.vue'),
    user: () => import('@/views/EditView/User/WhimboxUserEdit.vue'),
  },
} satisfies Record<OrdinaryScriptType, { script: LazyPage; user: LazyPage }>

const PAGE_ROUTES = {
  script: { name: 'ScriptEdit', path: (suffix: string) => `/scripts/:id/edit/${suffix}` },
  userAdd: { name: 'UserAdd', path: (suffix: string) => `/scripts/:scriptId/users/add/${suffix}` },
  userEdit: {
    name: 'UserEdit',
    path: (suffix: string) => `/scripts/:scriptId/users/:userId/edit/${suffix}`,
  },
}

export type ScriptEditorKind = keyof typeof PAGE_ROUTES
const routeNameOf = (type: ScriptType, kind: ScriptEditorKind) => `${type}${PAGE_ROUTES[kind].name}`
type ScriptEditorParams = {
  script: { id: string }
  userAdd: { scriptId: string }
  userEdit: { scriptId: string; userId: string }
}

declare module 'vue-router' {
  interface RouteMeta {
    /** 普通专项页面种类；MFW 保留自身的引导和 canonical 路由契约。 */
    scriptPage?: ScriptEditorKind
  }
}

/** 普通专项与 MFW 共用已有的路由名，跳转无需再维护类型分支。 */
export const scriptEditorLocation = <K extends ScriptEditorKind>(
  type: ScriptType,
  kind: K,
  params: ScriptEditorParams[K]
): { name: string; params: ScriptEditorParams[K] } => ({
  name: routeNameOf(type, kind),
  params: { ...params },
})

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

/** 养成是 MAA 独有入口，保持独立登记和既有页面参数。 */
export const MAA_CULTIVATE_ROUTE: RouteRecordRaw = {
  path: '/scripts/:scriptId/users/:userId/cultivate/maa',
  name: 'MAACultivate',
  component: () => import('@/views/EditView/User/MAAUserEdit.vue'),
  props: { cultivationPage: true },
  meta: { title: 'MAA 干员养成' },
}
