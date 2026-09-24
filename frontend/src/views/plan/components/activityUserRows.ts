// 计划表页「活动关指派表」的纯逻辑：选关选项、用户行状态、汇总与筛选。
// 表格组件只渲染；取数与写回在 useActivityStageAssignment；判玉/排序/解析原语
// 在 @/utils/activityStage（与后端 _resolve_activity_stage 同锚）。
//
// 行模型是「一行一个用户」：每人各自持有自己的选关意图，谁和谁同关无所谓，
// 因此这里没有槽位、没有一人一槽，也不需要把用户分组。

import type { ActivityItem } from '@/types/home'
import { isJadeStage, resolveIntentStage, stageNumber } from '@/utils/activityStage'

/** 表格行的用户模型（来自 MAA 脚本用户配置扫描） */
export interface ActivityUserRow {
  scriptId: string
  userId: string
  userName: string
  server: string
  /** Info.Status：停用用户不参与调度 */
  status: boolean
  ifQuickConfig: boolean
  ifActivityFirst: boolean
  intent: string
  /** 跳过簿当日命中：后端本轮不会注入 */
  skipToday: boolean
  /** 跳过簿记录的在打关卡摘要 */
  skipSummary: string
}

/** 行状态（key 供筛选与汇总，文案由 STATE_LABEL_KEYS 走词表） */
export type ActivityUserState =
  | 'inject'
  | 'no-intent'
  | 'switch-off'
  | 'no-quick-config'
  | 'disabled'
  | 'skipped'
  | 'no-match'
  | 'no-activity'

export const STATE_LABEL_KEYS: Record<ActivityUserState, string> = {
  inject: 'plan.activity.stateInject',
  'no-intent': 'plan.activity.stateNoIntent',
  'switch-off': 'plan.activity.stateSwitchOff',
  'no-quick-config': 'plan.activity.stateNoQuickConfig',
  disabled: 'plan.activity.stateDisabled',
  skipped: 'plan.activity.stateSkipped',
  'no-match': 'plan.activity.stateNoMatch',
  'no-activity': 'plan.activity.stateNoActivity',
}

/** 需要留意的状态（会挡住注入或说明这号根本没在跑）：汇总的「注意」与筛选用它 */
const ATTENTION_STATES: ActivityUserState[] = ['no-quick-config', 'disabled', 'skipped', 'no-match']

export const isAttentionState = (state: ActivityUserState): boolean =>
  ATTENTION_STATES.includes(state)

/**
 * 行状态：先看能不能跑（停用/未开快速配置），再看会不会注入
 * （总开关/跳过簿/意图/本期有没有这一关）。顺序即优先级。
 */
export function resolveUserState(
  row: Pick<
    ActivityUserRow,
    'status' | 'ifQuickConfig' | 'ifActivityFirst' | 'skipToday' | 'intent'
  >,
  stages: ActivityItem[],
  period: 'ongoing' | 'preview' | 'gap'
): ActivityUserState {
  if (!row.status) return 'disabled'
  if (!row.ifQuickConfig) return 'no-quick-config'
  if (!row.ifActivityFirst) return 'switch-off'
  if (row.skipToday) return 'skipped'
  if (!row.intent) return 'no-intent'
  if (period === 'gap') return 'no-activity'
  return resolveIntentStage(row.intent, stages) ? 'inject' : 'no-match'
}

export type ActivityFilter = 'all' | 'no-intent' | 'attention'

export function matchesFilter(state: ActivityUserState, filter: ActivityFilter): boolean {
  if (filter === 'all') return true
  if (filter === 'no-intent') return state === 'no-intent'
  return isAttentionState(state)
}

/** 选关下拉的一项：值 + 展示用的词表键与参数（标签由组件 t() 出来） */
export interface IntentOption {
  value: string
  labelKey: string
  labelParams: Record<string, string | number>
}

/** 下拉项 + 已渲染的标签（表格组件直接用，不再碰词表） */
export interface IntentOptionView extends IntentOption {
  label: string
}

const stageParams = (stage: ActivityItem): Record<string, string> => ({
  stage: stage.Value,
  mat: stage.DropName ?? '',
})

/**
 * 按该服当期（间隙期用下期预览）关卡生成选关选项：未指派 + 倒1…倒N + 搓玉。
 * 当前值不在本期选项里时（旧版序号、本期无此关、本期无搓玉关）补一条带着当前
 * 值的选项，避免下拉显示空白而状态行却在报正常注入。
 */
export function buildIntentOptions(stages: ActivityItem[], currentIntent: string): IntentOption[] {
  const options: IntentOption[] = [
    { value: '', labelKey: 'plan.activity.intentEmpty', labelParams: {} },
  ]

  const ranked = stages
    .filter(stage => !isJadeStage(stage))
    .sort((a, b) => stageNumber(b.Value) - stageNumber(a.Value))
  ranked.forEach((stage, index) => {
    options.push({
      value: `last:${index + 1}`,
      labelKey: 'plan.activity.intentLast',
      labelParams: { n: index + 1, ...stageParams(stage) },
    })
  })

  const jade = stages.find(stage => isJadeStage(stage))
  if (jade) {
    options.push({
      value: 'jade',
      labelKey: 'plan.activity.intentJade',
      labelParams: stageParams(jade),
    })
  }

  if (currentIntent && !options.some(option => option.value === currentIntent)) {
    options.push(currentIntentOption(currentIntent))
  }
  return options
}

/** 当前值的兜底选项：本期解析不到时也要看得见自己选的是什么 */
function currentIntentOption(intent: string): IntentOption {
  const rank = Number(intent.slice(intent.indexOf(':') + 1)) || 0
  if (intent.startsWith('pos:')) {
    return {
      value: intent,
      labelKey: 'plan.activity.intentLegacy',
      labelParams: { n: rank },
    }
  }
  if (intent.startsWith('last:')) {
    return {
      value: intent,
      labelKey: 'plan.activity.intentLastMissing',
      labelParams: { n: rank },
    }
  }
  return { value: intent, labelKey: 'plan.activity.intentJadeMissing', labelParams: {} }
}

/** 表格行视图模型：文案与选项都在这里备好，组件保持无逻辑 */
export interface ActivityUserRowView {
  key: string
  row: ActivityUserRow
  state: ActivityUserState
  /** 状态文案（已渲染） */
  stateText: string
  /** 该行自己服务器的期间态（各服可能不同期） */
  period: 'ongoing' | 'preview' | 'gap'
  /** 该行自己服务器的当期（或下期预览）关卡选项 */
  options: IntentOptionView[]
}

export interface ActivityRowSummary {
  /** 本表跟随用户数 */
  followed: number
  willInject: number
  attention: number
}

export function summarizeRows(states: ActivityUserState[]): ActivityRowSummary {
  return {
    followed: states.length,
    willInject: states.filter(state => state === 'inject').length,
    attention: states.filter(isAttentionState).length,
  }
}
