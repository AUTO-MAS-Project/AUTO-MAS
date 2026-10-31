import type { MaaEndScriptConfig } from '@/types/script'

/** MaaEnd 脚本编辑页的初始配置：与 generalScriptDraft 同一形态，字段默认值只在这里维护。 */
export const createMaaEndScriptDraft = (): MaaEndScriptConfig => ({
  Update: { TakeoverEnabled: false, Channel: 'stable', MirrorChyanCDK: '' },
  Info: {
    Name: '',
    Path: '',
  },
  Run: {
    HardTimeLimit: 120,
    RunTimeLimit: 30,
    ProxyTimesLimit: 0,
    RunTimesLimit: 3,
    AccountSwitchMethod: 'MAAEND',
    TaskTransitionMethod: 'NoAction',
    IfSaveLogBundle: false,
    LogBundlePath: null,
  },
  Game: {
    ControllerType: '',
    LaunchMode: 'Launcher',
    Path: '',
    LauncherPath: '',
    Arguments: '',
    WaitTime: 60,
    EmulatorId: '',
    EmulatorIndex: '',
    SetResolution: false,
    CloseOnFinish: true,
    RestoreResolution: 'Off',
    RestoreDisplayType: 'Window',
    RestoreResolutionWidth: 1920,
    RestoreResolutionHeight: 1080,
    IfAutoUpdate: false,
    UpdateTimeLimit: 240,
  },
})
