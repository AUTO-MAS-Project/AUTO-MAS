// 活动关批量指派表的纯逻辑：槽位行推导、用户注入状态判定。
// 共享原语（判玉/排序）在 @/utils/activityStage，本模块只保留
// 计划表页特有的槽位行与用户行模型。

import type { ActivityItem } from '@/types/home'
import {
  isJadeStage,
  resolveIntentStage,
  slotKeyOfIntent,
  stageNumber,
} from '@/utils/activityStage'

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
  /** 跳过簿命中当前活动（首错当日或连错≥2 天），后端本轮不会注入 */
  skipActive: boolean
  /** 跳过簿连错天数（0=未命中） */
  skipDays: number
  /** 跳过簿记录的在打关卡摘要（后端 detail：如「倒1 → SR-8 · 异铁组」） */
  skipSummary: string
}

/** 槽位行（倒N → 搓玉）；标题文案由组件按 key 走词表（slotLabelOfIntent） */
export interface StageSlotRow {
  key: string
  /** 本期关卡码（锚定服务器视角；null=本期无此关） */
  stageCode: string | null
  stageMat: string | null
  /** 间隙期预解析（下期关卡，仅预览不注入） */
  notStarted: boolean
  /** 无任何关卡数据时的默认骨架行（待下期录入后由真实数据替换） */
  skeleton: boolean
}

/**
 * 推导槽位行。stages = 当前显示视图关卡（进行中优先，间隙期用下期预览）；
 * notStarted 标记当前展示的是下期预览（间隙期预解析，仅显示不注入）；
 * assignedIntents = 跟随用户当前持有的全部意图（本期不存在的倒N有指派时
 * 保留置灰行，搓玉无玉期同理）。
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

  // 无任何关卡数据（间隙期且下期未录入）时给默认骨架 倒1~倒3 + 搓玉，
  // 指派照常可落，待录入后由真实数据替换；数据齐全时行数以真实关卡为准
  const skeleton = stages.length === 0
  const rowCount = Math.max(ranked.length, maxAssignedLast, skeleton ? 3 : 0)
  for (let index = 1; index <= rowCount; index += 1) {
    const stage = ranked[index - 1]
    rows.push({
      key: `last:${index}`,
      stageCode: stage?.Value ?? null,
      stageMat: stage?.DropName ?? null,
      notStarted: notStarted || skeleton,
      // 骨架态与真实数据行互斥：stages 为空时 ranked 必为空
      skeleton,
    })
  }

  if (jade || assignedKeys.has('jade') || skeleton) {
    rows.push({
      key: 'jade',
      stageCode: jade?.Value ?? null,
      stageMat: jade?.DropName ?? null,
      notStarted: notStarted || skeleton,
      skeleton,
    })
  }
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
  | 'skipped'
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
  if (user.skipActive) return { willInject: false, reason: 'skipped' }
  if (!user.intent) return { willInject: false, reason: 'no-intent' }
  if (period !== 'ongoing') return { willInject: false, reason: 'gap' }
  if (!resolveIntentStage(user.intent, stages)) {
    return { willInject: false, reason: 'no-match' }
  }
  return { willInject: true, reason: 'ok' }
}
