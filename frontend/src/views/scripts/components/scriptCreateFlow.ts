import type { WebConfigTemplate } from '@/composables/useTemplateApi'
import type { ScriptType } from '@/types/script'
import { SCRIPT_LOGOS } from '@/utils/scriptLogos'

export type ConfigMode = 'template' | 'custom'
/** MFW 家族新建时项目从哪来：进引导页选目录导入，还是直接复用已有脚本的副本 */
export type MfwSourceMode = 'new' | 'reuse'
export type CreateStepKey = 'type' | 'config'

/** 由 MaaFW 引擎运行的类型（M9A 是它的特调类型，类型最终由项目决定） */
export type MfwFamilyType = 'MaaFW' | 'M9A'
export const isMfwFamily = (type: ScriptType): type is MfwFamilyType =>
  type === 'MaaFW' || type === 'M9A'
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

interface CreateStep {
  key: CreateStepKey
  titleKey: string
}

interface CreateRequestState {
  type: ScriptType
  configMode: ConfigMode
  template: WebConfigTemplate | null
  mfwSourceMode?: MfwSourceMode
  mfwSourceScriptId?: string | null
}

export type ScriptCreateRequest =
  | { kind: 'new'; type: Exclude<ScriptType, 'General'> }
  /** 同一个 MFW 项目再建一个脚本：建好后从 sourceScriptId 的副本克隆，不再选目录 */
  | { kind: 'mfw-reuse'; type: MfwFamilyType; sourceScriptId: string }
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
    // MaaFW 是通用引擎，不是专项：任何带 interface.json 的项目都由它运行，和「通用脚本」并列。
    value: 'MaaFW',
    titleKey: 'scripts.type.MaaFW',
    descriptionKey: 'scripts.create.typeDesc.MaaFW',
    keywords: ['maafw', 'maaframework', 'framework', 'mfw', 'interface.json', '通用'],
    group: 'general',
    icon: SCRIPT_LOGOS.MaaFW,
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
  {
    value: 'ZzzOd',
    titleKey: 'scripts.type.ZzzOd',
    descriptionKey: 'scripts.create.typeDesc.ZzzOd',
    keywords: ['zzz-od', 'zzz', '绝区零', 'zenless', '一条龙'],
    group: 'specialized',
    icon: SCRIPT_LOGOS.ZzzOd,
  },
  {
    value: 'BAAH',
    titleKey: 'scripts.type.BAAH',
    descriptionKey: 'scripts.create.typeDesc.BAAH',
    keywords: ['baah', '碧蓝档案', '蔚蓝档案', 'bluearchive', '爱丽丝助手'],
    group: 'specialized',
    icon: SCRIPT_LOGOS.BAAH,
  },
]

export const buildCreateSteps = ({ type }: Pick<CreateRequestState, 'type'>): CreateStep[] => {
  const steps: CreateStep[] = [{ key: 'type', titleKey: 'scripts.create.step.type' }]
  if (type === 'General') {
    steps.push({ key: 'config', titleKey: 'scripts.create.step.config' })
  } else if (isMfwFamily(type)) {
    steps.push({ key: 'config', titleKey: 'scripts.create.step.mfwSource' })
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
  ZzzOd: 'zzzod',
  BAAH: 'baah',
  General: 'general',
}

export const getScriptEditSegment = (type: ScriptType) => EDIT_SEGMENT_BY_TYPE[type]

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
