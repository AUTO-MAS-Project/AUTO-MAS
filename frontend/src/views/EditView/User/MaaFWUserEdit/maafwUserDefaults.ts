import type { MaaFWUserConfig } from '@/types/script'

export const getDefaultMaaFWUserData = (): MaaFWUserConfig => ({
  Info: {
    Name: '',
    Status: true,
    RemainedDay: -1,
    IfScriptBeforeTask: false,
    ScriptBeforeTask: '',
    IfScriptAfterTask: false,
    ScriptAfterTask: '',
    Notes: '',
    Tag: '',
    Id: '',
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
    LastProxyStatus: '未知',
    PeriodTaskRecords: '{ }',
  },
})
