import type { ShareTemplateItem } from '@/composables/useTemplateApi'
import type { MaaFWEmbeddedSourceItem } from '@/api'
import { isMaaFWFamily, type MaaFWFlavorType } from '@/composables/useMaaFWFlavor'
import type { ScriptType } from '@/types/script'
import { SCRIPT_DESCRIPTORS, getScriptDescriptor } from '@/scriptDescriptors'

export type ConfigMode = 'template' | 'custom'
/** MFW 家族新建时项目从哪来：进引导页选目录导入，还是直接复用已有脚本的副本 */
export type MfwSourceMode = 'new' | 'reuse'
export type CreateStepKey = 'type' | 'config'

/** 由 MaaFW 引擎运行的类型（各特调登记在特调注册表，类型最终由项目决定） */
export type MfwFamilyType = MaaFWFlavorType
export const isMfwFamily = (type: ScriptType): type is MfwFamilyType => isMaaFWFamily(type)
type ScriptTypeGroup = 'all' | 'specialized' | 'general'

interface ScriptTypeOption {
  value: ScriptType
  titleKey: string
  descriptionKey: string
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
  | { kind: 'new'; type: Exclude<ScriptType, 'General'> }
  /** 同一个 MFW 项目再建一个脚本：建好后从 sourceScriptId 的副本克隆，不再选目录 */
  | { kind: 'mfw-reuse'; type: MfwFamilyType; sourceScriptId: string }
  | { kind: 'general-custom' }
  | { kind: 'general-template'; template: ShareTemplateItem }

export const SCRIPT_TYPE_OPTIONS: ScriptTypeOption[] = SCRIPT_DESCRIPTORS.map(descriptor => {
  const { after: _after, order: _order, ...card } = descriptor.card
  return { value: descriptor.type, ...card, icon: descriptor.logo }
})

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

type TypeSearchFields = Pick<ScriptTypeOption, 'titleKey' | 'descriptionKey' | 'keywords'>

/** translate 缺省时按 key 原样参与匹配，别名（keywords）永远参与匹配 */
export const filterScriptTypeOptions = <T extends TypeSearchFields>(
  options: T[],
  keyword: string,
  translate: (key: string) => string = key => key
): T[] => {
  const normalizedKeyword = keyword.trim().toLowerCase()
  return options.filter(option => {
    const searchableText = [
      translate(option.titleKey),
      translate(option.descriptionKey),
      ...option.keywords,
    ]
      .join(' ')
      .toLowerCase()
    return !normalizedKeyword || searchableText.includes(normalizedKeyword)
  })
}

export const splitScriptTypeOptions = <T extends Pick<ScriptTypeOption, 'group'>>(
  options: T[]
) => ({
  specialized: options.filter(option => option.group === 'specialized'),
  general: options.filter(option => option.group === 'general'),
})

export const getScriptEditSegment = (type: ScriptType) => {
  const path = getScriptDescriptor(type).routes.script.path
  return path.slice(path.lastIndexOf('/') + 1)
}

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
