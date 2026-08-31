import type { WebConfigTemplate } from '@/composables/useTemplateApi'
import type { ScriptType } from '@/types/script'
import { SCRIPT_LOGOS } from '@/utils/scriptLogos'

export type ConfigMode = 'template' | 'custom'
export type CreateStepKey = 'type' | 'config'
export type ScriptTypeGroup = 'all' | 'specialized' | 'general'

export interface ScriptTypeOption {
  value: ScriptType
  titleKey: string
  descriptionKey: string
  /** 搜索别名。刻意保留中文：译成英文中文用户就搜不到了，英文用户用 latin 别名一样能命中 */
  keywords: string[]
  group: Exclude<ScriptTypeGroup, 'all'>
  icon: string
}

export interface CreateStep {
  key: CreateStepKey
  titleKey: string
}

export interface CreateRequestState {
  type: ScriptType
  configMode: ConfigMode
  template: WebConfigTemplate | null
}

export type ScriptCreateRequest =
  | { kind: 'new'; type: Exclude<ScriptType, 'General'> }
  | { kind: 'general-custom' }
  | { kind: 'general-template'; template: WebConfigTemplate }

export const SCRIPT_TYPE_OPTIONS: ScriptTypeOption[] = [
  {
    value: 'General',
    titleKey: 'scripts.type.General',
    descriptionKey: 'scripts.create.typeDesc.General',
    keywords: ['general', '通用', '自定义'],
    group: 'general',
    icon: SCRIPT_LOGOS.General,
  },
  {
    value: 'MAA',
    titleKey: 'scripts.type.MAA',
    descriptionKey: 'scripts.create.typeDesc.MAA',
    keywords: ['maa', '明日方舟'],
    group: 'specialized',
    icon: SCRIPT_LOGOS.MAA,
  },
  {
    value: 'SRC',
    titleKey: 'scripts.type.SRC',
    descriptionKey: 'scripts.create.typeDesc.SRC',
    keywords: ['src', '星穹铁道'],
    group: 'specialized',
    icon: SCRIPT_LOGOS.SRC,
  },
  {
    value: 'MaaEnd',
    titleKey: 'scripts.type.MaaEnd',
    descriptionKey: 'scripts.create.typeDesc.MaaEnd',
    keywords: ['maaend', 'maaframework'],
    group: 'specialized',
    icon: SCRIPT_LOGOS.MaaEnd,
  },
  {
    value: 'M9A',
    titleKey: 'scripts.type.M9A',
    descriptionKey: 'scripts.create.typeDesc.M9A',
    keywords: ['m9a', '1999', '重返未来'],
    group: 'specialized',
    icon: SCRIPT_LOGOS.M9A,
  },
  {
    value: 'MaaFW',
    titleKey: 'scripts.type.MaaFW',
    descriptionKey: 'scripts.create.typeDesc.MaaFW',
    keywords: ['maafw', 'maaframework', 'framework', 'mfw'],
    group: 'specialized',
    icon: SCRIPT_LOGOS.MaaFW,
  },
  {
    value: 'Okww',
    titleKey: 'scripts.type.Okww',
    descriptionKey: 'scripts.create.typeDesc.Okww',
    keywords: ['okww', 'ok-ww', 'ok-script'],
    group: 'specialized',
    icon: SCRIPT_LOGOS.Okww,
  },
  {
    value: 'OkNte',
    titleKey: 'scripts.type.OkNte',
    descriptionKey: 'scripts.create.typeDesc.OkNte',
    keywords: ['oknte', 'ok-nte', '异环', 'ok-script'],
    group: 'specialized',
    icon: SCRIPT_LOGOS.OkNte,
  },
  {
    value: 'HSR',
    titleKey: 'scripts.type.HSR',
    descriptionKey: 'scripts.create.typeDesc.HSR',
    keywords: ['hsr', '三月七', 'sra'],
    group: 'specialized',
    icon: SCRIPT_LOGOS.HSR,
  },
  {
    value: 'BetterGI',
    titleKey: 'scripts.type.BetterGI',
    descriptionKey: 'scripts.create.typeDesc.BetterGI',
    keywords: ['bettergi', 'better-gi', '原神', 'genshin'],
    group: 'specialized',
    icon: SCRIPT_LOGOS.BetterGI,
  },
]

export const buildCreateSteps = ({ type }: Pick<CreateRequestState, 'type'>): CreateStep[] => {
  const steps: CreateStep[] = [{ key: 'type', titleKey: 'scripts.create.step.type' }]
  if (type === 'General') {
    steps.push({ key: 'config', titleKey: 'scripts.create.step.config' })
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

const EDIT_SEGMENT_BY_TYPE: Record<ScriptType, string> = {
  MAA: 'maa',
  SRC: 'src',
  MaaEnd: 'maaend',
  M9A: 'm9a',
  MaaFW: 'maafw',
  Okww: 'okww',
  OkNte: 'oknte',
  HSR: 'hsr',
  BetterGI: 'bettergi',
  General: 'general',
}

export const getScriptEditSegment = (type: ScriptType) => EDIT_SEGMENT_BY_TYPE[type]

export const buildCreateRequest = (state: CreateRequestState): ScriptCreateRequest | null => {
  if (state.type !== 'General') {
    return { kind: 'new', type: state.type }
  }
  if (state.configMode === 'custom') {
    return { kind: 'general-custom' }
  }
  return state.template ? { kind: 'general-template', template: state.template } : null
}
