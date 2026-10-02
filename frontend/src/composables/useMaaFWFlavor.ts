// MaaFW 特调注册表：MaaFW 与各特调在前端的唯一事实来源。
//
// MaaFW 提供四个部分的默认实现：脚本页、用户页、新建流程、路由。特调是 MaaFW 引擎的一种「口味」，
// 与 MaaFW 的差别全部写在自己的描述对象里，公共代码只按描述对象的字段取值，不写
// `type === 'XXX'` 这类分支。flavor 以脚本实际类型为准（导入后后端会按项目内容原地换类型），
// 不以路由为准；新建流程按选中的类型卡片取。
//
// ── 定制的三种方式（由浅到深，能用浅的就别用深的） ─────────────────────────────
// 1. 身份与差异：defineMaaFWFlavor（MaaFWFlavor/defineFlavor.ts）只写与 MaaFW 不同的部分——
//    身份、路由后缀、新建卡片必写；scriptPage.text / userPage.text / userPage.managed 按字段
//    浅合并（不写沿用 MaaFW，写 null 关掉）。
// 2. 分节级：
//    - 替换分节：defineMaaFWSection(part, key, load) 写进 scriptPage / userPage / create 的
//      sections。替换组件必须接得住 MFW 该分节的契约（MaaFWFlavor/sectionContracts.ts，不接住
//      typecheck 报错），只有这个特调用到时才加载。事件不在类型检查之内：替换组件要照
//      defineEmits<该分节的 …Emits>() 把 change / save 等事件发出来（或把 $attrs 透传给它包的 MFW
//      分节），否则改动不会落盘。
//    - 插入点：defineMaaFWLazyComponent 写进 slots，组件以 `context` 一个 prop 接收上下文。
//      scriptPage：afterBasicInfo / beforeControl / besidePackageName（control 分节内、与游戏包名
//      并排）/ afterControl / afterUpdate / afterRun
//      userPage：afterBasicInfo / beforeTaskQueue / afterTaskQueue
//      create：afterSourceStep（只读）
//    - 预取数据：scriptPage.prepare / userPage.prepare（页面加载期间调用；新建流程没有）。
// 3. 页面级：scriptPage.page / userPage.page 整页替换，用 MFW 的公共件拼——
//    views/EditView/Script/MaaFWScriptEdit/pageKit.ts、views/EditView/User/MaaFWUserEdit/pageKit.ts
//    导出分节、分节契约与编排层（useMaaFWScriptPage / useMaaFWUserPage），不必复制 MFW 页面。
//    这两个文件刻意不叫 index.ts：vite 解析扩展名时 .vue 排在目录之前，按目录名引入会拿到
//    同名的 MaaFWScriptEdit.vue / MaaFWUserEdit.vue 页面本身（typecheck 却照样通过）。
// 路由不用改：router/maafwFlavorRoutes.ts 按注册表给每个类型生成四条路由；页面宿主
// （MaaFWFlavor/MaaFWPageHost.vue）按脚本实际类型选页面，地址后缀写错的纠正到实际类型那条。
// 需要一个现在没有的插入点：在 maafwFlavorTypes.ts 的 MaaFWFlavorSlotContextMap 对应部分下加
// 名字，在公共页面对应位置放一个 <MaaFWFlavorSlot>——不要在公共页面里按类型分支。
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
// 4. 新建目录 views/EditView/MaaFWFlavor/x/：index.ts 用 defineMaaFWFlavor 导出描述对象
//    X_FLAVOR，按上面三种方式写差异；独有组件都放在本目录。
// 5. 在下面的 FLAVOR_REGISTRY 里登记 X_FLAVOR（漏登记 typecheck 会报错）。
// 公共页面（MaaFW 脚本页 / 用户页、脚本列表、新建流程）与路由不用改：路由、类型卡片、
// 路由后缀、用户类型白名单、默认脚本名都从这里生成。
// ──────────────────────────────────────────────────────────────────────────

import { computed, toValue, type Component, type ComputedRef, type MaybeRefOrGetter } from 'vue'
import type { ScriptType } from '@/types/script'
import { MAAFW_FLAVOR } from '@/views/EditView/MaaFWFlavor/maafw'
import { M9A_FLAVOR } from '@/views/EditView/MaaFWFlavor/m9a'
import { MSS_FLAVOR } from '@/views/EditView/MaaFWFlavor/mss'
import type {
  MaaFWFlavor,
  MaaFWFlavorPart,
  MaaFWFlavorPrepare,
  MaaFWFlavorSlotName,
  MaaFWFlavorType,
  MaaFWLazyComponent,
  MaaFWSectionKey,
} from './maafwFlavorTypes'

export type {
  MaaFWCreateSlotContext,
  MaaFWFlavor,
  MaaFWFlavorPart,
  MaaFWFlavorSlotName,
  MaaFWFlavorType,
  MaaFWScriptSlotContext,
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

/** 只有特调（不含 MaaFW 本身） */
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
  resolveMaaFWFlavor(type).routes.suffix

/** MaaFW 家族的后端用户配置类名（M9A / MSS 的用户类都是 MaaFWUserConfig 的子类） */
export const maafwUserConfigTypes = (): ReadonlySet<string> => USER_CONFIG_TYPES

/** 后端脚本配置类名 → 脚本类型（脚本详情里只有配置类名） */
export const maafwScriptTypeByConfigType = (): Record<string, MaaFWFlavorType> =>
  Object.fromEntries(MAAFW_FLAVORS.map(flavor => [flavor.scriptConfigType, flavor.type]))

/** 后端给新建脚本起的默认名：脚本名还是其中之一时，读到 interface 后改成项目名 */
export const maafwDefaultScriptNames = (): ReadonlySet<string> => DEFAULT_SCRIPT_NAMES

/** 某一页某个插入点上当前 flavor 要渲染的组件（没有就是空数组） */
export const resolveMaaFWFlavorSlot = <P extends MaaFWFlavorPart>(
  flavor: MaaFWFlavor,
  part: P,
  name: MaaFWFlavorSlotName<P>
): readonly MaaFWLazyComponent[] =>
  (flavor[part].slots as Partial<Record<string, readonly MaaFWLazyComponent[]>>)[name] ?? []

/**
 * 页面加载期间调用：预取该 flavor 在这一部分的整页、替换分节与插入点组件的 chunk、跑这一部分的
 * prepare（新建流程没有整页与 prepare，只预取分节与插入点，在进入「项目从哪来」一步时调用）。
 * 预取过的异步组件在首次渲染时同一轮微任务内就能解析，不会先空一下再冒出来。
 * 全部并行、用 allSettled 收：失败只影响独有区块自己（组件渲染时会再加载一次），
 * 不拖垮页面加载，也从不往外抛（同步抛出的也收住）。
 */
export const prepareMaaFWFlavorPage = async (
  flavor: MaaFWFlavor,
  part: MaaFWFlavorPart
): Promise<void> => {
  const page: {
    page?: MaaFWLazyComponent | null
    sections: object
    slots: object
    prepare?: MaaFWFlavorPrepare
  } = flavor[part]
  const lazy: MaaFWLazyComponent[] = [
    page.page ?? undefined,
    ...Object.values(page.sections as Record<string, MaaFWLazyComponent | undefined>),
    ...Object.values(
      page.slots as Record<string, readonly MaaFWLazyComponent[] | undefined>
    ).flat(),
  ].filter((entry): entry is MaaFWLazyComponent => Boolean(entry))
  const settle = (run: () => unknown) => (async () => run())()
  await Promise.allSettled([
    ...lazy.map(entry => settle(() => entry.load())),
    settle(() => page.prepare?.()),
  ])
}

/**
 * 某一页实际渲染的分节表：MFW 默认分节（页面模块里静态引入，通用 MFW 打开不闪）叠上当前
 * flavor 的替换分节。返回类型与默认表相同：替换分节由 defineMaaFWSection 保证接得住同一组 props，
 * 页面模板照常按默认分节的类型检查绑定。flavor 变了（导入后换类型）跟着变。
 */
export const useMaaFWSections = <
  P extends MaaFWFlavorPart,
  D extends Record<MaaFWSectionKey<P>, Component>,
>(
  flavor: MaybeRefOrGetter<MaaFWFlavor>,
  part: P,
  defaults: D
): ComputedRef<D> =>
  computed(() => {
    const overrides = toValue(flavor)[part].sections as Record<
      string,
      MaaFWLazyComponent | undefined
    >
    const merged: Record<string, Component> = { ...defaults }
    for (const [key, section] of Object.entries(overrides)) {
      if (section) merged[key] = section.component
    }
    return merged as D
  })

/** 响应式版本：类型变了（导入后后端按项目换了类型）文案跟着变。 */
export const useMaaFWFlavor = (type: MaybeRefOrGetter<ScriptType | string | null | undefined>) =>
  computed(() => resolveMaaFWFlavor(toValue(type)))
