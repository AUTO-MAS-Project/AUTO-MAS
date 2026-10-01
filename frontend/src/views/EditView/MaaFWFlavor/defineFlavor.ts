// 特调描述对象的声明工具：特调只写与通用 MaaFW 不同的部分，其余沿用 MAAFW_FLAVOR。
// maafw/index.ts 自己是完整的默认值，不经过这里（否则成环）。
import type {
  MaaFWFlavor,
  MaaFWFlavorCreate,
  MaaFWFlavorRoutes,
  MaaFWManagedTasks,
  MaaFWScriptPagePart,
  MaaFWScriptPageText,
  MaaFWUserPagePart,
  MaaFWUserPageText,
} from '@/composables/maafwFlavorTypes'
import { MAAFW_FLAVOR } from './maafw'

/**
 * 特调的声明：
 * - 身份、`routes.suffix`、`create.card` 必须写，不继承；
 * - `scriptPage` / `userPage` 可省；其中 `text` / `managed` 按字段浅合并到 MaaFW 上：
 *   不写或写 `undefined` 沿用 MaaFW，写 `null` 表示明确关掉（只有可为空的字段能写 null）；
 * - `slots` / `prepare` 不继承，不写就是没有。
 */
export interface MaaFWFlavorSpec extends Pick<
  MaaFWFlavor,
  | 'type'
  | 'scriptConfigType'
  | 'userConfigType'
  | 'defaultScriptName'
  | 'typeTagLabel'
  | 'typeTagColor'
  | 'logo'
  | 'docUrl'
> {
  routes: MaaFWFlavorRoutes
  create: MaaFWFlavorCreate
  scriptPage?: {
    text?: Partial<MaaFWScriptPageText>
    slots?: MaaFWScriptPagePart['slots']
    prepare?: MaaFWScriptPagePart['prepare']
  }
  userPage?: {
    text?: Partial<MaaFWUserPageText>
    managed?: Partial<MaaFWManagedTasks>
    slots?: MaaFWUserPagePart['slots']
    prepare?: MaaFWUserPagePart['prepare']
  }
}

/** 浅合并：override 里值为 undefined 的键不覆盖 base（null 照常覆盖） */
const mergeDefined = <T extends object>(base: T, override: Partial<T> | undefined): T => {
  const merged = { ...base }
  for (const [key, value] of Object.entries(override ?? {})) {
    if (value !== undefined) (merged as Record<string, unknown>)[key] = value
  }
  return merged
}

/** 把特调的差异合并到 base 上，得到字段齐全的描述对象。base 一般是 MAAFW_FLAVOR（测试可换） */
export const mergeMaaFWFlavor = (base: MaaFWFlavor, spec: MaaFWFlavorSpec): MaaFWFlavor => ({
  type: spec.type,
  scriptConfigType: spec.scriptConfigType,
  userConfigType: spec.userConfigType,
  defaultScriptName: spec.defaultScriptName,
  typeTagLabel: spec.typeTagLabel,
  typeTagColor: spec.typeTagColor,
  logo: spec.logo,
  docUrl: spec.docUrl,
  routes: { suffix: spec.routes.suffix },
  create: { card: spec.create.card },
  scriptPage: {
    text: mergeDefined(base.scriptPage.text, spec.scriptPage?.text),
    slots: spec.scriptPage?.slots ?? {},
    prepare: spec.scriptPage?.prepare ?? null,
  },
  userPage: {
    text: mergeDefined(base.userPage.text, spec.userPage?.text),
    managed: mergeDefined(base.userPage.managed, spec.userPage?.managed),
    slots: spec.userPage?.slots ?? {},
    prepare: spec.userPage?.prepare ?? null,
  },
})

/** 声明一个特调：只写与通用 MaaFW 不同的部分 */
export const defineMaaFWFlavor = (spec: MaaFWFlavorSpec): MaaFWFlavor =>
  mergeMaaFWFlavor(MAAFW_FLAVOR, spec)
