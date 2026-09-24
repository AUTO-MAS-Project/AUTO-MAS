import type { RouteRecordRaw } from 'vue-router'
import type { MaaFWFlavor } from '@/composables/maafwFlavorTypes'

type LazyPage = Extract<RouteRecordRaw, { component: unknown }>['component']

/**
 * 特调没有专用页面：脚本页、用户页都与 MFW 同一个组件，flavor 以脚本当前类型为准，
 * meta.scriptType 只是登记。路由名与路径按注册表生成（<Type>ScriptEdit / <Type>UserAdd /
 * <Type>UserEdit，后缀取 routeSuffix），新增特调不用改路由表。
 */
export const buildMaaFWFlavorRoutes = (
  flavors: readonly MaaFWFlavor[],
  pages: { script: LazyPage; user: LazyPage }
) => ({
  scriptEdit: flavors.map((flavor): RouteRecordRaw => ({
    path: `/scripts/:id/edit/${flavor.routeSuffix}`,
    name: `${flavor.type}ScriptEdit`,
    component: pages.script,
    meta: { title: `编辑${flavor.typeTagLabel}脚本`, scriptType: flavor.type },
  })),
  userAdd: flavors.map((flavor): RouteRecordRaw => ({
    path: `/scripts/:scriptId/users/add/${flavor.routeSuffix}`,
    name: `${flavor.type}UserAdd`,
    component: pages.user,
    meta: { title: `添加${flavor.typeTagLabel}用户`, scriptType: flavor.type },
  })),
  userEdit: flavors.map((flavor): RouteRecordRaw => ({
    path: `/scripts/:scriptId/users/:userId/edit/${flavor.routeSuffix}`,
    name: `${flavor.type}UserEdit`,
    component: pages.user,
    meta: { title: `编辑${flavor.typeTagLabel}用户`, scriptType: flavor.type },
  })),
})
