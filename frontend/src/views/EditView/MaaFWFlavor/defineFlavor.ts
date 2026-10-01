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
 * - `routes.titles` 可省，按 `typeTagLabel` 生成，写了的逐条覆盖；
 * - `scriptPage` / `userPage` 可省；其中 `text` / `managed` 按字段浅合并到 MaaFW 上：
 *   不写或写 `undefined` 沿用 MaaFW，写 `null` 表示明确关掉（只有可为空的字段能写 null）；
 * - `page` / `sections` / `slots` / `prepare`（含 `create.sections` / `create.slots`）不继承，
 *   不写就是没有。
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
  /** 路由后缀必须写；标题不写就按 typeTagLabel 生成（见 defaultMaaFWRouteTitles），写了的逐条覆盖 */
  routes: Pick<MaaFWFlavorRoutes, 'suffix'> & { titles?: Partial<MaaFWFlavorRoutes['titles']> }
  create: Pick<MaaFWFlavorCreate, 'card'> & {
    sections?: MaaFWFlavorCreate['sections']
    slots?: MaaFWFlavorCreate['slots']
  }
  scriptPage?: {
    text?: Partial<MaaFWScriptPageText>
    page?: MaaFWScriptPagePart['page']
    sections?: MaaFWScriptPagePart['sections']
    slots?: MaaFWScriptPagePart['slots']
    prepare?: MaaFWScriptPagePart['prepare']
  }
  userPage?: {
    text?: Partial<MaaFWUserPageText>
    managed?: Partial<MaaFWManagedTasks>
    page?: MaaFWUserPagePart['page']
    sections?: MaaFWUserPagePart['sections']
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

/** 按类型标签生成的四个路由标题（M9A：编辑M9A脚本 / M9A项目引导 / 添加M9A用户 / 编辑M9A用户） */
export const defaultMaaFWRouteTitles = (label: string): MaaFWFlavorRoutes['titles'] => ({
  script: `编辑${label}脚本`,
  setup: `${label}项目引导`,
  userAdd: `添加${label}用户`,
  userEdit: `编辑${label}用户`,
})

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
  routes: {
    suffix: spec.routes.suffix,
    // 标题不从底继承（底是 MaaFW 自己的标题），按本特调的标签生成
    titles: mergeDefined(defaultMaaFWRouteTitles(spec.typeTagLabel), spec.routes.titles),
  },
  create: {
    card: spec.create.card,
    sections: spec.create.sections ?? {},
    slots: spec.create.slots ?? {},
  },
  scriptPage: {
    text: mergeDefined(base.scriptPage.text, spec.scriptPage?.text),
    page: spec.scriptPage?.page ?? null,
    sections: spec.scriptPage?.sections ?? {},
    slots: spec.scriptPage?.slots ?? {},
    prepare: spec.scriptPage?.prepare ?? null,
  },
  userPage: {
    text: mergeDefined(base.userPage.text, spec.userPage?.text),
    managed: mergeDefined(base.userPage.managed, spec.userPage?.managed),
    page: spec.userPage?.page ?? null,
    sections: spec.userPage?.sections ?? {},
    slots: spec.userPage?.slots ?? {},
    prepare: spec.userPage?.prepare ?? null,
  },
})

/** 声明一个特调：只写与通用 MaaFW 不同的部分 */
export const defineMaaFWFlavor = (spec: MaaFWFlavorSpec): MaaFWFlavor =>
  mergeMaaFWFlavor(MAAFW_FLAVOR, spec)
