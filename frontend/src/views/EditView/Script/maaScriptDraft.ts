import type { MAAScriptConfig } from '@/types/script'

export const createMaaScriptDraft = (): MAAScriptConfig => ({
  Info: {
    Name: '',
    Path: '.',
  },
  Run: {
    HardTimeLimit: 120,
    TaskTransitionMethod: 'ExitEmulator',
    ProxyTimesLimit: 0,
    RunTimesLimit: 3,
    AnnihilationTimeLimit: 40,
    RoutineTimeLimit: 10,
    IfCheckGameUpdate: false,
    IfAutoInstallGameApk: false,
    GameUpdateTimeLimit: 60,
  },
  Emulator: {
    Id: '',
    Index: '',
  },
  Update: {
    TakeoverEnabled: false,
    MirrorChyanCDK: '',
  },
})
