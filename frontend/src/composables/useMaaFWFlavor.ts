// MaaFW 特调注册表：MaaFW 与各特调（M9A / MSS ……）在前端的唯一事实来源。
//
// 特调是 MaaFW 引擎的一种「口味」：脚本页 / 用户页 / 脚本列表 / 新建流程都是 MaaFW 的公共组件，
// 特调之间的差别全部写在各自的描述对象里（身份、文案 key、独有区块、钩子），公共代码只按
// 描述对象的字段取值，不写 `type === 'XXX'` 这类分支。
// flavor 以脚本当前类型为准（导入后后端会按项目内容原地换类型），不以路由 meta 为准。
//
// ── 新增一个特调 X 需要做的事 ──────────────────────────────────────────────
// 1. 后端：配置类 XConfig(MaaFWConfig) / XUserConfig、app/task/X 的特调钩子、schema，
//    然后起开发后端重新生成 OpenAPI（frontend/src/api 不手改）。
// 2. 全应用的脚本类型登记（与任何新脚本类型相同，漏了 typecheck 会逐处报错）：
//    types/script.ts 的 ScriptType 与 ScriptIndexItem.type（配置类名，这处不受 typecheck 约束）、
//    utils/scriptLogos.ts 的图标与展示名、
//    composables/useScriptApi.ts 的 SCRIPT_CREATE_TYPE_BY_SCRIPT_TYPE、
//    词表 zh-CN.ts 的 scripts.type.X / scripts.create.typeDesc.X 与该特调自己的文案。
// 3. maafwFlavorTypes.ts 的 MaaFWFlavorType 加上 'X'。
// 4. 新建目录 views/EditView/MaaFWFlavor/x/：index.ts 导出描述对象 X_FLAVOR（字段见
//    MaaFWFlavor，全部必填）；独有区块写成本目录下的组件，用 defineMaaFWFlavorSlotComponent
//    声明到 slots 的插入点上（按需加载），需要预取数据就给 prepareUserPage。
// 5. 在下面的 FLAVOR_REGISTRY 里登记 X_FLAVOR（漏登记 typecheck 会报错）。
// 公共页面（MaaFW 脚本页 / 用户页、脚本列表、新建流程）与路由不用改：路由、类型卡片、
// 路由后缀、用户类型白名单、默认脚本名都从这里生成。只有需要一个现在没有的插入点时，
// 才在 MaaFWFlavorSlotContextMap 加名字、在公共页面对应位置放一个 <MaaFWFlavorSlot>。
// ──────────────────────────────────────────────────────────────────────────

import { computed, toValue, type MaybeRefOrGetter } from 'vue'
import type { ScriptType } from '@/types/script'
import { MAAFW_FLAVOR } from '@/views/EditView/MaaFWFlavor/maafw'
import { M9A_FLAVOR } from '@/views/EditView/MaaFWFlavor/m9a'
import { MSS_FLAVOR } from '@/views/EditView/MaaFWFlavor/mss'
import type {
  MaaFWFlavor,
  MaaFWFlavorSlotComponent,
  MaaFWFlavorSlotName,
  MaaFWFlavorType,
} from './maafwFlavorTypes'

export type {
  MaaFWFlavor,
  MaaFWFlavorSlotName,
  MaaFWFlavorType,
  MaaFWUserSlotContext,
} from './maafwFlavorTypes'

// 按类型登记：MaaFWFlavorType 加了新成员却没在这里登记时 typecheck 直接报错
const FLAVOR_REGISTRY = {
  MaaFW: MAAFW_FLAVOR,
  M9A: M9A_FLAVOR,
  MSS: MSS_FLAVOR,
} satisfies Record<MaaFWFlavorType, MaaFWFlavor>

/** 全部 MaaFW 类型，MaaFW 本身在第一个（未知类型的兜底） */
export const MAAFW_FLAVORS: readonly MaaFWFlavor[] = Object.values(FLAVOR_REGISTRY)

/** 只有特调（不含 MaaFW 本身）：路由按它们生成，MaaFW 自己的几条路由（含引导页）手写在路由表里 */
export const MAAFW_SPECIAL_FLAVORS: readonly MaaFWFlavor[] = MAAFW_FLAVORS.filter(
  flavor => flavor !== MAAFW_FLAVOR
)

const FLAVOR_BY_TYPE = new Map<string, MaaFWFlavor>(
  MAAFW_FLAVORS.map(flavor => [flavor.type, flavor])
)
const USER_CONFIG_TYPES: ReadonlySet<string> = new Set(
  MAAFW_FLAVORS.map(flavor => flavor.userConfigType)
)
const DEFAULT_SCRIPT_NAMES: ReadonlySet<string> = new Set(
  MAAFW_FLAVORS.map(flavor => flavor.defaultScriptName)
)

/** 是否由 MaaFW 引擎运行（MaaFW 本身或它的特调） */
export const isMaaFWFamily = (
  type: ScriptType | string | null | undefined
): type is MaaFWFlavorType => Boolean(type) && FLAVOR_BY_TYPE.has(type as string)

/** 按脚本类型取 flavor 表；未知 / 空类型按通用 MaaFW 处理。 */
export const resolveMaaFWFlavor = (type: ScriptType | string | null | undefined): MaaFWFlavor =>
  (type && FLAVOR_BY_TYPE.get(type)) || MAAFW_FLAVOR

/** 路由后缀（/edit/<suffix>、/users/add/<suffix>），未知类型按 maafw */
export const maafwRouteSuffix = (type: ScriptType | string | null | undefined): string =>
  resolveMaaFWFlavor(type).routeSuffix

/** MaaFW 家族的后端用户配置类名（M9A / MSS 的用户类都是 MaaFWUserConfig 的子类） */
export const maafwUserConfigTypes = (): ReadonlySet<string> => USER_CONFIG_TYPES

/** 后端脚本配置类名 → 脚本类型（脚本详情里只有配置类名） */
export const maafwScriptTypeByConfigType = (): Record<string, MaaFWFlavorType> =>
  Object.fromEntries(MAAFW_FLAVORS.map(flavor => [flavor.scriptConfigType, flavor.type]))

/** 后端给新建脚本起的默认名：脚本名还是其中之一时，读到 interface 后改成项目名 */
export const maafwDefaultScriptNames = (): ReadonlySet<string> => DEFAULT_SCRIPT_NAMES

/** 某个插入点上当前 flavor 要渲染的组件（没有就是空数组） */
export const resolveMaaFWFlavorSlot = (
  flavor: MaaFWFlavor,
  name: MaaFWFlavorSlotName
): readonly MaaFWFlavorSlotComponent[] => flavor.slots[name] ?? []

/**
 * 用户页加载期间调用：预取该 flavor 插入点组件的 chunk、跑它的 prepareUserPage。
 * 预取过的异步组件在首次渲染时同一轮微任务内就能解析，不会先空一下再冒出来。
 * 失败只影响独有区块自己（组件渲染时会再加载一次），不拖垮页面加载。
 */
export const prepareMaaFWFlavorUserPage = async (flavor: MaaFWFlavor): Promise<void> => {
  const loads = Object.values(flavor.slots).flatMap(entries =>
    (entries ?? []).map(entry => entry.load())
  )
  await Promise.allSettled([...loads, flavor.prepareUserPage?.()])
}

/** 响应式版本：类型变了（导入后后端按项目换了类型）文案跟着变。 */
export const useMaaFWFlavor = (type: MaybeRefOrGetter<ScriptType | string | null | undefined>) =>
  computed(() => resolveMaaFWFlavor(toValue(type)))
