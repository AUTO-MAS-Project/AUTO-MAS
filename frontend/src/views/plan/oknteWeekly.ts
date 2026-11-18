import { PLAN_WEEKDAY_KEYS } from '@/utils/planDays'
import type { OverrideConfigs } from './oknteOverrideTypes'

export const oknteWeeklyLabelKeys: Record<string, string> = {
  'Dress Sleeves of Vanity': 'core.plan.oknte.weeklyArachne',
  'Eternal Memory': 'core.plan.oknte.weeklyDebtCollector',
  'Good Boy Stamp': 'core.plan.oknte.weeklyMorphix',
  'Hollowflower Seeds': 'core.plan.oknte.weeklyBroodmother',
}
export const oknteWeeklyLabel = (value: string, translate: (key: string) => string) =>
  oknteWeeklyLabelKeys[value] ? translate(oknteWeeklyLabelKeys[value]!) : value

export function hasExplicitWeekly(configs: OverrideConfigs): boolean {
  const items = configs['DailyRoutineTask.json']?.['Routine Items'] as
    | { id: string; enabled: boolean }[]
    | undefined
  const enabled = items?.find(item => item.id === 'anomaly_pilgrimage')?.enabled
  const weekly = configs['DailyRoutineTaskConfigs.json']?.anomaly_pilgrimage as
    | Record<string, unknown>
    | undefined
  return enabled === true || (enabled !== false && weekly?.['目标'] !== undefined)
}
export function withWeeklyDefaults(configs: OverrideConfigs, day: string): OverrideConfigs {
  const next: OverrideConfigs = JSON.parse(JSON.stringify(configs))
  if (hasExplicitWeekly(next)) {
    const tasks = (next['DailyRoutineTaskConfigs.json'] ??= {})
    const weekly = (tasks.anomaly_pilgrimage ??= {}) as Record<string, unknown>
    const weekday = PLAN_WEEKDAY_KEYS.findIndex(key => key === day)
    if (weekly['每周开始运行日'] === undefined)
      weekly['每周开始运行日'] = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'][
        Math.max(weekday, 0)
      ]
    if (weekly['轮换起始日期'] === undefined) weekly['轮换起始日期'] = ''
  }
  return next
}
