import type { ScriptType } from '@/types/script'
import type { MaaFWFlavorType } from '@/composables/maafwFlavorTypes'
import { MAAFW_FLAVORS } from '@/composables/useMaaFWFlavor'
import { buildMaaFWRoutes } from '@/router/maafwFlavorRoutes'
import { indexScriptDescriptors, orderScriptDescriptors } from './assembly'
import type { ScriptDescriptor, ScriptPageKind, ScriptPageParams } from './contracts'
import { GENERAL_DESCRIPTOR } from './general'
import { MAA_DESCRIPTOR } from './maa'
import { SRC_DESCRIPTOR } from './src'
import { MAAEND_DESCRIPTOR } from './maaend'
import { OKWW_DESCRIPTOR } from './okww'
import { OKNTE_DESCRIPTOR } from './oknte'
import { HSR_DESCRIPTOR } from './hsr'
import { BETTERGI_DESCRIPTOR } from './bettergi'
import { ZZZOD_DESCRIPTOR } from './zzzod'
import { BAAH_DESCRIPTOR } from './baah'
import { WHIMBOX_DESCRIPTOR } from './whimbox'

// 普通专项完整覆盖非 MaaFW 类型；MaaFW 家族的覆盖由原 flavor 注册表负责。
const ordinaryDescriptors = {
  General: GENERAL_DESCRIPTOR,
  MAA: MAA_DESCRIPTOR,
  SRC: SRC_DESCRIPTOR,
  MaaEnd: MAAEND_DESCRIPTOR,
  Okww: OKWW_DESCRIPTOR,
  OkNte: OKNTE_DESCRIPTOR,
  HSR: HSR_DESCRIPTOR,
  BetterGI: BETTERGI_DESCRIPTOR,
  ZzzOd: ZZZOD_DESCRIPTOR,
  BAAH: BAAH_DESCRIPTOR,
  Whimbox: WHIMBOX_DESCRIPTOR,
} satisfies {
  [T in Exclude<ScriptType, MaaFWFlavorType>]: ScriptDescriptor<T>
}

const maaFWDescriptors = MAAFW_FLAVORS.map((flavor): ScriptDescriptor => {
  const routes = buildMaaFWRoutes(
    [flavor],
    () => import('@/views/EditView/MaaFWFlavor/MaaFWPageHost.vue')
  )
  return {
    type: flavor.type,
    configType: flavor.scriptConfigType,
    label: flavor.typeTagLabel,
    logo: flavor.logo,
    card: flavor.create.card,
    routes: {
      script: routes.script[0],
      userAdd: routes.userAdd[0],
      userEdit: routes.userEdit[0],
    },
    extraRoutes: routes.setup,
    flavor,
  }
})

export const SCRIPT_DESCRIPTORS: readonly ScriptDescriptor[] = orderScriptDescriptors([
  ...Object.values(ordinaryDescriptors),
  ...maaFWDescriptors,
])

const index = indexScriptDescriptors(SCRIPT_DESCRIPTORS)
export const SCRIPT_ROUTES = index.routes

/** 仅从已通过完整覆盖与冲突校验的登记表投影，调用者不能传入不完整集合。 */
export function projectScriptDescriptors<T>(select: (descriptor: ScriptDescriptor) => T) {
  return Object.fromEntries(
    SCRIPT_DESCRIPTORS.map(descriptor => [descriptor.type, select(descriptor)])
  ) as Record<ScriptType, T>
}

/** 已知类型不套默认身份；漏登记在完整覆盖检查和装配时暴露。 */
export function getScriptDescriptor(type: ScriptType): ScriptDescriptor {
  const descriptor = index.byType.get(type)
  if (!descriptor) throw new Error(`未登记脚本类型: ${type}`)
  return descriptor
}

export const findScriptDescriptorByConfigType = (configType: string) =>
  index.byConfigType.get(configType)

/** 后端配置类型未知时，保持 API 读取的 General 回退。分析分类可直接查询索引保留 unknown。 */
export const resolveScriptType = (configType: string): ScriptType =>
  findScriptDescriptorByConfigType(configType)?.type ?? 'General'

/** 点击时按最新脚本类型选入口，普通专项沿用路径传参，MaaFW 沿用命名路由传参。 */
export function scriptRouteLocation<K extends ScriptPageKind>(
  type: ScriptType,
  kind: K,
  params: ScriptPageParams[K]
): string | { name: string; params: ScriptPageParams[K] } {
  const descriptor = getScriptDescriptor(type)
  const route = descriptor.routes[kind]
  if (descriptor.flavor) return { name: route.name, params: { ...params } }
  return Object.entries(params).reduce(
    (path, [key, value]) => path.replace(`:${key}`, value),
    route.path
  )
}
