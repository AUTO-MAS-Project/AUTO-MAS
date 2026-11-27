import type { ShareTemplateItem } from '@/composables/useTemplateApi'
import type { MaaFWEmbeddedSourceItem } from '@/api'
import { isMaaFWFamily, type MaaFWFamilyType } from '@/plugins/maafwFamily'
import type { ScriptType } from '@/types/script'
import type { PluginScriptTypes } from '@/utils/pluginScriptTypes'
import { isBuiltinScriptType, SCRIPT_METADATA } from '@/utils/scriptMetadata'

export type ConfigMode = 'template' | 'custom'
/** MFW 家族新建时项目从哪来：进引导页选目录导入，还是直接复用已有脚本的副本 */
export type MfwSourceMode = 'new' | 'reuse'
export type CreateStepKey = 'type' | 'config'

/** 由 MaaFW 引擎运行的类型（看适配条目上的家族标记，类型最终由项目决定） */
export type MfwFamilyType = MaaFWFamilyType
export const isMfwFamily = (type: ScriptType): type is MfwFamilyType => isMaaFWFamily(type)
type ScriptTypeGroup = 'all' | 'specialized' | 'general'

export interface ScriptTypeOption {
  value: ScriptType
  title: string
  description: string
  /** 搜索别名。刻意保留中文：译成英文中文用户就搜不到了，英文用户用 latin 别名一样能命中 */
  keywords: string[]
  group: Exclude<ScriptTypeGroup, 'all'>
  icon: string
}

export interface TemplateRequest {
  page: number
  keyword: string
}

interface CreateStep {
  key: CreateStepKey
  titleKey: string
}

interface CreateRequestState {
  type: ScriptType
  configMode: ConfigMode
  template: ShareTemplateItem | null
  mfwSourceMode?: MfwSourceMode
  mfwSourceScriptId?: string | null
}

export type ScriptCreateRequest =
  | { kind: 'new'; type: ScriptType }
  /** 同一个 MFW 项目再建一个脚本：建好后从 sourceScriptId 的副本克隆，不再选目录 */
  | { kind: 'mfw-reuse'; type: MfwFamilyType; sourceScriptId: string }
  | { kind: 'general-custom' }
  | { kind: 'general-template'; template: ShareTemplateItem }

// 全部类型（含 MaaFW 家族）按各自 metadata.createOrder 排
const builtinOptions = Object.entries(SCRIPT_METADATA).sort(
  ([, left], [, right]) => left.createOrder - right.createOrder
)

export function getScriptTypeOptions(
  enabled: readonly string[],
  plugins: PluginScriptTypes,
  t: (key: string) => string
): ScriptTypeOption[] {
  const options = builtinOptions.flatMap(([value, { create, logo }]) =>
    enabled.includes(value)
      ? [
          {
            value,
            title: t(create.titleKey),
            description: t(create.descriptionKey),
            keywords: create.keywords,
            group: create.group,
            icon: logo,
          },
        ]
      : []
  )
  for (const { scriptKey, displayName, description } of plugins.byScriptKey.values()) {
    if (isBuiltinScriptType(scriptKey) || !enabled.includes(scriptKey)) continue
    options.push({
      value: scriptKey,
      title: displayName,
      description,
      keywords: [scriptKey],
      group: 'specialized',
      icon: SCRIPT_METADATA.General.logo,
    })
  }
  return options
}

/** 第二步列表里的一行「已导入的项目」：同一项目开了几个脚本只列一行，克隆源取其中一个 */
export interface MfwReuseChoice {
  /** 克隆源脚本：同一项目有多个脚本时优先没在跑的那个 */
  scriptId: string
  scriptName: string
  projectName: string
  version: string
  /** 所有持有该项目的脚本都在跑，此刻不能克隆 */
  busy: boolean
  /** 持有该项目的脚本数 */
  scriptCount: number
}

/**
 * 把后端给的「有副本的脚本」按项目归成可复用的选项：
 * - 只留与新建入口同类型的（选了 M9A 入口就只能复用 M9A 项目，通用 MaaFW 入口同理）；
 * - 同名同版本的项目并成一行，克隆源优先取没在跑的脚本；读不出项目名的按脚本单列。
 */
export const buildMfwReuseChoices = (
  items: readonly MaaFWEmbeddedSourceItem[],
  type: ScriptType
): MfwReuseChoice[] => {
  const byProject = new Map<string, MfwReuseChoice>()
  for (const item of items) {
    if (item.type !== type) continue
    const projectName = (item.projectName || '').trim()
    const version = (item.version || '').trim()
    const key = projectName
      ? `project:${JSON.stringify([projectName.toLowerCase(), version.toLowerCase()])}`
      : `script:${item.scriptId}`
    const existing = byProject.get(key)
    if (!existing) {
      byProject.set(key, {
        scriptId: item.scriptId,
        scriptName: item.name || '',
        projectName,
        version,
        busy: Boolean(item.busy),
        scriptCount: 1,
      })
      continue
    }
    existing.scriptCount += 1
    if (existing.busy && !item.busy) {
      existing.scriptId = item.scriptId
      existing.scriptName = item.name || ''
      existing.busy = false
    }
  }
  return [...byProject.values()]
}

export const buildCreateSteps = ({ type }: Pick<CreateRequestState, 'type'>): CreateStep[] => {
  const steps: CreateStep[] = [{ key: 'type', titleKey: 'core.scripts.create.step.type' }]
  if (type === 'General') {
    steps.push({ key: 'config', titleKey: 'core.scripts.create.step.config' })
  } else if (isMfwFamily(type)) {
    steps.push({ key: 'config', titleKey: 'core.scripts.create.step.mfwSource' })
  }
  return steps
}

export const filterScriptTypeOptions = (options: ScriptTypeOption[], keyword: string) => {
  const search = keyword.trim().toLowerCase()
  return options.filter(option =>
    [option.title, option.description, ...option.keywords].join(' ').toLowerCase().includes(search)
  )
}

export const splitScriptTypeOptions = <T extends Pick<ScriptTypeOption, 'group'>>(
  options: T[]
) => ({
  specialized: options.filter(option => option.group === 'specialized'),
  general: options.filter(option => option.group === 'general'),
})

export const buildCreateRequest = (state: CreateRequestState): ScriptCreateRequest | null => {
  if (isMfwFamily(state.type) && state.mfwSourceMode === 'reuse') {
    return state.mfwSourceScriptId
      ? { kind: 'mfw-reuse', type: state.type, sourceScriptId: state.mfwSourceScriptId }
      : null
  }
  if (state.type !== 'General') {
    return { kind: 'new', type: state.type }
  }
  if (state.configMode === 'custom') {
    return { kind: 'general-custom' }
  }
  return state.template ? { kind: 'general-template', template: state.template } : null
}

/**
 * 新建流程 `source`：MFW 家族第二步「项目从哪来」的选项（新建一个别的项目 / 复用已导入的项目）。
 * 选中状态归对话框所有（返回再进来照样保留，列表变了选中的源失效时由对话框退回 'new'），
 * 分节只负责显示与交回选择。
 */
export interface MaaFWCreateSourceSectionProps {
  /** 选中的类型卡片：只列与它同类型的项目 */
  type: MfwFamilyType
  /** 可复用的项目（已按类型筛好、同一项目并成一行） */
  choices: MfwReuseChoice[]
  /** 候选列表正在读 */
  loading: boolean
  /** 候选列表没读出来的原因；有值就显示错误条 + 重试 */
  error: string | null
  /** 'new' = 新建一个别的项目；否则是要复用的项目所属脚本的 id */
  value: string
}

export interface MaaFWCreateSourceSectionEmits {
  'update:value': [value: string]
  /** 点了错误条上的「重试」：对话框重新读候选列表 */
  retry: []
}
