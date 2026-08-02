export type HSRStageEngine = 'M7A' | 'SRA'

export type HSRDynamicStageOption = {
  label: string
  detail?: string | null
  value: string
  categoryKey: string
  categoryLabel: string
  cost?: number | null
  maxCount?: number | null
  m7a?: { instanceType?: string; instanceName?: string } | null
  sra?: { id?: string; level?: number | null } | null
}

export type HSRDynamicStageCategory = {
  categoryKey: string
  categoryLabel: string
  options?: HSRDynamicStageOption[]
}

export type HSRDynamicStageOptionsData = {
  engine: HSRStageEngine
  categories?: HSRDynamicStageCategory[]
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

export type HSRPerEngineStageStore<T> = {
  version?: 2
  byEngine?: Partial<Record<HSRStageEngine, T>>
}

export type HSRUserSRAConfig = {
  Id?: string | null
  Password?: string | null
}

// HSR 编辑器使用插件表单契约；reactive 默认值保持字段始终可编辑。
export type HSRUserConfigData = {
  Info: {
    Name?: string | null
    Status?: boolean | null
    Server?: 'CN-Official' | null
    RemainedDay?: number | null
    Notes?: string | null
  }
  SRA: HSRUserSRAConfig
  Stage: {
    Channel?: 'CalyxGolden' | 'CalyxCrimson' | 'Relic' | 'Ornament' | null
    ScriptStage?: Record<string, unknown> | null
    ScriptEchoOfWar?: Record<string, unknown> | null
  }
  TaskSwitch: {
    Daily?: boolean | null
    ReceiveRewards?: boolean | null
    DivergentUniverse?: boolean | null
    CurrencyWars?: boolean | null
  }
  TaskOpt: {
    EchoOfWarWeekday?:
      | 'Monday'
      | 'Tuesday'
      | 'Wednesday'
      | 'Thursday'
      | 'Friday'
      | 'Saturday'
      | 'Sunday'
      | null
  }
  Control: {
    Mode?: 'managed' | 'direct' | null
    SRA?: boolean | null
    M7A?: boolean | null
  }
  Managed: {
    TaskMapping?: Record<string, HSRStageEngine> | null
    Options?: Record<string, Record<string, Record<string, unknown>>> | null
  }
  Direct: {
    SRAConfig?: string | null
    M7AConfig?: string | null
    SRAImportedAt?: string | null
    M7AImportedAt?: string | null
    SRASource?: string | null
    M7ASource?: string | null
  }
  Data: {
    LastProxyDate?: string | null
    ProxyTimes?: number | null
    IfPassCheck?: boolean | null
    EchoOfWarCompletedThisWeek?: boolean | null
    EchoOfWarLastResetWeek?: string | null
    EchoOfWarLastCompletionDate?: string | null
    WeeklyLastCompletionDate?: string | null
    WeeklyCompletedThisWeek?: boolean | null
    WeeklyLastResetWeek?: string | null
    SRARedeemCodeFingerprint?: string | null
    M7ARedeemCodeFingerprint?: string | null
  }
}
