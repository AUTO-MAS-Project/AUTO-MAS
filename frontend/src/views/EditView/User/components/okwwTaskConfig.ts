import type { OkwwUserConfig } from '@/api'

export type OkwwTaskForm = {
  [K in keyof NonNullable<OkwwUserConfig['Task']>]-?: NonNullable<
    NonNullable<OkwwUserConfig['Task']>[K]
  >
}

export const getDefaultOkwwTaskConfig = (): OkwwTaskForm => ({
  WhichToFarm: 'Tacet Suppression',
  WhichTacetSuppressionToFarm: 1,
  WhichForgeryChallengeToFarm: 1,
  MaterialSelection: 'Shell Credit',
  FarmNightmareNestForDailyEcho: true,
  AdditionalTasks: ['Check Weekly Garden'],
  IfCustomArguments: false,
  CustomArguments: '-t DailyTask',
})
