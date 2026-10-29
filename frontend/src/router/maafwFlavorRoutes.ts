import type {
  LocationQueryRaw,
  RouteLocationNormalizedLoaded,
  RouteParamsRaw,
  RouteRecordRaw,
  RouteRecordSingleView,
} from 'vue-router'
import type { MaaFWFlavor, MaaFWPageKind } from '@/composables/maafwFlavorTypes'
import { isMaaFWFamily, resolveMaaFWFlavor } from '@/composables/useMaaFWFlavor'
import type { ScriptType } from '@/types/script'
import { SCRIPT_PAGE_ROUTES } from '@/scriptDescriptors/contracts'

declare module 'vue-router' {
  interface RouteMeta {
    /** MaaFW 家族的路由：这条路由登记的特调类型。页面以脚本实际类型为准，它只用来纠正后缀写错的地址 */
    scriptType?: ScriptType
    /** MaaFW 家族的路由：页面种类 */
    maafwPage?: MaaFWPageKind
  }
}

type MaaFWRoute = RouteRecordSingleView & { name: string }

type LazyPage = Extract<RouteRecordRaw, { component: unknown }>['component']

/**
 * MaaFW 家族四种页面的路由名后缀与路径。路由名 = 类型 + 名字后缀（MaaFWScriptEdit、
 * M9ASetupWizard……），路径后缀取描述对象的 routes.suffix。生成路由与拼跳转目标共用这一张表。
 */
export const MAAFW_PAGE_KINDS = Object.keys(SCRIPT_PAGE_ROUTES) as MaaFWPageKind[]

/** 各页面种类的路由参数 */
export type MaaFWPageParams = {
  script: { id: string }
  setup: { id: string }
  userAdd: { scriptId: string }
  userEdit: { scriptId: string; userId: string }
}

const routeNameOf = (type: string, kind: MaaFWPageKind) => `${type}${SCRIPT_PAGE_ROUTES[kind].name}`

/** 某个类型某种页面的路由名；未知 / 非 MaaFW 家族类型按通用 MaaFW */
export const maafwRouteName = (
  type: ScriptType | string | null | undefined,
  kind: MaaFWPageKind
): string => routeNameOf(resolveMaaFWFlavor(type).type, kind)

/**
 * 跳到 MaaFW 家族页面的目标：`router.push(maafwRouteLocation(type, 'userAdd', { scriptId }))`。
 * 按脚本类型走它自己那条线；未知 / 非 MaaFW 家族类型按通用 MaaFW。
 */
export const maafwRouteLocation = <K extends MaaFWPageKind>(
  type: ScriptType | string | null | undefined,
  kind: K,
  params: MaaFWPageParams[K]
): { name: string; params: MaaFWPageParams[K] } => ({
  name: maafwRouteName(type, kind),
  params: { ...params },
})

/**
 * 路由登记的类型与脚本实际类型不符时（老链接、手输的地址、导入后换了类型），应该去的地址：
 * 同一种页面、实际类型那条线，参数、query、hash 照带。不用纠正（类型相符、不是 MaaFW 家族的
 * 路由或脚本）时返回 null。只有页面宿主调它（路由 meta.scriptType 只在这里读）。
 */
export const resolveMaaFWCanonicalLocation = (
  route: Pick<RouteLocationNormalizedLoaded, 'meta' | 'params' | 'query' | 'hash'>,
  actualType: ScriptType | string | null | undefined
): { name: string; params: RouteParamsRaw; query: LocationQueryRaw; hash: string } | null => {
  const kind = route.meta.maafwPage
  const routeType = route.meta.scriptType
  if (!kind || !routeType || !isMaaFWFamily(actualType) || actualType === routeType) return null
  return {
    name: maafwRouteName(actualType, kind),
    params: { ...route.params },
    query: { ...route.query },
    hash: route.hash,
  }
}

/**
 * MaaFW 与各特调的路由按注册表生成：每个类型四条（脚本编辑 / 引导 / 加用户 / 编辑用户），
 * 按页面种类分组返回，路由表在原来的位置展开。组件都是页面宿主（按脚本实际类型选页面），
 * meta 记下标题、登记的类型与页面种类。新增特调不用改路由表。
 */
export const buildMaaFWRoutes = (
  flavors: readonly MaaFWFlavor[],
  page: LazyPage
): Record<MaaFWPageKind, MaaFWRoute[]> =>
  Object.fromEntries(
    MAAFW_PAGE_KINDS.map(kind => [
      kind,
      flavors.map((flavor): MaaFWRoute => ({
        path: SCRIPT_PAGE_ROUTES[kind].path(flavor.routes.suffix),
        name: routeNameOf(flavor.type, kind),
        component: page,
        meta: { title: flavor.routes.titles[kind], scriptType: flavor.type, maafwPage: kind },
      })),
    ])
  ) as Record<MaaFWPageKind, MaaFWRoute[]>
