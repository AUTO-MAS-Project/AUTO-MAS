import type { ScriptIndexItem } from '@/api'
import type { ScriptType } from '@/types/script'
import type { MaaFWFlavor } from '@/composables/maafwFlavorTypes'
import type { RouteRecordSingleView } from 'vue-router'

export type ScriptConfigType = `${ScriptIndexItem['type']}`
export type ScriptPageKind = 'script' | 'userAdd' | 'userEdit'
export type ScriptRoute = RouteRecordSingleView & { name: string }

/** 生成入口和构造跳转共用路径形状，MaaFW 的 setup 也沿用同一组规则。 */
export const SCRIPT_PAGE_ROUTES = {
  script: { name: 'ScriptEdit', path: (suffix: string) => `/scripts/:id/edit/${suffix}` },
  setup: { name: 'SetupWizard', path: (suffix: string) => `/scripts/:id/setup/${suffix}` },
  userAdd: { name: 'UserAdd', path: (suffix: string) => `/scripts/:scriptId/users/add/${suffix}` },
  userEdit: {
    name: 'UserEdit',
    path: (suffix: string) => `/scripts/:scriptId/users/:userId/edit/${suffix}`,
  },
}

export type ScriptCreateCard = {
  titleKey: string
  descriptionKey: string
  keywords: string[]
  group: 'specialized' | 'general'
} & (
  | { order: number; after?: never }
  /** 沿用 flavor 的插入规则：排在指定类型后面；null 排到最后。 */
  | { after: ScriptType | null; order?: never }
)

/** 只声明身份与入口；页面、创建流程、保存和会话仍由原模块负责。 */
export interface ScriptDescriptor<T extends ScriptType = ScriptType> {
  type: T
  configType: ScriptConfigType
  label: string
  logo: string
  card: ScriptCreateCard
  routes: Record<ScriptPageKind, ScriptRoute>
  extraRoutes: ScriptRoute[]
  /** 保留原 flavor 引用，不能用投影副本参与对象身份判断。 */
  flavor?: MaaFWFlavor
}

export type ScriptPageParams = {
  script: { id: string }
  userAdd: { scriptId: string }
  userEdit: { scriptId: string; userId: string }
}

export interface ScriptDescriptorSpec<T extends ScriptType> extends Omit<
  ScriptDescriptor<T>,
  'routes' | 'extraRoutes' | 'flavor'
> {
  routes: {
    suffix: string
    titles: Record<ScriptPageKind, string>
    script: NonNullable<ScriptRoute['component']>
    user: NonNullable<ScriptRoute['component']>
  }
  extraRoutes?: ScriptRoute[]
}

/** 普通专项共用路径形状，懒加载函数由专项静态声明，Vite 可以分析。 */
export function defineScriptDescriptor<T extends ScriptType>(
  spec: ScriptDescriptorSpec<T>
): ScriptDescriptor<T> {
  const { routes, extraRoutes = [], ...identity } = spec
  return {
    ...identity,
    routes: {
      script: {
        path: SCRIPT_PAGE_ROUTES.script.path(routes.suffix),
        name: `${spec.type}${SCRIPT_PAGE_ROUTES.script.name}`,
        component: routes.script,
        meta: { title: routes.titles.script },
      },
      userAdd: {
        path: SCRIPT_PAGE_ROUTES.userAdd.path(routes.suffix),
        name: `${spec.type}${SCRIPT_PAGE_ROUTES.userAdd.name}`,
        component: routes.user,
        meta: { title: routes.titles.userAdd },
      },
      userEdit: {
        path: SCRIPT_PAGE_ROUTES.userEdit.path(routes.suffix),
        name: `${spec.type}${SCRIPT_PAGE_ROUTES.userEdit.name}`,
        component: routes.user,
        meta: { title: routes.titles.userEdit },
      },
    },
    extraRoutes,
  }
}
