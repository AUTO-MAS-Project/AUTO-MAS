// 活动关选关意图的共享纯逻辑：意图解析、判玉、材料白名单、活动时间。
// 排序与判玉规则必须与后端 _resolve_activity_stage / getStage 保持同锚；
// 计划表页槽位逻辑（activityStageSlots.ts）与用户编辑页状态机共用本模块。

import type { ActivityItem } from '@/types/home'

export type { ActivityItem } from '@/types/home'

/** 选关下拉里「自定义材料」的伪值（选中后展开材料子选，写回 mat:<id>；不落库） */
export const MATERIAL_PSEUDO_VALUE = '__mat__'

/** 槽位键：意图 → 归并键 */
export function slotKeyOfIntent(intent: string): string {
  if (intent === 'jade') return 'jade'
  if (intent.startsWith('last:')) return intent
  if (intent.startsWith('mat:')) return 'mat'
  return ''
}

/** 提取关卡码尾部编号（SR-8 → 8），与后端 _stage_number_key 一致 */
export function stageNumber(value: string): number {
  const match = /(\d+)$/.exec(value)
  return match ? parseInt(match[1], 10) : -1
}

/** 判玉：原始掉落文本含「玉」（归一化 Drop 与真固源岩线同 ID，不可靠） */
export function isJadeStage(stage: Pick<ActivityItem, 'RawDrop' | 'Drop'>): boolean {
  return (stage.RawDrop ?? '').includes('玉')
}

/** 意图 → 关卡码（与后端 _resolve_activity_stage 同语义） */
export function resolveIntentStage(
  intent: string,
  stages: ActivityItem[],
): string | null {
  if (!intent) return null
  if (intent === 'jade') {
    return stages.find(stage => isJadeStage(stage))?.Value ?? null
  }
  if (intent.startsWith('last:')) {
    const index = parseInt(intent.slice(5), 10)
    if (!Number.isFinite(index) || index < 1) return null
    const ranked = stages
      .filter(stage => !isJadeStage(stage))
      .sort((a, b) => stageNumber(b.Value) - stageNumber(a.Value))
    return ranked[index - 1]?.Value ?? null
  }
  if (intent.startsWith('mat:')) {
    const materialId = intent.slice(4)
    return stages.find(stage => (stage.RawDrop ?? '') === materialId)?.Value ?? null
  }
  return null
}

/** 材料白名单：当前数据里作为活动掉落出现过的材料（各服并集，含下期预览） */
export function collectMaterialOptions(
  stageByServer: Record<string, ActivityItem[]>,
): Array<{ label: string; value: string }> {
  const seen = new Map<string, string>()
  for (const stages of Object.values(stageByServer)) {
    for (const stage of stages) {
      const raw = stage.RawDrop ?? ''
      if (raw && /^\d+$/.test(raw) && !seen.has(raw)) {
        seen.set(raw, stage.DropName || raw)
      }
    }
  }
  return [...seen.entries()]
    .sort((a, b) => a[1].localeCompare(b[1], 'zh-Hans-CN'))
    .map(([value, label]) => ({ label: `${label}（${value}）`, value }))
}

/** 活动元信息（名称/起止文本）取自该组关卡第一条的 Activity 描述 */
export interface ActivityMeta {
  name: string
  startText: string
  expireText: string
}

export function readActivityMeta(stages: ActivityItem[]): ActivityMeta | null {
  const activity = stages[0]?.Activity
  if (!activity?.StageName) return null
  return {
    name: activity.StageName,
    startText: formatActivityTime(activity.UtcStartTime, activity.TimeZone),
    expireText: formatActivityTime(activity.UtcExpireTime, activity.TimeZone),
  }
}

/** 按活动时区格式化 UTC 时间为 MM-DD HH:mm */
export function formatActivityTime(utcText: string, timeZone: number): string {
  const parsed = new Date(`${utcText.replace(/\//g, '-')}Z`)
  if (Number.isNaN(parsed.getTime())) return utcText
  const shifted = new Date(parsed.getTime() + (timeZone ?? 8) * 3600_000)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(shifted.getUTCMonth() + 1)}-${pad(shifted.getUTCDate())} ${pad(shifted.getUTCHours())}:${pad(shifted.getUTCMinutes())}`
}
