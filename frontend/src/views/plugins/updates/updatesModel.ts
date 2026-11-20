import {
  actionEditable,
  actionVisible,
  installPhaseLabelKey,
  isInstallPhaseActive,
  isInstallRestartPhase,
  type InstallPhase,
  type MarketEntryView,
  type PluginStatus,
  type PluginUpdateView,
} from '../pluginCenterModel'
import type { InstallTask } from '../usePluginInstallation'

/**
 * 「更新」页签的纯计算：行内阶段标签、可批量更新的条目、需要重启的集中提示。
 * 是否可更新只看后端的 update_available（由 updatableEntries 保证），按钮显隐只看界面提示。
 */

const ROW_PHASE: Record<InstallPhase, Pick<PluginStatus, 'labelKey' | 'tone'> | null> = {
  queued: { labelKey: 'core.plugins.installPhase.queued', tone: 'default' },
  running: null,
  waiting: { labelKey: 'core.plugins.updates.waitingRestart', tone: 'warning' },
  restarting: { labelKey: 'core.plugins.updates.restarting', tone: 'processing' },
  recovering: { labelKey: 'core.plugins.updates.recovering', tone: 'warning' },
  // 已完成不挂标签，见 updatePhaseStatus。
  succeeded: null,
  failed: { labelKey: 'core.plugins.installPhase.failed', tone: 'error' },
}

/** 行内阶段标签；没有任务时返回 null，不显示。 */
export function updatePhaseStatus(task: InstallTask | null): PluginStatus | null {
  // 已完成的行还留在可更新列表里，只可能是又出了新版本或回读失败：只留按钮，不再挂「已完成」。
  if (!task || task.phase === 'succeeded') return null
  const known = ROW_PHASE[task.phase]
  if (known) return { ...known, raw: task.phase }
  return {
    labelKey: installPhaseLabelKey(task.phase, task.upgrade),
    raw: task.phase,
    tone: 'processing',
  }
}

/**
 * 排队和进行中只显示阶段，其余都给「更新至」按钮：失败可以重试；
 * 本次已成功、后端仍说可更新，说明又出了新版本，和市场卡片的口径一致。
 */
export function showsUpdateButton(entry: MarketEntryView, task: InstallTask | null): boolean {
  if (!actionVisible(entry, 'install')) return false
  return !isInstallPhaseActive(task?.phase)
}

/** 「全部更新」：界面提示里有安装操作的可更新项按目录顺序排队；至少两项时出现，其中有可执行的才可点。 */
export function batchUpdateState(updates: readonly PluginUpdateView[]) {
  const targets = updates.flatMap(item => (actionVisible(item.entry, 'install') ? item.entry : []))
  return {
    visible: targets.length >= 2,
    editable: targets.some(entry => actionEditable(entry, 'install')),
    targets,
  }
}

/** 正在等待或执行后端重启的任务；没有时返回 null。 */
export function restartTask(active: InstallTask | null): InstallTask | null {
  return active && isInstallRestartPhase(active.phase) ? active : null
}

/** 市场里已安装且后端判为无更新的条目数；拿不到就是 0，由调用方不显示。 */
export function upToDateCount(market: readonly MarketEntryView[]): number {
  return market.filter(entry => entry.installed && !entry.updateAvailable).length
}
