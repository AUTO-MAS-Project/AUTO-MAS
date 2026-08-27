// 任务行折叠态摘要：不展开也能确认当前生效的配置
export const ANNIHILATION_STAGE_OPTIONS = [
  { label: '关闭', value: 'Close' },
  { label: '当期剿灭', value: 'Annihilation' },
  { label: '切尔诺伯格', value: 'Chernobog@Annihilation' },
  { label: '龙门外环', value: 'LungmenOutskirts@Annihilation' },
  { label: '龙门市区', value: 'LungmenDowntown@Annihilation' },
]

export const ANNIHILATION_WEEKDAY_OPTIONS = [
  { label: '周一', value: 'Monday' },
  { label: '周二', value: 'Tuesday' },
  { label: '周三', value: 'Wednesday' },
  { label: '周四', value: 'Thursday' },
  { label: '周五', value: 'Friday' },
  { label: '周六', value: 'Saturday' },
  { label: '周日', value: 'Sunday' },
]

export const weekdayLabel = (value: string) =>
  ANNIHILATION_WEEKDAY_OPTIONS.find(option => option.value === value)?.label ?? '周一'

export const annihilationStageLabel = (value: string) =>
  ANNIHILATION_STAGE_OPTIONS.find(option => option.value === value)?.label ?? value

/** 关卡值转显示文本：'-' 表示沿用游戏内当前选择，空表示未配置 */
export const stageLabel = (value: string) => (value === '-' ? '当前/上次' : value || '不选择')

/** 连战次数：'0' 为自动识别倍率，'-1' 为不改动游戏内设置 */
export const seriesLabel = (value: string) =>
  value === '0' ? 'AUTO' : value === '-1' ? '不切换' : value

// 关闭态一律返回空串：关着的开关已经表达了关闭，摘要再写一遍就是重复
export const summarizeAnnihilation = (
  stage: string,
  weekday: string,
  completedThisWeek: boolean
) => {
  if (stage === 'Close') return ''
  const parts = [
    annihilationStageLabel(stage),
    `${weekdayLabel(weekday)}起`,
    `本周${completedThisWeek ? '已完成' : '未完成'}`,
  ]
  return parts.join(' · ')
}

export const summarizeActivity = (options: {
  enabled: boolean
  loading: boolean
  optionCount: number
  stageLabel?: string
  medicine: number
}) => {
  if (!options.enabled) return ''
  if (options.loading) return '加载中…'
  if (!options.optionCount) return '当前无可刷活动关'
  return `${options.stageLabel ?? '未选择'} · 理智药 ${options.medicine}`
}

export const summarizeDepot = (isPlanMode: boolean, enabled: boolean, plansJson: string) => {
  if (isPlanMode) return '计划模式下不可用'
  if (!enabled) return ''
  let count = 0
  try {
    const parsed = JSON.parse(plansJson || '[]')
    count = Array.isArray(parsed) ? parsed.length : 0
  } catch {
    count = 0
  }
  return count ? `${count} 项计划` : '尚未添加计划'
}

export const INFRAST_MODE_OPTIONS = [
  { label: '常规模式', value: 'Normal' },
  { label: '一键轮休', value: 'Rotation' },
  { label: '自定义基建', value: 'Custom' },
]

export const infrastModeLabel = (value: string) =>
  INFRAST_MODE_OPTIONS.find(option => option.value === value)?.label ?? value

/** customLabel 由调用方拼好（配置名 + 排班名），自定义模式下未选完则只显示模式名 */
export const summarizeInfrast = (enabled: boolean, mode: string, customLabel: string) => {
  if (!enabled) return ''
  const modeText = infrastModeLabel(mode)
  return mode === 'Custom' && customLabel ? `${modeText} · ${customLabel}` : modeText
}

export const summarizeFight = (options: {
  enabled: boolean
  planLabel?: string
  stage: string
  series: string
  medicine: number
  remain: string
}) => {
  if (!options.enabled) return ''
  const parts = [
    stageLabel(options.stage),
    `连战 ${seriesLabel(options.series)}`,
    `理智药 ${options.medicine}`,
  ]
  if (options.remain && options.remain !== '-') {
    parts.push(`剩余理智 ${options.remain}`)
  }
  return options.planLabel ? `${options.planLabel} · ${parts.join(' · ')}` : parts.join(' · ')
}
