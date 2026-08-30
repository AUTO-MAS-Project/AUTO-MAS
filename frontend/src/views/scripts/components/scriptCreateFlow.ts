import type { WebConfigTemplate } from '@/composables/useTemplateApi'
import type { ScriptType } from '@/types/script'
import { SCRIPT_LOGOS } from '@/utils/scriptLogos'

export type ConfigMode = 'template' | 'custom'
export type CreateStepKey = 'type' | 'config'
export type ScriptTypeGroup = 'all' | 'specialized' | 'general'

export interface ScriptTypeOption {
  value: ScriptType
  title: string
  description: string
  keywords: string[]
  group: Exclude<ScriptTypeGroup, 'all'>
  icon: string
}

export interface CreateStep {
  key: CreateStepKey
  title: string
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
    title: '通用脚本',
    description: '适用于具备日志文件的自动化脚本',
    keywords: ['general', '通用', '自定义'],
    group: 'general',
    icon: SCRIPT_LOGOS.General,
  },
  {
    value: 'MAA',
    title: 'MAA 脚本',
    description: '明日方舟自动化与多账号日常代理',
    keywords: ['maa', '明日方舟'],
    group: 'specialized',
    icon: SCRIPT_LOGOS.MAA,
  },
  {
    value: 'SRC',
    title: 'SRC 脚本',
    description: '星穹铁道自动化与多账号代理',
    keywords: ['src', '星穹铁道'],
    group: 'specialized',
    icon: SCRIPT_LOGOS.SRC,
  },
  {
    value: 'MaaEnd',
    title: 'MaaEnd 脚本',
    description: 'MFW 专项适配脚本',
    keywords: ['maaend', 'maaframework'],
    group: 'specialized',
    icon: SCRIPT_LOGOS.MaaEnd,
  },
  {
    value: 'M9A',
    title: 'M9A 脚本',
    description: '重返未来：1999 自动化脚本',
    keywords: ['m9a', '1999', '重返未来'],
    group: 'specialized',
    icon: SCRIPT_LOGOS.M9A,
  },
  {
    value: 'MaaFW',
    title: 'MFW 脚本',
    description: 'MFW 项目外部运行脚本',
    keywords: ['maafw', 'maaframework', 'framework', '外部运行'],
    group: 'specialized',
    icon: SCRIPT_LOGOS.MaaFW,
  },
  {
    value: 'Okww',
    title: 'ok-ww 脚本',
    description: 'ok-script 专项任务脚本',
    keywords: ['okww', 'ok-ww', 'ok-script'],
    group: 'specialized',
    icon: SCRIPT_LOGOS.Okww,
  },
  {
    value: 'OkNte',
    title: 'ok-nte 脚本',
    description: '异环 OK-NTE 自动化脚本',
    keywords: ['oknte', 'ok-nte', '异环', 'ok-script'],
    group: 'specialized',
    icon: SCRIPT_LOGOS.OkNte,
  },
  {
    value: 'HSR',
    title: 'HSR 脚本',
    description: '三月七 / SRA 双脚本适配',
    keywords: ['hsr', '三月七', 'sra'],
    group: 'specialized',
    icon: SCRIPT_LOGOS.HSR,
  },
]

export const buildCreateSteps = ({ type }: Pick<CreateRequestState, 'type'>): CreateStep[] => {
  const steps: CreateStep[] = [{ key: 'type', title: '脚本类型' }]
  if (type === 'General') {
    steps.push({ key: 'config', title: '配置来源' })
  }
  return steps
}

export const filterScriptTypeOptions = (options: ScriptTypeOption[], keyword: string) => {
  const normalizedKeyword = keyword.trim().toLowerCase()
  return options.filter(option => {
    const searchableText = [option.title, option.description, ...option.keywords]
      .join(' ')
      .toLowerCase()
    return !normalizedKeyword || searchableText.includes(normalizedKeyword)
  })
}

export const splitScriptTypeOptions = (options: ScriptTypeOption[]) => ({
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
