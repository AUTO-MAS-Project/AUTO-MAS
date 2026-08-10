import type {
  HSRDynamicStageCategory,
  HSRDynamicStageOption,
  HSRStageOptionsData,
  HSRUserConfig_Data,
  HSRUserConfig_Info,
  HSRUserConfig_Notify,
  HSRUserConfig_Stage,
  HSRUserConfig_TaskOpt,
  HSRUserConfig_TaskSwitch,
} from '@/api'

export type HSRStageEngine = 'M7A' | 'SRA'

export type { HSRDynamicStageCategory, HSRDynamicStageOption }

export type HSRDynamicStageOptionsData = Omit<HSRStageOptionsData, 'engine'> & {
  engine: HSRStageEngine
}

export type HSRScriptStagePayload = {
  engine?: HSRStageEngine | ''
  category?: string
  categoryLabel?: string
  label?: string
  detail?: string
  value?: string
  sra?: {
    id?: string
    level?: number | null
  }
  m7a?: {
    instanceType?: string
    instanceName?: string
  }
}

export type HSRScriptStageContainer = {
  engine?: HSRStageEngine | ''
  stages?: Partial<Record<string, HSRScriptStagePayload>>
}

/** Versioned per-engine stage storage used by the plugin-v2 editor. */
export type HSRPerEngineStageStore<T> = {
  version?: 2
  byEngine?: Partial<Record<HSRStageEngine, T>>
}

export type HSRUserControlMode = 'managed' | 'direct'

export type HSRUserControl = {
  Mode?: HSRUserControlMode | null
  SRA?: boolean | null
  M7A?: boolean | null
}

export type HSRUserManagedConfig = {
  TaskMapping?: Record<string, HSRStageEngine | string> | null
  Options?: Record<string, Record<string, Record<string, unknown>>> | null
}

export type HSRUserDirectConfig = {
  SRAImportedAt?: string | null
  M7AImportedAt?: string | null
  SRASource?: string | null
  M7ASource?: string | null
}

type HSRLegacyOrDynamicStage = string | HSRScriptStageContainer | Record<string, unknown> | null

// HSR 内部非空 reactive 形态（OpenAPI 生成的类型全部字段为 optional | null，
// 但前端用 reactive 实际为非空值；模板 / 计算属性通过该形态消除 strict null 警告）。
export type HSRUserConfigData = {
  Info: HSRUserConfig_Info & {
    Id?: string | null
    Password?: string | null
    Tag?: string | null
  }
  Stage: Omit<HSRUserConfig_Stage, 'ScriptStage' | 'ScriptEchoOfWar'> & {
    ScriptStage?: HSRLegacyOrDynamicStage
    ScriptEchoOfWar?: HSRLegacyOrDynamicStage
  }
  TaskSwitch: HSRUserConfig_TaskSwitch
  TaskOpt: HSRUserConfig_TaskOpt
  Data: HSRUserConfig_Data
  Notify?: HSRUserConfig_Notify
  Control: HSRUserControl
  Managed: HSRUserManagedConfig
  Direct: HSRUserDirectConfig
}
