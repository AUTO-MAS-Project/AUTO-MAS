// 活动关批量指派表的纯逻辑：槽位行推导、用户注入状态判定。
// 排序与判玉规则必须与后端 _resolve_activity_stage / getStage 保持同锚。

import type { ActivityItem } from '@/types/home'

export type { ActivityItem } from '@/types/home'

/** 派生表的用户行（来自 MAA 脚本用户配置扫描） */
export interface ActivityUserRow {
  scriptId: string
  scriptName: string
  userId: string
  userName: string
  server: string
  /** 用户启用状态（Info.Status） */
  status: boolean
  /** 关卡配置模式（Info.StageMode：计划表 id 或 'Fixed'），followsPlan 由它派生 */
  stageMode: string
  /** 是否跟随当前计划表（stageMode === 当前计划表 id，由组件按当前表派生） */
  followsPlan: boolean
  /** 未跟随时的归属描述（其他计划表名 / 固定模式） */
  planLabel: string
  ifQuickConfig: boolean
  ifActivityFirst: boolean
  intent: string
}

/** 槽位行（倒N → 搓玉 → 自定义材料） */
export interface StageSlotRow {
  key: string
  label: string
  /** 本期关卡码（锚定服务器视角；null=本期无此关） */
  stageCode: string | null
  stageMat: string | null
  /** 间隙期预解析（下期关卡，仅预览不注入） */
  notStarted: boolean
}

/** 槽位键：意图 → 表行归并键 */
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

/** 判玉：原始掉落文本含「玉」（与后端一致，归一化 Drop 不可靠） */
export function isJadeStage(stage: Pick<ActivityItem, 'RawDrop' | 'Drop'>): boolean {
  return (stage.RawDrop ?? '').includes('玉')
}

/**
 * 推导槽位行。stages = 当前显示视图关卡（进行中优先，间隙期用下期预览）；
 * notStarted 标记当前展示的是下期预览（间隙期预解析，仅显示不注入）；
 * assignedIntents = 跟随用户 currently 持有的全部意图（本期不存在的倒N
 * 有指派时保留置灰行，搓玉无玉期同理）。
 */
export function buildSlotRows(
  stages: ActivityItem[],
  assignedIntents: string[],
  notStarted: boolean,
): StageSlotRow[] {
  const rows: StageSlotRow[] = []

  const ranked = stages
    .filter(stage => !isJadeStage(stage))
    .sort((a, b) => stageNumber(b.Value) - stageNumber(a.Value))
  const jade = stages.find(stage => isJadeStage(stage))

  const assignedKeys = new Set(
    assignedIntents.map(slotKeyOfIntent).filter(key => key !== ''),
  )
  const maxAssignedLast = Math.max(
    0,
    ...[...assignedKeys]
      .filter((key): key is string => key.startsWith('last:'))
      .map(key => parseInt(key.slice(5), 10) || 0),
  )

  const rowCount = Math.max(ranked.length, maxAssignedLast)
  for (let index = 1; index <= rowCount; index += 1) {
    const stage = ranked[index - 1]
    rows.push({
      key: `last:${index}`,
      label: `倒${index}`,
      stageCode: stage?.Value ?? null,
      stageMat: stage?.DropName ?? null,
      notStarted,
    })
  }

  if (jade || assignedKeys.has('jade')) {
    rows.push({
      key: 'jade',
      label: '搓玉',
      stageCode: jade?.Value ?? null,
      stageMat: jade?.DropName ?? null,
      notStarted,
    })
  }

  rows.push({
    key: 'mat',
    label: '自定义材料',
    stageCode: null,
    stageMat: null,
    notStarted,
  })
  return rows
}

/**
 * 单用户注入状态。stagesForServer 按该用户自己的服务器解析；
 * period = 'ongoing' | 'preview' | 'gap'。
 */
export type UserInjectReason =
  | 'ok'
  | 'not-following'
  | 'user-disabled'
  | 'switch-off'
  | 'no-quick-config'
  | 'no-intent'
  | 'no-match'
  | 'gap'

export interface UserInjectStatus {
  willInject: boolean
  reason: UserInjectReason
}

export function resolveUserInjectStatus(
  user: ActivityUserRow,
  stages: ActivityItem[],
  period: 'ongoing' | 'preview' | 'gap',
): UserInjectStatus {
  if (!user.followsPlan) return { willInject: false, reason: 'not-following' }
  if (!user.status) return { willInject: false, reason: 'user-disabled' }
  if (!user.ifActivityFirst) return { willInject: false, reason: 'switch-off' }
  if (!user.ifQuickConfig) return { willInject: false, reason: 'no-quick-config' }
  if (!user.intent) return { willInject: false, reason: 'no-intent' }
  if (period !== 'ongoing') return { willInject: false, reason: 'gap' }
  if (!resolveIntentStage(user.intent, stages)) {
    return { willInject: false, reason: 'no-match' }
  }
  return { willInject: true, reason: 'ok' }
}

/** 意图 → 关卡码（与后端 _resolve_activity_stage 同语义，供状态列展示） */
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

/** 材料白名单：当前数据里作为活动掉落出现过的材料（本期 + 下期预览，各服并集） */
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
