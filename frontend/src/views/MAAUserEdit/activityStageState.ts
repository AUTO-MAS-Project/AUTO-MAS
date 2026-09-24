// 用户编辑页「选关」下方状态行的纯逻辑（方案 §6 状态机，表/用户页同一套）。
// 输入意图与该用户服务器的进行中/下期预览关卡，输出 tone + i18n 键 + 参数。

import type { ActivityItem } from '@/types/home'
import { isJadeStage, readActivityMeta, resolveIntentStage } from '@/utils/activityStage'

export type ActivityStageTone = 'ok' | 'warn' | 'info' | 'muted'

export interface ActivityStageState {
  tone: ActivityStageTone
  messageKey: string
  params: Record<string, string | number>
}

/** 选关状态行：意图 × 期间（进行中/下期预览/间隙期）→ 展示态 */
export function resolveActivityStageState(
  intent: string,
  activity: ActivityItem[],
  preview: ActivityItem[]
): ActivityStageState {
  if (!intent) {
    return {
      tone: 'muted',
      messageKey: 'edit.activityStateNoIntent',
      params: {},
    }
  }
  const period = activity.length ? 'ongoing' : preview.length ? 'preview' : 'gap'
  if (period === 'gap') {
    return {
      tone: 'muted',
      messageKey: 'edit.activityStateGap',
      params: {},
    }
  }

  const stages = period === 'ongoing' ? activity : preview
  const meta = readActivityMeta(stages)
  const common = {
    name: meta?.name ?? '',
    tone: (period === 'preview' ? 'info' : 'ok') as ActivityStageTone,
  }

  if (intent === 'jade') {
    const jade = stages.find(stage => isJadeStage(stage))
    if (!jade) {
      return { tone: 'muted', messageKey: 'edit.activityStateNoJade', params: {} }
    }
    return {
      tone: common.tone,
      messageKey: period === 'preview' ? 'edit.activityStatePreview' : 'edit.activityStateOk',
      params: { stage: jade.Value, mat: jade.DropName, name: common.name },
    }
  }

  if (intent.startsWith('last:')) {
    const index = Number(intent.slice(5)) || 0
    const stage = resolveIntentStage(intent, stages)
    if (!stage) {
      return {
        tone: 'muted',
        messageKey: 'edit.activityStateNoStage',
        params: { n: index },
      }
    }
    const dropName = stages.find(item => item.Value === stage)?.DropName ?? ''
    return {
      tone: common.tone,
      messageKey: period === 'preview' ? 'edit.activityStatePreview' : 'edit.activityStateOk',
      params: { stage, mat: dropName, name: common.name },
    }
  }

  return { tone: 'muted', messageKey: 'edit.activityStateNoIntent', params: {} }
}
