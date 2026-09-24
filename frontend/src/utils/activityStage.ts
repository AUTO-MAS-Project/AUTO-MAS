// 活动关选关意图的共享纯逻辑：意图解析、判玉、活动时间。
// 排序与判玉规则必须与后端 _resolve_activity_stage / getStage 保持同锚；
// 计划表页的行状态（activityUserRows.ts）与用户编辑页状态机共用本模块。

import type { ActivityItem } from '@/types/home'

export type { ActivityItem } from '@/types/home'

/** B服关卡数据与官服同源（后端 Bilibili→Official 归一），按服务器取关卡数据前先归一 */
export function stageServerOf(server: string): string {
  return server === 'Bilibili' ? 'Official' : server
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
export function resolveIntentStage(intent: string, stages: ActivityItem[]): string | null {
  if (!intent) return null
  if (intent === 'jade') {
    return stages.find(stage => isJadeStage(stage))?.Value ?? null
  }
  if (intent.startsWith('pos:')) {
    // 旧版序号：MAA 列表位置（迁移值，末位通常是玉关），越界不回退首关
    const index = parseInt(intent.slice(4), 10)
    if (!Number.isFinite(index) || index < 1) return null
    return stages[index - 1]?.Value ?? null
  }
  if (intent.startsWith('last:')) {
    const index = parseInt(intent.slice(5), 10)
    if (!Number.isFinite(index) || index < 1) return null
    const ranked = stages
      .filter(stage => !isJadeStage(stage))
      .sort((a, b) => stageNumber(b.Value) - stageNumber(a.Value))
    // 越界即无匹配：旧序号已如实迁成 pos:，这里不再对 last: 做旧值兼容，
    // 否则同一期选的「倒3」在下期只有 2 个材料关时会被当成旧值改刷玉关
    return ranked[index - 1]?.Value ?? null
  }
  return null
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
