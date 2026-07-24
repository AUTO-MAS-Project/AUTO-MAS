import maaIcon from '@/assets/MAA.png'
import srcIcon from '@/assets/SRC.png'
import maaEndIcon from '@/assets/MaaEnd.png'
import okwwIcon from '@/assets/ok-ww.ico'
import hsrIcon from '@/assets/hsr.png'
import autoMasIcon from '@/assets/AUTO-MAS.ico'
import type { Script, User } from '@/types/script'
import type { ScriptRecord, ScriptTypeDescriptor, ScriptUserRecord } from '@/types/scriptRegistry'
import { OpenAPI } from '@/api/core/OpenAPI'

const DEFAULT_USER_SHAPE = {
  Data: {
    IfPassCheck: false,
    LastProxyDate: '',
    LastSklandDate: '',
    ProxyTimes: 0,
  },
  Info: {
    Annihilation: '',
    Id: '',
    IfSkland: false,
    InfrastMode: '',
    InfrastName: '',
    InfrastIndex: '',
    MedicineNumb: 0,
    Mode: '',
    Name: '',
    Notes: '',
    Password: '',
    RemainedDay: -1,
    SeriesNumb: '',
    Server: '',
    SklandToken: '',
    Stage: '',
    StageMode: 'Fixed',
    Stage_1: '',
    Stage_2: '',
    Stage_3: '',
    Stage_Remain: '',
    Status: true,
    Tag: null,
  },
  Notify: {
    Enabled: false,
    IfSendMail: false,
    IfSendSixStar: false,
    CustomWebhooks: [],
    IfSendStatistic: false,
    IfServerChan: false,
    ServerChanChannel: '',
    ServerChanKey: '',
    ServerChanTag: '',
    ToAddress: '',
  },
  Task: {
    IfRoguelike: false,
    IfInfrast: false,
    IfFight: false,
    IfMall: false,
    IfAward: false,
    IfReclamation: false,
    IfRecruit: false,
    IfStartUp: false,
  },
  QFluentWidgets: {
    ThemeColor: '',
    ThemeMode: '',
  },
}

export const BUILTIN_SCRIPT_TYPES = new Set(['MAA', 'SRC', 'MaaEnd', 'M9A', 'MaaFW', 'OkScript'])

export const isBuiltinScriptType = (type: string) => BUILTIN_SCRIPT_TYPES.has(type)

export const getFallbackScriptIcon = (type: string) => {
  switch (type) {
    case 'MAA':
      return maaIcon
    case 'SRC':
      return srcIcon
    case 'MaaEnd':
      return maaEndIcon
    case 'Okww':
      return okwwIcon
    case 'OkScript':
      return autoMasIcon
    case 'HSR':
      return hsrIcon
    default:
      return autoMasIcon
  }
}

export const getScriptIcon = (type: string, iconUrl?: string | null) => {
  if (iconUrl) {
    if (iconUrl.startsWith('/')) {
      const base = (OpenAPI.BASE || 'http://127.0.0.1:36163').replace(/\/+$/, '')
      return `${base}${iconUrl}`
    }
    return iconUrl
  }
  return getFallbackScriptIcon(type)
}

export const handleScriptIconError = (event: Event, type: string) => {
  const image = event.currentTarget as HTMLImageElement | null
  if (!image || image.dataset.scriptIconFallbackApplied === 'true') {
    return
  }

  image.dataset.scriptIconFallbackApplied = 'true'
  image.src = getFallbackScriptIcon(type)
}

export const getScriptTypeTagColor = (type: string, themeColor?: string | null) => {
  const declaredColor = themeColor?.trim()
  if (declaredColor) return declaredColor

  switch (type) {
    case 'MAA':
      return 'blue'
    case 'SRC':
      return 'purple'
    case 'MaaEnd':
      return 'cyan'
    case 'MaaFW':
      return 'geekblue'
    case 'Okww':
    case 'OkScript':
      return 'orange'
    case 'HSR':
      return 'purple'
    case 'General':
      return 'green'
    default:
      return 'default'
  }
}

const BUILTIN_EDITOR_SEGMENTS: Record<string, string> = {
  'builtin:maa': 'maa',
  'builtin:src': 'src',
  'builtin:maaend': 'maaend',
  'builtin:m9a': 'm9a',
  'builtin:maafw': 'maafw',
  'builtin:ok-script': 'ok-script',
  'builtin:okef': 'ok-script',
}

const TYPE_KEY_EDITOR_SEGMENTS: Record<string, string> = {
  MaaFW: 'maafw',
  M9A: 'maafw',
  // ok-ww 使用专属编辑页（/edit/okww 等），与 PR #287/#288 的视觉与配置字段保持一致
  Okww: 'okww',
}

const PLUGIN_EDITOR_SEGMENTS: Record<string, string> = {
  'plugin:automas_script_hsr': 'hsr',
}

export const getScriptEditPath = (script: Pick<Script, 'id' | 'type' | 'editorKind'>) => {
  const segment =
    BUILTIN_EDITOR_SEGMENTS[script.editorKind ?? ''] ??
    PLUGIN_EDITOR_SEGMENTS[script.editorKind ?? ''] ??
    TYPE_KEY_EDITOR_SEGMENTS[script.type]
  if (segment) {
    return `/scripts/${script.id}/edit/${segment}`
  }
  if (script.editorKind?.startsWith('plugin:')) {
    return `/scripts/${script.id}/edit/plugin`
  }
  return `/scripts/${script.id}/edit/schema`
}

export const getUserCreatePath = (script: Pick<Script, 'id' | 'type' | 'editorKind'>) => {
  const segment =
    BUILTIN_EDITOR_SEGMENTS[script.editorKind ?? ''] ??
    PLUGIN_EDITOR_SEGMENTS[script.editorKind ?? ''] ??
    TYPE_KEY_EDITOR_SEGMENTS[script.type]
  if (segment) {
    return `/scripts/${script.id}/users/add/${segment}`
  }
  if (script.editorKind?.startsWith('plugin:')) {
    return `/scripts/${script.id}/users/add/plugin`
  }
  return `/scripts/${script.id}/users/add/schema`
}

export const getUserEditPath = (
  script: Pick<Script, 'id' | 'type' | 'editorKind'>,
  user: Pick<User, 'id'>
) => {
  const segment =
    BUILTIN_EDITOR_SEGMENTS[script.editorKind ?? ''] ??
    PLUGIN_EDITOR_SEGMENTS[script.editorKind ?? ''] ??
    TYPE_KEY_EDITOR_SEGMENTS[script.type]
  if (segment) {
    return `/scripts/${script.id}/users/${user.id}/edit/${segment}`
  }
  if (script.editorKind?.startsWith('plugin:')) {
    return `/scripts/${script.id}/users/${user.id}/edit/plugin`
  }
  return `/scripts/${script.id}/users/${user.id}/edit/schema`
}

export const descriptorMapFromList = (items: ScriptTypeDescriptor[]) =>
  items.reduce<Record<string, ScriptTypeDescriptor>>((acc, item) => {
    acc[item.type_key] = item
    return acc
  }, {})

export const normalizeUserRecord = (record: ScriptUserRecord): User => {
  const info =
    record.config?.Info && typeof record.config.Info === 'object' ? record.config.Info : {}
  return {
    ...DEFAULT_USER_SHAPE,
    ...record.config,
    id: record.id,
    name: typeof info.Name === 'string' && info.Name.trim() ? info.Name : record.name,
    scriptId: record.script_id,
    type: record.type,
    schema: record.schema,
    config: record.config,
    Info: {
      ...DEFAULT_USER_SHAPE.Info,
      ...(record.config?.Info || {}),
      Name:
        typeof info.Name === 'string' && info.Name.trim()
          ? info.Name
          : record.name || DEFAULT_USER_SHAPE.Info.Name,
    },
    Notify: {
      ...DEFAULT_USER_SHAPE.Notify,
      ...(record.config?.Notify || {}),
    },
    Data: {
      ...DEFAULT_USER_SHAPE.Data,
      ...(record.config?.Data || {}),
    },
    Task: {
      ...DEFAULT_USER_SHAPE.Task,
      ...(record.config?.Task || {}),
    },
    QFluentWidgets: {
      ...DEFAULT_USER_SHAPE.QFluentWidgets,
      ...(record.config?.QFluentWidgets || {}),
    },
  }
}

export const normalizeScriptRecord = (
  record: ScriptRecord,
  descriptorMap: Record<string, ScriptTypeDescriptor>,
  users: ScriptUserRecord[] = []
): Script => {
  const descriptor = descriptorMap[record.type]
  const providerAvailable = Boolean(descriptor) && descriptor?.available !== false
  const available = record.available ?? providerAvailable
  const info =
    record.config?.Info && typeof record.config.Info === 'object' ? record.config.Info : {}
  return {
    id: record.id,
    type: record.type,
    name: typeof info.Name === 'string' && info.Name.trim() ? info.Name : record.name,
    config: record.config,
    users: users.map(normalizeUserRecord),
    schema: record.schema,
    userSchema: descriptor?.user_schema,
    editorKind: record.editor_kind,
    supportedModes: record.supported_modes,
    icon: record.icon ?? descriptor?.icon ?? null,
    iconUrl: record.icon_url ?? descriptor?.icon_url ?? null,
    themeColor: record.theme_color ?? descriptor?.theme_color ?? null,
    docsUrl: record.docs_url ?? descriptor?.docs_url ?? null,
    editHint: record.edit_hint ?? null,
    displayName: descriptor?.display_name ?? record.type,
    isBuiltin: descriptor?.is_builtin ?? isBuiltinScriptType(record.type),
    providerAvailable,
    available,
    unavailableReason: available
      ? null
      : record.unavailable_reason ||
        descriptor?.unavailable_reason ||
        `脚本类型 ${record.type} 当前未启用，暂时不能操作`,
    createTime: new Date().toLocaleString(),
  }
}
