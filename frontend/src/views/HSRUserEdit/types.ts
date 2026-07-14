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

export type HSRUserSRAConfig = {
  Id?: string | null
  Password?: string | null
}

// HSR 内部非空 reactive 形态（OpenAPI 生成的类型全部字段为 optional | null，
// 但前端用 reactive 实际为非空值；模板 / 计算属性通过该形态消除 strict null 警告）。
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
    ScriptStage?: string | Record<string, unknown> | null
    ScriptEchoOfWar?: string | Record<string, unknown> | null
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
  }
}
