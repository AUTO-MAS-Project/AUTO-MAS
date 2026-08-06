import type { WebConfigTemplate } from '@/composables/useTemplateApi'
import type { ScriptType } from '@/types/script'
import type { ScriptTypeDescriptor } from '@/types/scriptRegistry'
import { getScriptIcon } from '@/utils/scriptRegistry'
import generalIcon from '@/assets/AUTO-MAS.ico'
import maaIcon from '@/assets/MAA.png'
import maaEndIcon from '@/assets/MaaEnd.png'
import srcIcon from '@/assets/SRC.png'

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
    icon: generalIcon,
  },
  {
    value: 'MAA',
    title: 'MAA 脚本',
    description: '明日方舟自动化与多账号日常代理',
    keywords: ['maa', '明日方舟'],
    group: 'specialized',
    icon: maaIcon,
  },
  {
    value: 'SRC',
    title: 'SRC 脚本',
    description: '星穹铁道自动化与多账号代理',
    keywords: ['src', '星穹铁道'],
    group: 'specialized',
    icon: srcIcon,
  },
  {
    value: 'MaaEnd',
    title: 'MaaEnd 脚本',
    description: 'MaaFramework 专项适配脚本',
    keywords: ['maaend', 'maaframework'],
    group: 'specialized',
    icon: maaEndIcon,
  },
  {
    value: 'MaaFW',
    title: 'MaaFramework 项目',
    description: '读取 interface 并运行 MaaFramework 项目',
    keywords: ['maafw', 'maaframework', 'interface'],
    group: 'general',
    icon: generalIcon,
  },
]

export const createScriptTypeOptions = (descriptors: ScriptTypeDescriptor[]): ScriptTypeOption[] =>
  descriptors
    .filter(descriptor => descriptor.available !== false && descriptor.creatable !== false)
    .map(descriptor => {
      const createClient = descriptor.client?.create
      const createDescription =
        typeof createClient === 'object' && createClient !== null && 'description' in createClient
          ? (createClient as { description?: unknown }).description
          : undefined
      const createKeywords =
        typeof createClient === 'object' && createClient !== null && 'keywords' in createClient
          ? (createClient as { keywords?: unknown }).keywords
          : undefined
      const description =
        typeof createDescription === 'string' && createDescription.trim()
          ? createDescription.trim()
          : descriptor.supported_modes.length
            ? `支持模式：${descriptor.supported_modes.join(' / ')}`
            : '由脚本类型插件提供'
      const keywords = Array.isArray(createKeywords)
        ? createKeywords.filter((keyword): keyword is string => typeof keyword === 'string')
        : []
      return {
        value: descriptor.type_key,
        title: descriptor.display_name,
        description,
        keywords: [
          descriptor.type_key,
          descriptor.display_name,
          ...keywords,
          ...descriptor.supported_modes,
        ],
        group: descriptor.create_group ?? 'specialized',
        icon: getScriptIcon(descriptor.type_key, descriptor.icon_url),
      }
    })

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

export const buildCreateRequest = (state: CreateRequestState): ScriptCreateRequest | null => {
  if (state.type !== 'General') {
    return { kind: 'new', type: state.type }
  }
  if (state.configMode === 'custom') {
    return { kind: 'general-custom' }
  }
  return state.template ? { kind: 'general-template', template: state.template } : null
}
