import type { MaaFWUserConfig } from '@/types/script'

export const getDefaultMaaFWUserData = (): MaaFWUserConfig => ({
  Info: {
    Name: '',
    Status: true,
    Base: 'independent',
    // 快速配置：独立于配置来源的用户级开关（生成模型 MaaFWUserConfig_Info 已含该字段）
    IfQuickConfig: true,
    RemainedDay: -1,
    IfScriptBeforeTask: false,
    ScriptBeforeTask: '',
    IfScriptAfterTask: false,
    ScriptAfterTask: '',
    Notes: '',
    Tag: '',
    Account: '',
    Password: '',
    PlanMode: 'Fixed',
  },
  Task: {
    SelectedPreset: '',
    TaskSnapshot: '{ }',
  },
  Notify: {
    Enabled: false,
    IfSendStatistic: false,
    IfSendMail: false,
    ToAddress: '',
    IfServerChan: false,
    ServerChanKey: '',
  },
  Data: {
    LastProxyDate: '2000-01-01T00:00:00+04:00',
    ProxyTimes: 0,
    IfPassCheck: true,
    LastProxyStatus: '未知',
    PeriodTaskRecords: '{ }',
  },
})
