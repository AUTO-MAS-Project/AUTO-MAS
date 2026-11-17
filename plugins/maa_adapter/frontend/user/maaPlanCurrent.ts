import type { MaaPlanConfig } from '@/api'
import { getGameDayOffset } from './periodMarkers'

type CompleteMaaPlan = {
  MedicineNumb: number
  SeriesNumb: string
  Stage: string
  Stage_1: string
  Stage_2: string
  Stage_3: string
}

function completePlan(group: MaaPlanConfig['ALL']): CompleteMaaPlan | null {
  if (
    typeof group?.MedicineNumb !== 'number' ||
    typeof group.SeriesNumb !== 'string' ||
    typeof group.Stage !== 'string' ||
    typeof group.Stage_1 !== 'string' ||
    typeof group.Stage_2 !== 'string' ||
    typeof group.Stage_3 !== 'string'
  )
    return null
  return group as CompleteMaaPlan
}

export function getCurrentMaaPlan(plan: MaaPlanConfig | null, server: string, now = Date.now()) {
  if (!plan) return null
  const mode = plan.Info?.Mode ?? 'ALL'
  if (mode === 'ALL') return completePlan(plan.ALL)

  // 后端以游戏日日期为准：UTC+区服偏移减去 4 小时。
  const gameDay = new Date(now + getGameDayOffset(server) * 60 * 60 * 1000)
  if (mode === 'Weekly') {
    const days = [
      'Sunday',
      'Monday',
      'Tuesday',
      'Wednesday',
      'Thursday',
      'Friday',
      'Saturday',
    ] as const
    return completePlan(plan[days[gameDay.getUTCDay()]])
  }
  if (mode === 'Rotate') {
    const rotateDays = plan.Info?.RotateDays ?? 7
    if (!Number.isInteger(rotateDays) || rotateDays < 1 || rotateDays > 31) return null
    const ordinal = Math.floor(gameDay.getTime() / 86_400_000) + 719163
    const key = `Day${(ordinal % rotateDays) + 1}` as keyof MaaPlanConfig
    return completePlan(plan[key] as MaaPlanConfig['ALL'])
  }
  return null
}
