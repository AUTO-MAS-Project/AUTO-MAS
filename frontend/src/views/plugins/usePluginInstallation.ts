import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import type { PluginCatalogDocument } from '@/api'
import { usePluginApi } from '@/composables/usePluginApi'
import { apiErrorMessage } from '@/utils/apiResult'
import { pluginActionHint } from './configActions'
import { isInstallPhaseActive, type InstallPhase } from './pluginCenterModel'
import type { PluginOperationLock } from './pluginOperationLock'

export interface InstallTask {
  /** 市场条目 uid，也是安装命令的目标。 */
  uid: string
  pluginId: string | null
  upgrade: boolean
  phase: InstallPhase
}

export interface InstallSequenceResult {
  succeeded: string[]
  failed: string[]
  /** 没有执行的条目：前一项失败，或执行前按最新目录判断已无更新、不可安装。 */
  skipped: string[]
}

const installable = (row: PluginCatalogDocument) =>
  pluginActionHint(row.ui, 'info', 'install')?.editable === true

/**
 * 安装与升级的状态源：对外给出「哪个插件、处于哪个阶段」，由市场卡片和更新列表就地显示。
 * 跨重启流程仍由 usePluginApi.runCommand 负责；调用方组件释放后轮询停止，后台安装继续由宿主持有，
 * 再次进入时 runCommand 会接上等待重启的候选。
 */
export function usePluginInstallation(
  lock: PluginOperationLock,
  options: {
    onInstalled?: () => Promise<unknown>
    /**
     * 按 uid 取当前最新的市场条目；「全部更新」每项执行前用它重新判断。
     * 返回空表示条目已不在目录里。不传时沿用调用时给的条目。
     */
    latest?: (uid: string) => PluginCatalogDocument | null | undefined
  } = {}
) {
  const api = usePluginApi()
  const { t } = useI18n()
  const tasks = ref<Record<string, InstallTask>>({})

  const update = (task: InstallTask) => {
    tasks.value = { ...tasks.value, [task.uid]: task }
  }
  const drop = (uids: readonly string[]) => {
    const next = { ...tasks.value }
    for (const uid of uids) delete next[uid]
    tasks.value = next
  }

  const runOne = async (row: PluginCatalogDocument): Promise<boolean> => {
    // 以市场配置 UID 提交原安装触发器，安装与升级均等待完整加载结果后反馈。
    const task: InstallTask = {
      uid: row.uid,
      pluginId: row.info?.plugin_name ?? null,
      upgrade: row.info?.update_available === true,
      phase: 'running',
    }
    update(task)
    try {
      await api.runCommand(
        'install',
        { configUid: row.uid, group: 'info', field: 'install', value: true },
        stage => update({ ...task, phase: stage })
      )
      update({ ...task, phase: 'succeeded' })
      message.success(t(task.upgrade ? 'core.plugins.upgraded' : 'core.plugins.installed'))
      return true
    } catch (error) {
      update({ ...task, phase: 'failed' })
      message.error(apiErrorMessage(error, t('core.plugins.actionFailed')))
      return false
    }
  }

  const install = async (row: PluginCatalogDocument): Promise<boolean> => {
    // 与其他插件操作互斥；按钮可点与否只看后端界面提示。
    if (!installable(row) || !lock.acquire({ uid: row.uid, action: 'install' })) return false
    try {
      const succeeded = await runOne(row)
      if (succeeded) await options.onInstalled?.()
      return succeeded
    } finally {
      lock.release()
    }
  }

  const installSequence = async (
    rows: readonly PluginCatalogDocument[]
  ): Promise<InstallSequenceResult> => {
    // 「全部更新」按顺序逐个执行；一项失败即停止，剩余条目回到未排队状态。
    // 前一项升级（可能跨重启）并回读后目录会变，每项执行前按最新条目重新判断。
    const result: InstallSequenceResult = { succeeded: [], failed: [], skipped: [] }
    const candidates = rows.filter(installable)
    if (!candidates.length || !lock.acquire({ uid: candidates[0].uid, action: 'install' }))
      return result
    for (const row of candidates)
      update({
        uid: row.uid,
        pluginId: row.info?.plugin_name ?? null,
        upgrade: row.info?.update_available === true,
        phase: 'queued',
      })
    try {
      for (const [index, queued] of candidates.entries()) {
        const row = options.latest ? options.latest(queued.uid) : queued
        if (!row || row.info?.update_available !== true || !installable(row)) {
          // 已无更新或不可安装：不提交命令，也不算失败。
          result.skipped.push(queued.uid)
          drop([queued.uid])
          continue
        }
        lock.retarget({ uid: row.uid, action: 'install' })
        if (await runOne(row)) {
          result.succeeded.push(row.uid)
          await options.onInstalled?.()
          continue
        }
        result.failed.push(row.uid)
        result.skipped.push(...candidates.slice(index + 1).map(item => item.uid))
        break
      }
    } finally {
      drop(Object.values(tasks.value).flatMap(task => (task.phase === 'queued' ? task.uid : [])))
      lock.release()
    }
    return result
  }

  return {
    /** 按市场 uid 记录的任务；完成或失败的结果保留到该条目下次安装。 */
    tasks: computed(() => tasks.value),
    /** 正在执行（未排队、未结束）的任务。 */
    active: computed(
      () =>
        Object.values(tasks.value).find(
          task => isInstallPhaseActive(task.phase) && task.phase !== 'queued'
        ) ?? null
    ),
    taskOf: (uid: string): InstallTask | null => tasks.value[uid] ?? null,
    install,
    installSequence,
  }
}

export type PluginInstallationController = ReturnType<typeof usePluginInstallation>
