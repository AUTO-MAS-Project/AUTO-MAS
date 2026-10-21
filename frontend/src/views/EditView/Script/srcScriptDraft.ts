import type { SRCScriptConfig } from '@/types/script'

export const createSrcScriptDraft = (): SRCScriptConfig => ({
  Info: {
    Name: '',
    Path: '.',
  },
  Run: {
    HardTimeLimit: 120,
    TaskTransitionMethod: 'ExitEmulator',
    ProxyTimesLimit: 0,
    RunTimesLimit: 3,
    RunTimeLimit: 40,
    IfCheckGameUpdate: false,
    IfAutoInstallGameApk: false,
    GameUpdateTimeLimit: 60,
  },
  Emulator: {
    Id: '',
    Index: '',
  },
})
